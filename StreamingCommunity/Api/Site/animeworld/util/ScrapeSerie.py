# 21.03.25


# External libraries
import httpx
from bs4 import BeautifulSoup

# Internal utilities
from StreamingCommunity.Util.headers import get_userAgent
from StreamingCommunity.Util.config_json import config_manager


# Player
from ..site import get_session_and_csrf
from StreamingCommunity.Api.Player.sweetpixel import AnimeWorldPlayer


# Variable
max_timeout = config_manager.get_int("REQUESTS", "timeout")



class ScrapSerie:
    def __init__(self, url, full_url):
        """Initialize the ScrapSerie object with the provided URL and setup the HTTP client."""
        self.url = url
        self.link = httpx.URL(url).path 
        self.session_id, self.csrf_token = get_session_and_csrf()
        self.client = httpx.Client(
            cookies={"sessionId": self.session_id},
            headers={"User-Agent": get_userAgent(), "csrf-token": self.csrf_token},
            base_url=full_url
        )

    def get_name(self):
        """Extract and return the name of the anime series."""
        response = self.client.get(self.link, follow_redirects=True)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            return soup.find("h1", {"id": "anime-title"}).get_text()
        else:
            raise Exception(f"Failed to retrieve anime name. Status code: {response.status_code}")

    def get_episodes(self, nums=None):
        """Fetch and return the list of episodes, optionally filtering by specific episode numbers."""
        response = self.client.get(self.link, follow_redirects=True)
        if response.status_code != 200:
            raise Exception(f"Failed to retrieve episodes. Status code: {response.status_code}")

        soup = BeautifulSoup(response.content.decode('utf-8', 'ignore'), "html.parser")

        raw_eps = {}
        for data in soup.select('li.episode > a'):
            epNum = data.get('data-episode-num')
            epID = data.get('data-episode-id')

            if nums and epNum not in nums:
                continue

            if epID not in raw_eps:
                raw_eps[epID] = {
                    'number': epNum,
                    'link': f"/api/download/{epID}"
                }

        episodes = [episode_data for episode_data in raw_eps.values()]
        return episodes

    def get_episode(self, index):
        """Fetch a specific episode based on the index, and return an AnimeWorldPlayer instance."""
        episodes = self.get_episodes()
        
        if 0 <= index < len(episodes):
            episode_data = episodes[index]
            return AnimeWorldPlayer(episode_data, self.session_id, self.csrf_token)
        
        else:
            raise IndexError("Episode index out of range")
