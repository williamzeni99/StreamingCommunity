# 09.06.24

import os
import re
import sys
import time
import signal
import logging
from functools import partial


# External libraries
from tqdm import tqdm
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel


# Internal utilities
from StreamingCommunity.Util.headers import get_userAgent
from StreamingCommunity.Util.http_client import create_client
from StreamingCommunity.Util.color import Colors
from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Util.os import internet_manager, os_manager
from StreamingCommunity.TelegramHelp.telegram_bot import get_bot_instance


# Logic class
from ...FFmpeg import print_duration_table


# Config
REQUEST_VERIFY = config_manager.get_bool('REQUESTS', 'verify')
REQUEST_TIMEOUT = config_manager.get_float('REQUESTS', 'timeout')
TELEGRAM_BOT = config_manager.get_bool('DEFAULT', 'telegram_bot')


# Variable
msg = Prompt()
console = Console()


class InterruptHandler:
    def __init__(self):
        self.interrupt_count = 0
        self.last_interrupt_time = 0
        self.kill_download = False
        self.force_quit = False


def signal_handler(signum, frame, interrupt_handler, original_handler):
    """Enhanced signal handler for multiple interrupt scenarios"""
    current_time = time.time()
    
    # Reset counter if more than 2 seconds have passed since last interrupt
    if current_time - interrupt_handler.last_interrupt_time > 2:
        interrupt_handler.interrupt_count = 0
    
    interrupt_handler.interrupt_count += 1
    interrupt_handler.last_interrupt_time = current_time

    if interrupt_handler.interrupt_count == 1:
        interrupt_handler.kill_download = True
        console.print("\n[bold yellow]First interrupt received. Download will complete and save. Press Ctrl+C three times quickly to force quit.[/bold yellow]")
    
    elif interrupt_handler.interrupt_count >= 3:
        interrupt_handler.force_quit = True
        console.print("\n[bold red]Force quit activated. Saving partial download...[/bold red]")
        signal.signal(signum, original_handler)


def MP4_downloader(url: str, path: str, referer: str = None, headers_: dict = None):
    """
    Downloads an MP4 video with enhanced interrupt handling.
    - Single Ctrl+C: Completes download gracefully
    - Triple Ctrl+C: Saves partial download and exits
    """
    if TELEGRAM_BOT:
        bot = get_bot_instance()
        console.log("####")

    path = os_manager.get_sanitize_path(path)
    if os.path.exists(path):
        console.log("[red]Output file already exists.")
        if TELEGRAM_BOT:
            bot.send_message("Contenuto già scaricato!", None)
        return None, False

    if not (url.lower().startswith('http://') or url.lower().startswith('https://')):
        logging.error(f"Invalid URL: {url}")
        console.print(f"[bold red]Invalid URL: {url}[/bold red]")
        return None, False

    # Set headers
    headers = {}
    if referer:
        headers['Referer'] = referer
    
    if headers_:
        headers.update(headers_)
    else:
        headers['User-Agent'] = get_userAgent()

    # Set interrupt handler
    temp_path = f"{path}.temp"
    interrupt_handler = InterruptHandler()
    original_handler = signal.signal(signal.SIGINT, partial(signal_handler, interrupt_handler=interrupt_handler, original_handler=signal.getsignal(signal.SIGINT)))

    # Ensure the output directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)

    try:
        # Use unified HTTP client (verify/timeout/proxy from config)
        with create_client() as client:
            with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                total = int(response.headers.get('content-length', 0))
                
                if total == 0:
                    console.print("[bold red]No video stream found.[/bold red]")
                    return None, False

                # Create a fancy progress bar
                progress_bar = tqdm(
                    total=total,
                    ascii='░▒█',
                    bar_format=f"{Colors.YELLOW}[MP4]{Colors.WHITE}: "
                               f"{Colors.RED}{{percentage:.2f}}% {Colors.MAGENTA}{{bar}} {Colors.WHITE}[ "
                               f"{Colors.YELLOW}{{n_fmt}}{Colors.WHITE} / {Colors.RED}{{total_fmt}} {Colors.WHITE}] "
                               f"{Colors.YELLOW}{{elapsed}} {Colors.WHITE}< {Colors.CYAN}{{remaining}}{Colors.WHITE}, "
                               f"{Colors.YELLOW}{{rate_fmt}}{{postfix}} ",
                    unit='iB',
                    unit_scale=True,
                    desc='Downloading',
                    mininterval=0.05,
                    file=sys.stdout                         # Using file=sys.stdout to force in-place updates because sys.stderr may not support carriage returns in this environment.  
                )

                downloaded = 0
                with open(temp_path, 'wb') as file, progress_bar as bar:
                    try:
                        for chunk in response.iter_bytes(chunk_size=1024):
                            if interrupt_handler.force_quit:
                                console.print("\n[bold red]Force quitting... Saving partial download.[/bold red]")
                                break
                            
                            if chunk:
                                size = file.write(chunk)
                                downloaded += size
                                bar.update(size)

                    except KeyboardInterrupt:
                        if not interrupt_handler.force_quit:
                            interrupt_handler.kill_download = True
                    
        if os.path.exists(temp_path):
            os.rename(temp_path, path)

        if os.path.exists(path):
            console.print(Panel(
                f"[bold green]Download completed{' (Partial)' if interrupt_handler.force_quit else ''}![/bold green]\n"
                f"[cyan]File size: [bold red]{internet_manager.format_file_size(os.path.getsize(path))}[/bold red]\n"
                f"[cyan]Duration: [bold]{print_duration_table(path, description=False, return_string=True)}[/bold]", 
                title=f"{os.path.basename(path.replace('.mp4', ''))}", 
                border_style="green"
            ))

            if TELEGRAM_BOT:
                message = f"Download completato{'(Parziale)' if interrupt_handler.force_quit else ''}\nDimensione: {internet_manager.format_file_size(os.path.getsize(path))}\nDurata: {print_duration_table(path, description=False, return_string=True)}\nTitolo: {os.path.basename(path.replace('.mp4', ''))}"
                clean_message = re.sub(r'\[[a-zA-Z]+\]', '', message)
                bot.send_message(clean_message, None)

            return path, interrupt_handler.kill_download
        
        else:
            console.print("[bold red]Download failed or file is empty.[/bold red]")
            return None, interrupt_handler.kill_download

    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        console.print(f"[bold red]Unexpected Error: {e}[/bold red]")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return None, interrupt_handler.kill_download
    
    finally:
        signal.signal(signal.SIGINT, original_handler)
