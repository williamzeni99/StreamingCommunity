# 21.03.25

import logging

# External libraries
import httpx
from bs4 import BeautifulSoup
from rich.console import Console


# Internal utilities
from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Util.headers import get_userAgent, get_headers
from StreamingCommunity.Util.table import TVShowManager


# Logic class
from StreamingCommunity.Api.Template.config_loader import site_constant
from StreamingCommunity.Api.Template.Class.SearchType import MediaManager


# Variable
console = Console()
media_search_manager = MediaManager()
table_show_manager = TVShowManager()
max_timeout = config_manager.get_int("REQUESTS", "timeout")


def get_session_and_csrf() -> dict:
    """
    Get the session ID and CSRF token from the website's cookies and HTML meta data.
    """
    # Send an initial GET request to the website
    response = httpx.get(site_constant.FULL_URL, headers=get_headers())

    # Extract the sessionId from the cookies
    session_id = response.cookies.get('sessionId')
    logging.info(f"Session ID: {session_id}")

    # Use BeautifulSoup to parse the HTML and extract the CSRF-Token
    soup = BeautifulSoup(response.text, 'html.parser')

    # Try to find the CSRF token in a meta tag or hidden input
    csrf_token = None
    meta_tag = soup.find('meta', {'name': 'csrf-token'})
    if meta_tag:
        csrf_token = meta_tag.get('content')

    # If it's not in the meta tag, check for hidden input fields
    if not csrf_token:
        input_tag = soup.find('input', {'name': '_csrf'})
        if input_tag:
            csrf_token = input_tag.get('value')

    logging.info(f"CSRF Token: {csrf_token}")
    return session_id, csrf_token

def title_search(title: str) -> int:
    """
    Function to perform an anime search using a provided title.

    Parameters:
        - title_search (str): The title to search for.

    Returns:
        - int: A number containing the length of media search manager.
    """
    session_id, csrf_token = get_session_and_csrf()
    url = f"{site_constant.FULL_URL}/api/search/v2"

    # Set up the headers, params for the request
    headers = {
        'User-Agent': get_userAgent(),
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'CSRF-Token': csrf_token,
        'X-Requested-With': 'XMLHttpRequest'
    }
    params = {
        'keyword': title,
    }

    # Make the POST request
    response = httpx.post(url, params=params, cookies={'sessionId': session_id}, headers=headers)
    
    for dict_title in response.json()['animes']:
        try:

            media_search_manager.add_media({
                'id': dict_title.get('id'),
                'name': dict_title.get('name'),
                'type': 'TV',
                'status': dict_title.get('stateName'),
                'episodes_count': dict_title.get('episodes'),
                'plot': ' '.join((words := str(dict_title.get('story', '')).split())[:10]) + ('...' if len(words) > 10 else ''),
                'url': f"{site_constant.FULL_URL}/play/{dict_title.get('link')}.{dict_title.get('identifier')}"
            })

        except Exception as e:
            print(f"Error parsing a film entry: {e}")

    # Return the length of media search manager
    return media_search_manager.get_length()