# 21.05.24

import os
from typing import Tuple


# External library
from rich.console import Console


# Internal utilities
from StreamingCommunity.Util.os import os_manager, get_wvd_path
from StreamingCommunity.Util.message import start_message
from StreamingCommunity.Util.headers import get_headers


# Logic class
from StreamingCommunity.Api.Template.config_loader import site_constant
from StreamingCommunity.Api.Template.Class.SearchType import MediaItem


# Player
from .util.fix_mpd import get_manifest
from StreamingCommunity import DASH_Downloader
from .util.get_license import get_bearer_token, get_playback_url, get_tracking_info, generate_license_url


# Variable
console = Console()


def download_film(select_title: MediaItem) -> Tuple[str, bool]:
    """
    Downloads a film using the provided film ID, title name, and domain.

    Parameters:
        - select_title (MediaItem): The selected media item.

    Return:
        - str: output path if successful, otherwise None
    """
    start_message()
    console.print(f"[bold yellow]Download:[/bold yellow] [red]{site_constant.SITE_NAME}[/red] → [cyan]{select_title.name}[/cyan] \n")

    # Define the filename and path for the downloaded film
    title_name = os_manager.get_sanitize_file(select_title.name) + ".mp4"
    mp4_path = os.path.join(site_constant.MOVIE_FOLDER, title_name.replace(".mp4", ""))

    # Generate mpd and license URLs
    bearer = get_bearer_token()

    playback_json = get_playback_url(bearer, select_title.id)
    tracking_info = get_tracking_info(bearer, playback_json)[0]

    license_url = generate_license_url(bearer, tracking_info)
    mpd_url = get_manifest(tracking_info['video_src'])

    # Download the episode
    dash_process =  DASH_Downloader(
        cdm_device=get_wvd_path(),
        license_url=license_url,
        mpd_url=mpd_url,
        output_path=mp4_path,
    )
    dash_process.parse_manifest(custom_headers=get_headers())

    if dash_process.download_and_decrypt():
        dash_process.finalize_output()

    # Get final output path and status
    status = dash_process.get_status()

    if status['error'] is not None and status['path']:
        try: 
            os.remove(status['path'])
        except Exception: 
            pass

    return status['path'], status['stopped']