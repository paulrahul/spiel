import requests
import json
import os
import re

from bs4 import BeautifulSoup

from log import get_logger
import util

logger = get_logger()

SCRAPES_FOLDER_NAME = "scrapes"
SCRAPE_FILE_SUFFIX = "_json_ld.txt"

class Crawler:
    def __init__(self):
        curr_dir = os.path.dirname(os.path.abspath(__file__))     
        self._folder_scrapes_path = os.path.join(curr_dir, SCRAPES_FOLDER_NAME)
        if not os.path.exists(self._folder_scrapes_path):
            os.makedirs(self._folder_scrapes_path)
            
    def _dump_file_name(self, word):
        return os.path.join(self._folder_scrapes_path, word + SCRAPE_FILE_SUFFIX)

    def existing_crawl_words(self):
        return sorted(
            file_name[:-len(SCRAPE_FILE_SUFFIX)]
            for file_name in os.listdir(self._folder_scrapes_path)
            if file_name.endswith(SCRAPE_FILE_SUFFIX)
        )
        
    def crawl_file_exists(self, word):
        file_name = self._dump_file_name(word)
        return util.file_exists(file_name)
        
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
        grammar = self._extract_grammar(soup)

        # Step 3: Find JSON-LD script tag
        script_tags = soup.find_all('script', type='application/ld+json')

        if len(script_tags) < 2:
            logger.error(f"Found {len(script_tags)} in {url}")
            return None
        
        logger.debug(f"JSON+LD tags found for {word}: {script_tags}")

        # Step 4: Extract and Parse JSON Data
        try:
            json_data = json.loads(script_tags[1].string)

            # Keep the scrape format as a list so existing parsers remain
            # compatible, while retaining grammar that is not in the JSON-LD.
            if grammar and isinstance(json_data, list):
                json_data.append({"grammar": grammar})
            elif grammar and isinstance(json_data, dict):
                json_data["grammar"] = grammar
            
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

    def backfill_grammar(self, word):
        """Refresh only the grammar stored in an existing scrape file.

        Returns the extracted grammar (which may be empty when DWDS has no
        grammar block), or None when fetching/parsing failed.
        """
        file_name = self._dump_file_name(word)
        if not util.file_exists(file_name):
            logger.error(f"No existing scrape file found for {word}")
            return None

        url = self._dwds_url(word)
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Fetching grammar from {url} failed: {e}")
            return None

        grammar = self._extract_grammar(
            BeautifulSoup(response.text, 'html.parser'))

        try:
            with open(file_name, 'r') as file:
                scrape_contents = json.load(file)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Reading scrape file {file_name} failed: {e}")
            return None

        if isinstance(scrape_contents, list):
            grammar_entries = [
                item for item in scrape_contents
                if isinstance(item, dict) and "grammar" in item
            ]
            if grammar_entries:
                grammar_entries[0]["grammar"] = grammar
                for duplicate in grammar_entries[1:]:
                    scrape_contents.remove(duplicate)
            else:
                scrape_contents.append({"grammar": grammar})
        elif isinstance(scrape_contents, dict):
            scrape_contents["grammar"] = grammar
        else:
            logger.error(f"Unexpected scrape format in {file_name}")
            return None

        try:
            with open(file_name, 'w') as file:
                json.dump(scrape_contents, file)
        except OSError as e:
            logger.error(f"Writing scrape file {file_name} failed: {e}")
            return None

        return grammar

    @staticmethod
    def _extract_grammar(soup):
        for block in soup.select("div.dwdswb-ft-block"):
            label = block.select_one(".dwdswb-ft-blocklabel")
            if label is None or label.get_text(strip=True) != "Grammatik":
                continue

            block_text = block.select_one(".dwdswb-ft-blocktext")
            if block_text is None:
                return ""

            # Preserve DWDS's emphasis as Markdown, but discard all links and
            # other presentation markup by extracting only the resulting text.
            for bold in block_text.find_all("b"):
                bold.replace_with(f"**{bold.get_text(strip=True)}**")

            return re.sub(r"\s+", " ", block_text.get_text()).strip()

        return ""

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
