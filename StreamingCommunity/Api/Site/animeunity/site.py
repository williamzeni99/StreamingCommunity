# 10.12.23

import sys
import logging


# External libraries
import httpx
from bs4 import BeautifulSoup
from rich.console import Console


# Internal utilities
from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Util.headers import get_userAgent
from StreamingCommunity.Util.table import TVShowManager
from StreamingCommunity.TelegramHelp.telegram_bot import get_bot_instance


# Logic class
from StreamingCommunity.Api.Template.config_loader import site_constant
from StreamingCommunity.Api.Template.Class.SearchType import MediaManager


# Variable
console = Console()
media_search_manager = MediaManager()
table_show_manager = TVShowManager()
max_timeout = config_manager.get_int("REQUESTS", "timeout")


def get_token() -> dict:
    """
    Function to retrieve session tokens from a specified website.

    Parameters:
        - site_name (str): The name of the site.
        - domain (str): The domain of the site.

    Returns:
        - dict: A dictionary containing session tokens. The keys are 'XSRF_TOKEN', 'animeunity_session', and 'csrf_token'.
    """
    response = httpx.get(
        url=site_constant.FULL_URL,
        timeout=max_timeout
    )
    response.raise_for_status()

    # Initialize variables to store CSRF token
    find_csrf_token = None
    soup = BeautifulSoup(response.text, "html.parser")
    
    for html_meta in soup.find_all("meta"):
        if html_meta.get('name') == "csrf-token":

            find_csrf_token = html_meta.get('content')

    logging.info(f"Extract: ('animeunity_session': {response.cookies['animeunity_session']}, 'csrf_token': {find_csrf_token})")
    return {
        'animeunity_session': response.cookies['animeunity_session'],
        'csrf_token': find_csrf_token
    }


def get_real_title(record):
    """
    Get the real title from a record.

    This function takes a record, which is assumed to be a dictionary representing a row of JSON data.
    It looks for a title in the record, prioritizing English over Italian titles if available.
    
    Parameters:
        - record (dict): A dictionary representing a row of JSON data.
    
    Returns:
        - str: The title found in the record. If no title is found, returns None.
    """
    if record['title_eng'] is not None:
        return record['title_eng']
    elif record['title'] is not None:
        return record['title']
    else:
        return record['title_it']


def title_search(title: str) -> int:
    """
    Function to perform an anime search using a provided title.

    Parameters:
        - title_search (str): The title to search for.

    Returns:
        - int: A number containing the length of media search manager.
    """
    if site_constant.TELEGRAM_BOT:  
        bot = get_bot_instance()
    
    media_search_manager.clear()
    table_show_manager.clear()

    # Create parameter for request
    data = get_token()
    cookies = {'animeunity_session': data.get('animeunity_session')}
    headers = {
        'user-agent': get_userAgent(),
        'x-csrf-token': data.get('csrf_token')
    }
    json_data =  {'title': title}

    # Send a POST request to the API endpoint for live search
    try:
        response = httpx.post(
            f'{site_constant.FULL_URL}/livesearch', 
            cookies=cookies, 
            headers=headers, 
            json=json_data,
            timeout=max_timeout
        )
        response.raise_for_status()

    except Exception as e:
        console.print(f"Site: {site_constant.SITE_NAME}, request search error: {e}")
        return 0

    # Inizializza la lista delle scelte
    if site_constant.TELEGRAM_BOT:
        choices = []

    for dict_title in response.json()['records']:
        try:

            # Rename keys for consistency
            dict_title['name'] = get_real_title(dict_title)

            media_search_manager.add_media({
                'id': dict_title.get('id'),
                'slug': dict_title.get('slug'),
                'name': dict_title.get('name'),
                'type': dict_title.get('type'),
                'status': dict_title.get('status'),
                'episodes_count': dict_title.get('episodes_count'),
                'plot': ' '.join((words := str(dict_title.get('plot', '')).split())[:10]) + ('...' if len(words) > 10 else '')
            })

            if site_constant.TELEGRAM_BOT:
                
                # Crea una stringa formattata per ogni scelta con numero
                choice_text = f"{len(choices)} - {dict_title.get('name')} ({dict_title.get('type')}) - Episodi: {dict_title.get('episodes_count')}"
                choices.append(choice_text)

        except Exception as e:
            print(f"Error parsing a film entry: {e}")

    if site_constant.TELEGRAM_BOT:
        if choices:
            bot.send_message(f"Lista dei risultati:", choices)

    # Return the length of media search manager
    return media_search_manager.get_length()