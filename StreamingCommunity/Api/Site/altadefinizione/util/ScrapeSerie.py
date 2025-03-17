# 16.03.25

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
    def __init__(self, url):
        """
        Initialize the GetSerieInfo class for scraping TV series information.
        
        Args:
            - url (str): The URL of the streaming site.
        """
        self.headers = {'user-agent': get_userAgent()}
        self.url = url
        self.seasons_manager = SeasonManager()

    def collect_season(self) -> None:
        """
        Retrieve all episodes for all seasons
        """
        response = httpx.get(self.url, headers=self.headers)
        soup = BeautifulSoup(response.text, "html.parser")
        self.series_name = soup.find("title").get_text(strip=True).split(" - ")[0]

        # Process all seasons
        season_items = soup.find_all('div', class_='accordion-item')
    
        for season_idx, season_item in enumerate(season_items, 1):
            season_header = season_item.find('div', class_='accordion-header')
            if not season_header:
                continue
                
            season_name = season_header.get_text(strip=True)
            
            # Create a new season and get a reference to it
            current_season = self.seasons_manager.add_season({
                'number': season_idx, 
                'name': season_name
            })
            
            # Find episodes for this season
            episode_divs = season_item.find_all('div', class_='down-episode')
            for ep_idx, ep_div in enumerate(episode_divs, 1):
                episode_name_tag = ep_div.find('b')
                if not episode_name_tag:
                    continue
                    
                episode_name = episode_name_tag.get_text(strip=True)
                link_tag = ep_div.find('a', string=lambda text: text and "Supervideo" in text)
                episode_url = link_tag['href'] if link_tag else None
                
                # Add episode to the season
                if current_season:
                    current_season.episodes.add({
                        'number': ep_idx,
                        'name': episode_name,
                        'url': episode_url
                    })