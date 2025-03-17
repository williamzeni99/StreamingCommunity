# 26.05.24

from urllib.parse import quote_plus


# External library
from rich.console import Console
from rich.prompt import Prompt


# Internal utilities
from StreamingCommunity.Api.Template.config_loader import site_constant
from StreamingCommunity.Api.Template.Class.SearchType import MediaItem
from StreamingCommunity.Lib.TMBD import tmdb, Json_film


# Logic class
from .film import download_film


# Variable
indice = 7
_useFor = "film"
_deprecate = False
_priority = 2
_engineDownload = "hls"

msg = Prompt()
console = Console()


def process_search_result(select_title):
    """
    Handles the search result and initiates the download for either a film or series.
    """
    download_film(select_title)


def search(string_to_search: str = None, get_onlyDatabase: bool = False, direct_item: dict = None):
    """
    Main function of the application for search film, series and anime.

    Parameters:
        string_to_search (str, optional): String to search for
        get_onylDatabase (bool, optional): If True, return only the database object
        direct_item (dict, optional): Direct item to process (bypass search)
    """
    if direct_item:
        select_title = MediaItem(**direct_item)
        process_search_result(select_title)
        return

    if string_to_search is None:
        string_to_search = msg.ask(f"\n[purple]Insert word to search in [green]{site_constant.SITE_NAME}").strip()

    # Not available for the moment
    if get_onlyDatabase:
        return 0

    # Search on database
    movie_id = tmdb.search_movie(quote_plus(string_to_search))

    if movie_id is not None:
        movie_details: Json_film = tmdb.get_movie_details(tmdb_id=movie_id)

        # Download only film
        download_film(movie_details)

    else:

        # If no results are found, ask again
        console.print(f"\n[red]Nothing matching was found for[white]: [purple]{string_to_search}")
        search()