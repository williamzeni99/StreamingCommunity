# 18.04.24

import os
import sys
import asyncio
import logging
import binascii
from urllib.parse import urljoin, urlparse
from typing import Dict


# External libraries
import httpx
from tqdm import tqdm
from rich.console import Console


# Internal utilities
from StreamingCommunity.Util.color import Colors
from StreamingCommunity.Util.headers import get_userAgent
from StreamingCommunity.Util.config_json import config_manager


# Logic class
from ...M3U8 import (
    M3U8_Decryption,
    M3U8_Ts_Estimator,
    M3U8_Parser,
    M3U8_UrlFix
)

# Config
TQDM_DELAY_WORKER = 0.01
REQUEST_MAX_RETRY = config_manager.get_int('REQUESTS', 'max_retry')
REQUEST_VERIFY = config_manager.get_bool('REQUESTS', 'verify')
DEFAULT_VIDEO_WORKERS = config_manager.get_int('M3U8_DOWNLOAD', 'default_video_workers')
DEFAULT_AUDIO_WORKERS = config_manager.get_int('M3U8_DOWNLOAD', 'default_audio_workers')
MAX_TIMEOOUT = config_manager.get_int("REQUESTS", "timeout")
SEGMENT_MAX_TIMEOUT = config_manager.get_int("M3U8_DOWNLOAD", "segment_timeout")


# Variable
console = Console()


