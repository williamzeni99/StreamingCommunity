# 18.07.25

import os
import platform
import logging
import shutil
import zipfile


# External library
import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn


# Variable
console = Console()

BENTO4_CONFIGURATION = {
    'windows': {
        'base_dir': lambda home: os.path.join(os.path.splitdrive(home)[0] + os.sep, 'binary'),
        'download_url': 'https://www.bok.net/Bento4/binaries/Bento4-SDK-{version}.{platform}.zip',
        'versions': {
            'x64': 'x86_64-microsoft-win32',
            'x86': 'x86-microsoft-win32-vs2010',
        },
        'executables': ['mp4decrypt.exe']
    },
    'darwin': {
        'base_dir': lambda home: os.path.join(home, 'Applications', 'binary'),
        'download_url': 'https://www.bok.net/Bento4/binaries/Bento4-SDK-{version}.{platform}.zip',
        'versions': {
            'x64': 'universal-apple-macosx',
            'arm64': 'universal-apple-macosx'
        },
        'executables': ['mp4decrypt']
    },
    'linux': {
        'base_dir': lambda home: os.path.join(home, '.local', 'bin', 'binary'),
        'download_url': 'https://www.bok.net/Bento4/binaries/Bento4-SDK-{version}.{platform}.zip',
        'versions': {
            'x64': 'x86_64-unknown-linux',
            'x86': 'x86-unknown-linux',
            'arm64': 'x86_64-unknown-linux'
        },
        'executables': ['mp4decrypt']
    }
}


class Bento4Downloader:
    def __init__(self):
        self.os_name = platform.system().lower()
        self.arch = self._detect_arch()
        self.home_dir = os.path.expanduser('~')
        self.base_dir = BENTO4_CONFIGURATION[self.os_name]['base_dir'](self.home_dir)
        self.version = "1-6-0-641"  # Latest stable version as of Nov 2023
        os.makedirs(self.base_dir, exist_ok=True)

    def _detect_arch(self) -> str:
        machine = platform.machine().lower()
        arch_map = {
            'amd64': 'x64', 
            'x86_64': 'x64',
            'x64': 'x64',
            'arm64': 'arm64',
            'aarch64': 'arm64',
            'x86': 'x86',
            'i386': 'x86',
            'i686': 'x86'
        }
        return arch_map.get(machine, machine)

    def _download_file(self, url: str, destination: str) -> bool:
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            
            with open(destination, 'wb') as file, \
                Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                    TimeRemainingColumn()
                ) as progress:
                
                download_task = progress.add_task("[green]Downloading Bento4", total=total_size)
                for chunk in response.iter_content(chunk_size=8192):
                    size = file.write(chunk)
                    progress.update(download_task, advance=size)

            return True
        
        except Exception as e:
            logging.error(f"Download error: {e}")
            return False

    def _extract_executables(self, zip_path: str) -> list:
        try:
            extracted_files = []
            config = BENTO4_CONFIGURATION[self.os_name]
            executables = config['executables']

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for zip_info in zip_ref.filelist:
                    for executable in executables:
                        if zip_info.filename.endswith(executable):

                            # Extract to base directory
                            zip_ref.extract(zip_info, self.base_dir)
                            src_path = os.path.join(self.base_dir, zip_info.filename)
                            dst_path = os.path.join(self.base_dir, executable)
                            
                            # Move to final location
                            shutil.move(src_path, dst_path)
                            os.chmod(dst_path, 0o755)
                            extracted_files.append(dst_path)
                            
                            # Clean up intermediate directories
                            parts = zip_info.filename.split('/')
                            if len(parts) > 1:
                                shutil.rmtree(os.path.join(self.base_dir, parts[0]))

            return extracted_files

        except Exception as e:
            logging.error(f"Extraction error: {e}")
            return []

    def download(self) -> list:
        try:
            config = BENTO4_CONFIGURATION[self.os_name]
            platform_str = config['versions'].get(self.arch)
            
            if not platform_str:
                raise ValueError(f"Unsupported architecture: {self.arch}")

            download_url = config['download_url'].format(
                version=self.version,
                platform=platform_str
            )
            
            zip_path = os.path.join(self.base_dir, "bento4.zip")
            console.print(f"[bold blue]Downloading Bento4 from {download_url}[/]")

            if self._download_file(download_url, zip_path):
                extracted_files = self._extract_executables(zip_path)
                os.remove(zip_path)
                
                if extracted_files:
                    console.print("[bold green]Bento4 successfully installed[/]")
                    return extracted_files
                    
            raise Exception("Failed to install Bento4")

        except Exception as e:
            logging.error(f"Error downloading Bento4: {e}")
            console.print(f"[bold red]Error downloading Bento4: {str(e)}[/]")
            return []

def check_mp4decrypt() -> str:
    """Check for mp4decrypt in the system and download if not found."""
    try:
        # First check if mp4decrypt is in PATH
        mp4decrypt = "mp4decrypt.exe" if platform.system().lower() == "windows" else "mp4decrypt"
        mp4decrypt_path = shutil.which(mp4decrypt)
        
        if mp4decrypt_path:
            return mp4decrypt_path

        # If not found, check in binary directory
        downloader = Bento4Downloader()
        base_dir = downloader.base_dir
        local_path = os.path.join(base_dir, mp4decrypt)
        
        if os.path.exists(local_path):
            return local_path

        # Download if not found
        extracted_files = downloader.download()
        return extracted_files[0] if extracted_files else None

    except Exception as e:
        logging.error(f"Error checking or downloading mp4decrypt: {e}")
        return None
    
    except Exception as e:
        logging.error(f"Error checking or downloading mp4decrypt: {e}")
        return None
