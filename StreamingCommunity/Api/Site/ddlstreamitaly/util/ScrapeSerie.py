# 13.06.24

import sys
import logging
from typing import List, Dict


# External libraries
import httpx
from bs4 import BeautifulSoup


# Internal utilities
from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Util.headers import get_userAgent


# Logic class
from StreamingCommunity.Api.Template.Class.SearchType import MediaItem


# Variable
max_timeout = config_manager.get_int("REQUESTS", "timeout")


class GetSerieInfo:
    def __init__(self, dict_serie: MediaItem, cookies) -> None:
        """
        Initializes the GetSerieInfo object with default values.

        Parameters:
            - dict_serie (MediaItem): Dictionary containing series information (optional).
        """
        self.headers = {'user-agent': get_userAgent()}
        self.cookies = cookies
        self.url = dict_serie.url
        self.tv_name = None
        self.list_episodes = None

    def get_episode_number(self) -> List[Dict[str, str]]:
        """
        Retrieves the number of episodes for a specific season.

        Parameters:
            n_season (int): The season number.

        Returns:
            List[Dict[str, str]]: List of dictionaries containing episode information.
        """
        try:
            response = httpx.get(f"{self.url}?area=online", cookies=self.cookies, headers=self.headers, timeout=max_timeout)
            response.raise_for_status()

        except Exception as e:
            logging.error(f"Insert value for [ips4_device_key, ips4_member_id, ips4_login_key] in config.json file SITE \\ ddlstreamitaly \\ cookie. Use browser debug and cookie request with a valid account, filter by DOC. Error: {e}")
            sys.exit(0)

        # Parse HTML content of the page
        soup = BeautifulSoup(response.text, "html.parser")

        # Get tv name 
        self.tv_name = soup.find("span", class_= "ipsType_break").get_text(strip=True)

        # Find the container of episodes for the specified season
        table_content = soup.find('div', class_='ipsMargin_bottom:half')
        list_dict_episode = []

        for episode_div in table_content.find_all('a', href=True):

            # Get text of episode
            part_name = episode_div.get_text(strip=True)

            if part_name:
                obj_episode = {
                    'name': part_name,
                    'url': episode_div['href']
                }

                list_dict_episode.append(obj_episode)
     
        self.list_episodes = list_dict_episode
        return list_dict_episode
    
    
    # ------------- FOR GUI -------------
    def getNumberSeason(self) -> int:
        """
        Get the total number of seasons available for the series.
        Note: DDLStreamItaly typically provides content organized as threads, not seasons.
        """
        return 1
    
    def getEpisodeSeasons(self, season_number: int = 1) -> list:
        """
        Get all episodes for a specific season.
        Note: For DDLStreamItaly, this returns all episodes as they're typically in one list.
        """     
        if not self.list_episodes:
            self.list_episodes = self.get_episode_number()
            
        return self.list_episodes
        
    def selectEpisode(self, season_number: int = 1, episode_index: int = 0) -> dict:
        """
        Get information for a specific episode.
        """
        episodes = self.getEpisodeSeasons()
        if not episodes or episode_index < 0 or episode_index >= len(episodes):
            logging.error(f"Episode index {episode_index} is out of range")
            return None
            
        return episodes[episode_index]