class M3U8_Segments:
    def __init__(self, url: str, tmp_folder: str, is_index_url: bool = True):
        """
        Initializes the M3U8_Segments object.

        Parameters:
            - url (str): The URL of the M3U8 playlist.
            - tmp_folder (str): The temporary folder to store downloaded segments.
            - is_index_url (bool): Flag indicating if `m3u8_index` is a URL (default True).
        """
        self.url = url
        self.tmp_folder = tmp_folder
        self.is_index_url = is_index_url
        self.tmp_file_path = os.path.join(self.tmp_folder, "0.ts")
        os.makedirs(self.tmp_folder, exist_ok=True)

        # Util class
        self.decryption: M3U8_Decryption = None 
        self.class_url_fixer = M3U8_UrlFix(url)
        
        # Download tracking
        self.downloaded_segments = set()
        self.download_interrupted = False
        self.info_nFailed = 0
        self.info_nRetry = 0

    def __get_key__(self, m3u8_parser: M3U8_Parser) -> bytes:
        """
        Fetches the encryption key from the M3U8 playlist.

        Args:
            m3u8_parser (M3U8_Parser): An instance of M3U8_Parser containing parsed M3U8 data.

        Returns:
            bytes: The decryption key in byte format.
        """
        key_uri = urljoin(self.url, m3u8_parser.keys.get('uri'))
        parsed_url = urlparse(key_uri)
        self.key_base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
        
        try:
            client_params = {'headers': {'User-Agent': get_userAgent()}, 'timeout': MAX_TIMEOOUT, 'verify': REQUEST_VERIFY}
            response = httpx.get(url=key_uri, **client_params)
            response.raise_for_status()

            hex_content = binascii.hexlify(response.content).decode('utf-8')
            return bytes.fromhex(hex_content)
            
        except Exception as e:
            raise Exception(f"Failed to fetch key: {e}")
    
    def parse_data(self, m3u8_content: str) -> None:
        """
        Parses the M3U8 content and extracts necessary data.

        Args:
            m3u8_content (str): The raw M3U8 playlist content.
        """
        m3u8_parser = M3U8_Parser()
        m3u8_parser.parse_data(uri=self.url, raw_content=m3u8_content)

        self.expected_real_time_s = m3u8_parser.duration

        if m3u8_parser.keys:
            key = self.__get_key__(m3u8_parser)    
            self.decryption = M3U8_Decryption(
                key, 
                m3u8_parser.keys.get('iv'), 
                m3u8_parser.keys.get('method')
            )

        self.segments = [
            self.class_url_fixer.generate_full_url(seg)
            if "http" not in seg else seg
            for seg in m3u8_parser.segments
        ]

    def get_info(self) -> None:
        """
        Retrieves M3U8 playlist information from the given URL.
        """
        if self.is_index_url:
            try:
                client_params = {'headers': {'User-Agent': get_userAgent()}, 'timeout': MAX_TIMEOOUT, 'verify': REQUEST_VERIFY}
                response = httpx.get(self.url, **client_params, follow_redirects=True)
                response.raise_for_status()
                
                self.parse_data(response.text)
                with open(os.path.join(self.tmp_folder, "playlist.m3u8"), "w") as f:
                    f.write(response.text)
                    
            except Exception as e:
                raise RuntimeError(f"M3U8 info retrieval failed: {e}")
    
    def download_streams(self, description: str, type: str):
        """
        Synchronous wrapper for async download.
        """
        try:
            return asyncio.run(self.download_segments(description=description, type=type))
        
        except KeyboardInterrupt:
            self.download_interrupted = True
            console.print("\n[red]Download interrupted by user (Ctrl+C).")
            return self._generate_results(type)

    async def download_segments(self, description: str, type: str, concurrent_downloads: int = 8):
        """
        Download segments asynchronously.
        """
        self.get_info()
        
        progress_bar = tqdm(
            total=len(self.segments),
            unit='s',
            ascii='░▒█',
            bar_format=self._get_bar_format(description),
            mininterval=0.6,
            maxinterval=1.0,
            file=sys.stdout
        )

        # Initialize estimator
        estimator = M3U8_Ts_Estimator(total_segments=len(self.segments))
        semaphore = asyncio.Semaphore(self._get_worker_count(type))
        
        results = [None] * len(self.segments)
        
        try:
            async with httpx.AsyncClient(timeout=SEGMENT_MAX_TIMEOUT) as client:

                # Download all segments (first batch)
                await self._download_segments_batch(
                    client, self.segments, results, semaphore, 
                    REQUEST_MAX_RETRY, estimator, progress_bar
                )

                # Retry failed segments
                await self._retry_failed_segments(
                    client, self.segments, results, semaphore,
                    REQUEST_MAX_RETRY, estimator, progress_bar
                )

                # Write results
                self._write_results_to_file(results)

        except Exception as e:
            logging.error(f"Download error: {e}")
            raise

        finally:
            self._cleanup_resources(progress_bar)

        if not self.download_interrupted:
            self._verify_download_completion()

        return self._generate_results(type)

    async def _download_segments_batch(self, client, segment_urls, results, semaphore, max_retry, estimator, progress_bar):
        """
        Download a batch of segments with retry logic.
        """
        async def download_single(url, idx):
            async with semaphore:
                for attempt in range(max_retry):
                    try:
                        resp = await client.get(url, headers={'User-Agent': get_userAgent()})

                        if resp.status_code == 200:
                            content = resp.content

                            if self.decryption:
                                content = self.decryption.decrypt(content)
                            return idx, content, attempt
                        
                        await asyncio.sleep(1.1 * (2 ** attempt))
                        logging.info(f"Segment {idx} failed with status {resp.status_code}. Retrying...")
                    
                    except Exception:
                        await asyncio.sleep(1.1 * (2 ** attempt))
                        logging.info(f"Segment {idx} download failed: {sys.exc_info()[1]}. Retrying...")

                return idx, b'', max_retry

        tasks = [download_single(url, i) for i, url in enumerate(segment_urls)]
        
        for coro in asyncio.as_completed(tasks):
            try:
                idx, data, nretry = await coro
                results[idx] = data

                if data:
                    self.downloaded_segments.add(idx)
                    estimator.add_ts_file(len(data))
                    estimator.update_progress_bar(len(data), progress_bar)

                else:
                    self.info_nFailed += 1

                self.info_nRetry += nretry
                progress_bar.update(1)

            except KeyboardInterrupt:
                self.download_interrupted = True
                break

    async def _retry_failed_segments(self, client, segment_urls, results, semaphore, max_retry, estimator, progress_bar):
        """
        Retry failed segments with exponential backoff.
        """
        max_global_retries = 5
        global_retry_count = 0

        while (self.info_nFailed > 0 and 
               global_retry_count < max_global_retries and 
               not self.download_interrupted):
            
            failed_indices = [i for i, data in enumerate(results) if not data]
            if not failed_indices:
                break

            logging.info(f"[yellow]Retrying {len(failed_indices)} failed segments...")

            retry_tasks = [
                self._download_segments_batch(
                    client, [segment_urls[i]], [results[i]], 
                    semaphore, max_retry, estimator, progress_bar
                )
                for i in failed_indices
            ]
            
            await asyncio.gather(*retry_tasks)
            global_retry_count += 1

    def _write_results_to_file(self, results):
        """
        Write downloaded segments to file.
        """
        with open(self.tmp_file_path, 'wb') as f:
            for data in results:
                if data:
                    f.write(data)
                    f.flush()

    def _get_bar_format(self, description: str) -> str:
        """
        Generate platform-appropriate progress bar format.
        """
        return (
            f"{Colors.YELLOW}[HLS] {Colors.WHITE}({Colors.CYAN}{description}{Colors.WHITE}): "
            f"{Colors.RED}{{percentage:.2f}}% "
            f"{Colors.MAGENTA}{{bar}} "
            f"{Colors.YELLOW}{{elapsed}}{Colors.WHITE} < {Colors.CYAN}{{remaining}}{Colors.WHITE}{{postfix}}{Colors.WHITE}"
        )
    
    def _get_worker_count(self, stream_type: str) -> int:
        """
        Calculate optimal parallel workers based on stream type and infrastructure.
        """
        base_workers = {
            'video': DEFAULT_VIDEO_WORKERS,
            'audio': DEFAULT_AUDIO_WORKERS
        }.get(stream_type.lower(), 1)

        return base_workers
    
    def _generate_results(self, stream_type: str) -> Dict:
        """
        Package final download results.
        """
        return {
            'type': stream_type,
            'nFailed': self.info_nFailed,
            'stopped': self.download_interrupted
        }
    
    def _verify_download_completion(self) -> None:
        """
        Validate final download integrity.
        """
        total = len(self.segments)
        if len(self.downloaded_segments) / total < 0.999:
            missing = sorted(set(range(total)) - self.downloaded_segments)
            raise RuntimeError(f"Download incomplete ({len(self.downloaded_segments)/total:.1%}). Missing segments: {missing}")
        
    def _cleanup_resources(self, progress_bar: tqdm) -> None:
        """
        Ensure resource cleanup and final reporting.
        """
        progress_bar.close()
            
        if self.info_nFailed > 0:
            self._display_error_summary()

    def _display_error_summary(self) -> None:
        """
        Generate final error report.
        """
        console.print(f"\n[cyan]Retry Summary: "
                     f"[white]Max retries: [green]{self.info_maxRetry} "
                     f"[white]Total retries: [green]{self.info_nRetry} "
                     f"[white]Failed segments: [red]{self.info_nFailed}")
        
        if self.info_nRetry > len(self.segments) * 0.3:
            console.print("[yellow]Warning: High retry count detected. Consider reducing worker count in config.")