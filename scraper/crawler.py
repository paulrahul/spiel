import requests
import json
import os

from bs4 import BeautifulSoup

from log import get_logger
import util

logger = get_logger()

SCRAPES_FOLDER_NAME = "scrapes"

class Crawler:
    def __init__(self):
        curr_dir = os.path.dirname(os.path.abspath(__file__))     
        self._folder_scrapes_path = os.path.join(curr_dir, SCRAPES_FOLDER_NAME)
        if not os.path.exists(self._folder_scrapes_path):
            os.makedirs(self._folder_scrapes_path)
            
    def _dump_file_name(self, word):
        return self._folder_scrapes_path + "/" + word + "_json_ld.txt"
        
    def crawl(self, word):
        pass

class DWDSCrawler(Crawler):
    DWDS_URL_PREFIX = "https://www.dwds.de/wb/"
    
    def crawl(self, word):
        file_name = self._dump_file_name(word)
        if util.file_exists(file_name):
            logger.debug(f"Scrape file for {word} already present.")
            return file_name
         
        # Step 1: Make HTTP Request
        url = DWDSCrawler._dwds_url(word)
        response = requests.get(url)

        if response.status_code != 200:
            logger.error(f"Got return code {response.status_code} in {url}")
            return None
            
        # Step 2: Parse HTML Content
        soup = BeautifulSoup(response.text, 'html.parser')

        # Step 3: Find JSON-LD script tag
        script_tags = soup.find_all('script', type='application/ld+json')

        if len(script_tags) != 2:
            logger.error(f"Found {len(script_tags)} in {url}")
            return None
        
        logger.debug(f"JSON+LD tags found for {word}: {script_tags}")

        # Step 4: Extract and Parse JSON Data
        try:
            json_data = json.loads(script_tags[1].string)
            
            # Write json data to dump file
            with open(file_name, 'w') as file:
                json.dump(json_data, file)
            
            # Step 5: Extract Relevant Information
            # Modify this part based on the structure of the JSON data
            # title = json_data['name']
            # description = json_data['description']

            # print("Title:", title)
            # print("Description:", description)
            
            return file_name

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON in {url}:", e)

    @classmethod
    def _dwds_url(cls, word):
        return cls.DWDS_URL_PREFIX + word

class CrawlerFactory:
    @classmethod
    def get_crawler(cls, crawler_source):
        if crawler_source.lower() == "dwds":
            return DWDSCrawler()
        else:
            raise ValueError(f"Invalid translator source type {crawler_source}")
