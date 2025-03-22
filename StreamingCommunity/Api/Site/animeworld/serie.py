# 11.03.24

import os
import logging
from typing import Tuple


# External library
from rich.console import Console
from rich.prompt import Prompt


# Internal utilities
from StreamingCommunity.Util.os import os_manager
from StreamingCommunity.Util.message import start_message
from StreamingCommunity.Lib.Downloader import MP4_downloader


# Logic class
from .util.ScrapeSerie import ScrapSerie
from StreamingCommunity.Api.Template.config_loader import site_constant
from StreamingCommunity.Api.Template.Util import manage_selection, dynamic_format_number, map_episode_title
from StreamingCommunity.Api.Template.Class.SearchType import MediaItem


# Player
from StreamingCommunity.Api.Player.sweetpixel import AnimeWorldPlayer


# Variable
console = Console()
msg = Prompt()
KILL_HANDLER = bool(False)



def download_episode(index_select: int, scrape_serie: ScrapSerie, episodes) -> Tuple[str,bool]:
    """
    Downloads the selected episode.

    Parameters:
        - index_select (int): Index of the episode to download.

    Return:
        - str: output path
        - bool: kill handler status
    """
    start_message()

    # Get information about the selected episode
    console.print(f"[bold yellow]Download:[/bold yellow] [red]{site_constant.SITE_NAME}[/red] ([cyan]E{index_select+1}[/cyan]) \n")

    # Define filename and path for the downloaded video
    mp4_name = f"{scrape_serie.get_name()}_EP_{dynamic_format_number(str(index_select+1))}.mp4"
    mp4_path = os.path.join(site_constant.ANIME_FOLDER, scrape_serie.get_name())

    # Create output folder
    os_manager.create_path(mp4_path)

    # Collect mp4 link
    video_source = AnimeWorldPlayer(site_constant.FULL_URL, episodes[index_select], scrape_serie.session_id, scrape_serie.csrf_token)
    mp4_link = video_source.get_download_link()

    # Start downloading
    path, kill_handler = MP4_downloader(
        url=str(mp4_link).strip(),
        path=os.path.join(mp4_path, mp4_name)
    )

    return path, kill_handler


def download_series(select_title: MediaItem):
    """
    Function to download episodes of a TV series.

    Parameters:
        - tv_id (int): The ID of the TV series.
        - tv_name (str): The name of the TV series.
    """
    start_message()

    scrape_serie = ScrapSerie(select_title.url, site_constant.FULL_URL)

    # Get the count of episodes for the TV series
    episodes = scrape_serie.get_episodes()
    episoded_count = len(episodes)
    console.print(f"[cyan]Episodes find: [red]{episoded_count}")

    # Prompt user to select an episode index
    last_command = msg.ask("\n[cyan]Insert media [red]index [yellow]or [red]* [cyan]to download all media [yellow]or [red]1-2 [cyan]or [red]3-* [cyan]for a range of media")

    # Manage user selection
    list_episode_select = manage_selection(last_command, episoded_count)

    # Download selected episodes
    if len(list_episode_select) == 1 and last_command != "*":
        path, _ = download_episode(list_episode_select[0]-1, scrape_serie, episodes)
        return path

    # Download all other episodes selecter
    else:
        kill_handler = False
        for i_episode in list_episode_select:
            if kill_handler:
                break
            _, kill_handler = download_episode(i_episode-1, scrape_serie, episodes)