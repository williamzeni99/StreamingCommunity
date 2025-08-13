# 01.03.24

import json
import logging


# External libraries
import httpx
from bs4 import BeautifulSoup


# Internal utilities
from StreamingCommunity.Util.headers import get_userAgent
from StreamingCommunity.Util.config_json import config_manager
from StreamingCommunity.Api.Player.Helper.Vixcloud.util import SeasonManager


# Variable
max_timeout = config_manager.get_int("REQUESTS", "timeout")


class GetSerieInfo:
    def __init__(self, url, media_id: int = None, series_name: str = None):
        """
        Initialize the GetSerieInfo class for scraping TV series information.
        
        Args:
            - url (str): The URL of the streaming site.
            - media_id (int, optional): Unique identifier for the media
            - series_name (str, optional): Name of the TV series
        """
        self.is_series = False
        self.headers = {'user-agent': get_userAgent()}
        self.url = url
        self.media_id = media_id
        self.seasons_manager = SeasonManager()

        if series_name is not None:
            self.is_series = True
            self.series_name = series_name

    def collect_info_title(self) -> None:
        """
        Retrieve general information about the TV series from the streaming site.
        
        Raises:
            Exception: If there's an error fetching series information
        """
        try:
            response = httpx.get(
                url=f"{self.url}/titles/{self.media_id}-{self.series_name}",
                headers=self.headers,
                timeout=max_timeout
            )
            response.raise_for_status()

            # Extract series info from JSON response
            soup = BeautifulSoup(response.text, "html.parser")
            json_response = json.loads(soup.find("div", {"id": "app"}).get("data-page"))
            self.version = json_response['version']
            
            # Extract information about available seasons
            title_data = json_response.get("props", {}).get("title", {})
            
            # Save general series information
            self.title_info = title_data
            
            # Extract available seasons and add them to SeasonManager
            seasons_data = title_data.get("seasons", [])
            for season_data in seasons_data:
                self.seasons_manager.add_season({
                    'id': season_data.get('id', 0),
                    'number': season_data.get('number', 0),
                    'name': f"Season {season_data.get('number', 0)}",
                    'slug': season_data.get('slug', ''),
                    'type': title_data.get('type', '')
                })

        except Exception as e:
            logging.error(f"Error collecting series info: {e}")
            raise

    def collect_info_season(self, number_season: int) -> None:
        """
        Retrieve episode information for a specific season.
        
        Args:
            number_season (int): Season number to fetch episodes for
        
        Raises:
            Exception: If there's an error fetching episode information
        """
        try:
            # Get the season object from SeasonManager
            season = self.seasons_manager.get_season_by_number(number_season)
            if not season:
                logging.error(f"Season {number_season} not found")
                return
            
            response = httpx.get(
                url=f'{self.url}/titles/{self.media_id}-{self.series_name}/season-{number_season}', 
                headers={
                    'User-Agent': self.headers['user-agent'],
                    'x-inertia': 'true',
                    'x-inertia-version': self.version,
                },
                timeout=max_timeout
            )

            # Extract episodes from JSON response
            json_response = response.json().get('props', {}).get('loadedSeason', {}).get('episodes', [])
                
            # Add each episode to the corresponding season's episode manager
            for dict_episode in json_response:
                season.episodes.add(dict_episode)

        except Exception as e:
            logging.error(f"Error collecting episodes for season {number_season}: {e}")
            raise

    # ------------- FOR GUI -------------
    def getNumberSeason(self) -> int:
        """
        Get the total number of seasons available for the series.
        """
        if not self.seasons_manager.seasons:
            self.collect_info_title()
            
        return len(self.seasons_manager.seasons)
    
    def getEpisodeSeasons(self, season_number: int) -> list:
        """
        Get all episodes for a specific season.
        """
        season = self.seasons_manager.get_season_by_number(season_number)

        if not season:
            logging.error(f"Season {season_number} not found")
            return []
            
        if not season.episodes.episodes:
            self.collect_info_season(season_number)
            
        return season.episodes.episodes
        
    def selectEpisode(self, season_number: int, episode_index: int) -> dict:
        """
        Get information for a specific episode in a specific season.
        """
        episodes = self.getEpisodeSeasons(season_number)
        if not episodes or episode_index < 0 or episode_index >= len(episodes):
            logging.error(f"Episode index {episode_index} is out of range for season {season_number}")
            return None
            
        return episodes[episode_index]