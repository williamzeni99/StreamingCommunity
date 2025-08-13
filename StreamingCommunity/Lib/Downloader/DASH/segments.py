# 25.07.25

import os
import asyncio


# External libraries
import httpx
from tqdm import tqdm


# Internal utilities
from StreamingCommunity.Util.headers import get_userAgent
from StreamingCommunity.Lib.M3U8.estimator import M3U8_Ts_Estimator
from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Util.color import Colors


# Config
REQUEST_MAX_RETRY = config_manager.get_int('REQUESTS', 'max_retry')
DEFAULT_VIDEO_WORKERS = config_manager.get_int('M3U8_DOWNLOAD', 'default_video_workers')
DEFAULT_AUDIO_WORKERS = config_manager.get_int('M3U8_DOWNLOAD', 'default_audio_workers')
SEGMENT_MAX_TIMEOUT = config_manager.get_int("M3U8_DOWNLOAD", "segment_timeout")


class MPD_Segments:
    def __init__(self, tmp_folder: str, representation: dict, pssh: str = None):
        """
        Initialize MPD_Segments with temp folder, representation, and optional pssh.
        """
        self.tmp_folder = tmp_folder
        self.selected_representation = representation
        self.pssh = pssh
        self.download_interrupted = False
        self.info_nFailed = 0

    def get_concat_path(self, output_dir: str = None):
        """
        Get the path for the concatenated output file.
        """
        rep_id = self.selected_representation['id']
        return os.path.join(output_dir or self.tmp_folder, f"{rep_id}_encrypted.m4s")

    def download_streams(self, output_dir: str = None):
        """
        Synchronous wrapper for download_segments, compatible with legacy calls.
        """
        concat_path = self.get_concat_path(output_dir)

        # Run async download in sync mode
        try:
            asyncio.run(self.download_segments(output_dir=output_dir))

        except KeyboardInterrupt:
            self.download_interrupted = True
            print("\n[red]Download interrupted by user (Ctrl+C).")

        return {
            "concat_path": concat_path,
            "representation_id": self.selected_representation['id'],
            "pssh": self.pssh
        }

    async def download_segments(self, output_dir: str = None, concurrent_downloads: int = 8, description: str = "DASH"):
        """
        Download and concatenate all segments (including init) asynchronously and in order.
        """
        rep = self.selected_representation
        rep_id = rep['id']
        segment_urls = rep['segment_urls']
        init_url = rep.get('init_url')

        os.makedirs(output_dir or self.tmp_folder, exist_ok=True)
        concat_path = os.path.join(output_dir or self.tmp_folder, f"{rep_id}_encrypted.m4s")

        # Determine stream type (video/audio) for progress bar
        stream_type = rep.get('type', description)
        progress_bar = tqdm(
            total=len(segment_urls) + 1,
            desc=f"Downloading {rep_id}",
            bar_format=self._get_bar_format(stream_type),
            mininterval=0.6,
            maxinterval=1.0
        )

        # Define semaphore for concurrent downloads
        semaphore = asyncio.Semaphore(concurrent_downloads)

        # Initialize estimator
        estimator = M3U8_Ts_Estimator(total_segments=len(segment_urls) + 1)

        results = [None] * len(segment_urls)
        self.downloaded_segments = set()
        self.info_nFailed = 0
        self.download_interrupted = False
        self.info_nRetry = 0

        try:
            async with httpx.AsyncClient(timeout=SEGMENT_MAX_TIMEOUT) as client:
                # Download init segment
                await self._download_init_segment(client, init_url, concat_path, estimator, progress_bar)

                # Download all segments (first batch)
                await self._download_segments_batch(
                    client, segment_urls, results, semaphore, REQUEST_MAX_RETRY, estimator, progress_bar
                )

                # Retry failed segments 
                await self._retry_failed_segments(
                    client, segment_urls, results, semaphore, REQUEST_MAX_RETRY, estimator, progress_bar
                )

                # Write all results to file
                self._write_results_to_file(concat_path, results)

        except KeyboardInterrupt:
            self.download_interrupted = True
            print("\n[red]Download interrupted by user (Ctrl+C).")

        finally:
            self._cleanup_resources(None, progress_bar)

        self._verify_download_completion()
        return self._generate_results(stream_type)

    async def _download_init_segment(self, client, init_url, concat_path, estimator, progress_bar):
        """
        Download the init segment and update progress/estimator.
        """
        if not init_url:
            with open(concat_path, 'wb') as outfile:
                pass
            return
        
        try:
            headers = {'User-Agent': get_userAgent()}
            response = await client.get(init_url, headers=headers)

            with open(concat_path, 'wb') as outfile:
                if response.status_code == 200:
                    outfile.write(response.content)
                    # Update estimator with init segment size
                    estimator.add_ts_file(len(response.content))

            progress_bar.update(1)

            # Update progress bar with estimated info
            estimator.update_progress_bar(len(response.content), progress_bar)

        except Exception as e:
            progress_bar.close()
            raise RuntimeError(f"Error downloading init segment: {e}")

    async def _download_segments_batch(self, client, segment_urls, results, semaphore, max_retry, estimator, progress_bar):
        """
        Download a batch of segments and update results.
        """
        async def download_single(url, idx):
            async with semaphore:
                headers = {'User-Agent': get_userAgent()}
                for attempt in range(max_retry):
                    try:
                        resp = await client.get(url, headers=headers)
                        if resp.status_code == 200:
                            return idx, resp.content, attempt
                        else:
                            await asyncio.sleep(1.1 * (2 ** attempt))
                    except Exception:
                        await asyncio.sleep(1.1 * (2 ** attempt))
                return idx, b'', max_retry

        # Initial download attempt
        tasks = [download_single(url, i) for i, url in enumerate(segment_urls)]

        for coro in asyncio.as_completed(tasks):
            try:
                idx, data, nretry = await coro
                results[idx] = data
                if data and len(data) > 0:
                    self.downloaded_segments.add(idx)
                else:
                    self.info_nFailed += 1
                self.info_nRetry += nretry
                progress_bar.update(1)

                # Update estimator with segment size
                estimator.add_ts_file(len(data))

                # Update progress bar with estimated info
                estimator.update_progress_bar(len(data), progress_bar)

            except KeyboardInterrupt:
                self.download_interrupted = True
                print("\n[red]Download interrupted by user (Ctrl+C).")
                break

    async def _retry_failed_segments(self, client, segment_urls, results, semaphore, max_retry, estimator, progress_bar):
        """
        Retry failed segments up to 5 times.
        """
        max_global_retries = 5
        global_retry_count = 0

        while self.info_nFailed > 0 and global_retry_count < max_global_retries and not self.download_interrupted:
            failed_indices = [i for i, data in enumerate(results) if not data or len(data) == 0]
            if not failed_indices:
                break

            print(f"[yellow]Retrying {len(failed_indices)} failed segments (attempt {global_retry_count+1}/{max_global_retries})...")
            async def download_single(url, idx):
                async with semaphore:
                    headers = {'User-Agent': get_userAgent()}

                    for attempt in range(max_retry):
                        try:
                            resp = await client.get(url, headers=headers)

                            if resp.status_code == 200:
                                return idx, resp.content, attempt
                            else:
                                await asyncio.sleep(1.1 * (2 ** attempt))

                        except Exception:
                            await asyncio.sleep(1.1 * (2 ** attempt))
                return idx, b'', max_retry

            retry_tasks = [download_single(segment_urls[i], i) for i in failed_indices]

            # Reset nFailed for this round
            nFailed_this_round = 0
            for coro in asyncio.as_completed(retry_tasks):
                try:
                    idx, data, nretry = await coro

                    if data and len(data) > 0:
                        results[idx] = data
                        self.downloaded_segments.add(idx)
                    else:
                        nFailed_this_round += 1

                    self.info_nRetry += nretry
                    progress_bar.update(0)  # No progress bar increment, already counted
                    estimator.add_ts_file(len(data))
                    estimator.update_progress_bar(len(data), progress_bar)

                except KeyboardInterrupt:
                    self.download_interrupted = True
                    print("\n[red]Download interrupted by user (Ctrl+C).")
                    break
            self.info_nFailed = nFailed_this_round
            global_retry_count += 1

    def _write_results_to_file(self, concat_path, results):
        """
        Write all downloaded segments to the output file.
        """
        with open(concat_path, 'ab') as outfile:
            for data in results:
                if data:
                    outfile.write(data)

    def _get_bar_format(self, description: str) -> str:
        """
        Generate platform-appropriate progress bar format.
        """
        return (
            f"{Colors.YELLOW}[MPD] ({Colors.CYAN}{description}{Colors.WHITE}): "
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

    def _generate_results(self, stream_type: str) -> dict:
        """
        Package final download results.
        """
        return {
            'type': stream_type,
            'nFailed': getattr(self, 'info_nFailed', 0),
            'stopped': getattr(self, 'download_interrupted', False)
        }

    def _verify_download_completion(self) -> None:
        """
        Validate final download integrity.
        """
        total = len(self.selected_representation['segment_urls'])
        completed = getattr(self, 'downloaded_segments', set())

        # If interrupted, skip raising error
        if self.download_interrupted:
            return
        
        if total == 0:
            return
        
        if len(completed) / total < 0.999:
            missing = sorted(set(range(total)) - completed)
            raise RuntimeError(f"Download incomplete ({len(completed)/total:.1%}). Missing segments: {missing}")

    def _cleanup_resources(self, writer_thread, progress_bar: tqdm) -> None:
        """
        Ensure resource cleanup and final reporting.
        """
        progress_bar.close()
        if getattr(self, 'info_nFailed', 0) > 0:
            self._display_error_summary()
            
        self.buffer = {}
        self.expected_index = 0

    def _display_error_summary(self) -> None:
        """
        Generate final error report.
        """
        print(f"\n[cyan]Retry Summary: "
              f"[white]Max retries: [green]{getattr(self, 'info_maxRetry', 0)} "
              f"[white]Total retries: [green]{getattr(self, 'info_nRetry', 0)} "
              f"[white]Failed segments: [red]{getattr(self, 'info_nFailed', 0)}")
        
        if getattr(self, 'info_nRetry', 0) > len(self.selected_representation['segment_urls']) * 0.3:
            print("[yellow]Warning: High retry count detected. Consider reducing worker count in config.")