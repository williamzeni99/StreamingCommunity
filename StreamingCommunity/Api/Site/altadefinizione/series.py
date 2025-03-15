# 3.12.23

import os
from typing import Tuple


# External library
from rich.console import Console
from rich.prompt import Prompt


# Internal utilities
from StreamingCommunity.Util.message import start_message
from StreamingCommunity.Lib.Downloader import HLS_Downloader

# Logic class
from .util.ScrapeSerie import GetSerieInfo
from StreamingCommunity.Api.Template.Util import (
    manage_selection, 
    map_episode_title, 
    dynamic_format_number, 
    validate_selection, 
    validate_episode_selection, 
    display_episodes_list
)
from StreamingCommunity.Api.Template.config_loader import site_constant
from StreamingCommunity.Api.Template.Class.SearchType import MediaItem


# Player
from StreamingCommunity.Api.Player.supervideo import VideoSource


# Variable
msg = Prompt()
console = Console()


def download_video(index_season_selected: int, index_episode_selected: int, scrape_serie: GetSerieInfo) -> Tuple[str,bool]:
    """
    Download a single episode video.

    Parameters:
        - index_season_selected (int): Index of the selected season.
        - index_episode_selected (int): Index of the selected episode.

    Return:
        - str: output path
        - bool: kill handler status
    """
    start_message()
    index_season_selected = dynamic_format_number(str(index_season_selected))

    # Get info about episode
    obj_episode = scrape_serie.seasons_manager.get_season_by_number(int(index_season_selected)).episodes.get(index_episode_selected-1)
    console.print(f"[yellow]Download: [red]{index_season_selected}:{index_episode_selected} {obj_episode.name}")
    print()

    # Define filename and path for the downloaded video
    mp4_name = f"{map_episode_title(scrape_serie.serie_name, index_season_selected, index_episode_selected, obj_episode.name)}.mp4"
    mp4_path = os.path.join(site_constant.SERIES_FOLDER, scrape_serie.serie_name, f"S{index_season_selected}")

    # Retrieve scws and if available master playlist
    video_source = VideoSource(obj_episode.url)
    video_source.make_request(obj_episode.url)
    master_playlist = video_source.get_playlist()

    # Download the episode
    r_proc = HLS_Downloader(
        m3u8_url=master_playlist,
        output_path=os.path.join(mp4_path, mp4_name)
    ).start()

    if r_proc['error'] is not None:
        try: os.remove(r_proc['path'])
        except: pass

    return r_proc['path'], r_proc['stopped']
    

def download_episode(index_season_selected: int, scrape_serie: GetSerieInfo, download_all: bool = False) -> None:
    """
    Download episodes of a selected season.

    Parameters:
        - index_season_selected (int): Index of the selected season.
        - download_all (bool): Download all episodes in the season.
    """
    start_message()
    obj_episodes = scrape_serie.seasons_manager.get_season_by_number(index_season_selected).episodes
    episodes_count = len(obj_episodes.episodes)

    if download_all:

        # Download all episodes without asking
        for i_episode in range(1, episodes_count + 1):
            path, stopped = download_video(index_season_selected, i_episode, scrape_serie)

            if stopped:
                break

        console.print(f"\n[red]End downloaded [yellow]season: [red]{index_season_selected}.")

    else:

        # Display episodes list and manage user selection
        last_command = display_episodes_list(obj_episodes.episodes)
        list_episode_select = manage_selection(last_command, episodes_count)

        try:
            list_episode_select = validate_episode_selection(list_episode_select, episodes_count)
        except ValueError as e:
            console.print(f"[red]{str(e)}")
            return

        # Download selected episodes if not stopped
        for i_episode in list_episode_select:
            path, stopped = download_video(index_season_selected, i_episode, scrape_serie)

            if stopped:
                break

def download_series(select_season: MediaItem) -> None:
    """
    Download episodes of a TV series based on user selection.

    Parameters:
        - select_season (MediaItem): Selected media item (TV series).
    """
    start_message()

    # Init class
    scrape_serie = GetSerieInfo(select_season.url)

    # Collect information about seasons
    scrape_serie.collect_season()
    seasons_count = len(scrape_serie.seasons_manager)

    # Prompt user for season selection and download episodes
    console.print(f"\n[green]Seasons found: [red]{seasons_count}")
    index_season_selected = msg.ask(
        "\n[cyan]Insert season number [yellow](e.g., 1), [red]* [cyan]to download all seasons, "
        "[yellow](e.g., 1-2) [cyan]for a range of seasons, or [yellow](e.g., 3-*) [cyan]to download from a specific season to the end"
    )

    # Manage and validate the selection
    list_season_select = manage_selection(index_season_selected, seasons_count)

    try:
        list_season_select = validate_selection(list_season_select, seasons_count)
    except ValueError as e:
        console.print(f"[red]{str(e)}")
        return
    
    # Loop through the selected seasons and download episodes
    for i_season in list_season_select:
        if len(list_season_select) > 1 or index_season_selected == "*":

            # Download all episodes if multiple seasons are selected or if '*' is used
            download_episode(i_season, scrape_serie, download_all=True)
        else:

            # Otherwise, let the user select specific episodes for the single season
            download_episode(i_season, scrape_serie, download_all=False)