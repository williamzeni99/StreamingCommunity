# 10.12.23


# External libraries
import httpx
from bs4 import BeautifulSoup
from rich.console import Console


# Internal utilities
from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Util.headers import get_userAgent
from StreamingCommunity.Util.table import TVShowManager


# Logic class
from StreamingCommunity.Api.Template.config_loader import site_constant
from StreamingCommunity.Api.Template.Class.SearchType import MediaManager


# Variable
console = Console()
media_search_manager = MediaManager()
table_show_manager = TVShowManager()
max_timeout = config_manager.get_int("REQUESTS", "timeout")


def title_search(title_search: str) -> int:
    """
    Search for titles based on a search query.
      
    Parameters:
        - title_search (str): The title to search for.

    Returns:
        int: The number of titles found.
    """
    media_search_manager.clear()
    table_show_manager.clear()

    search_url = f"{site_constant.FULL_URL}/?story={title_search}&do=search&subaction=search"
    console.print(f"[cyan]Search url: [yellow]{search_url}")

    try:
        response = httpx.post(search_url, headers={'user-agent': get_userAgent()}, timeout=max_timeout, follow_redirects=True)
        response.raise_for_status()

    except Exception as e:
        console.print(f"Site: {site_constant.SITE_NAME}, request search error: {e}")
        return 0
    
    # Create soup istance
    soup = BeautifulSoup(response.text, "html.parser")

    # Collect data from soup
    for movie_div in soup.find_all("div", class_="movie"):
        
        title_tag = movie_div.find("h2", class_="movie-title")
        title = title_tag.find("a").get_text(strip=True)
        url = title_tag.find("a").get("href")

        # Define typo
        if "/serie-tv/" in url:
            tipo = "tv"
        else:
            tipo = "film"

        media_search_manager.add_media({
            'url': url,
            'name': title,
            'type': tipo
        })
	
    # Return the number of titles found
    return media_search_manager.get_length()