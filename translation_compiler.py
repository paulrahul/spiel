import gevent
from gevent import monkey
monkey.patch_all()

from functools import partial
import json
import os
import queue
import threading
import traceback

import gspread

from log import get_logger
from scraper.crawler import CrawlerFactory
from scraper.parser import ParserFactory
from scraper.translator import TranslatorFactory
import util

DUMP_FILE_NAME =  "_dump.txt"
SCRAPE_QUEUE_FILE_NAME = "_scrape_queue.txt"
INCORRECT_WORDS_FILE_NAME = "_to_be_fixed.txt"

DEEPL_KEY_VAR = "DEEPL_KEY"

logger = get_logger()

class Compiler:
    def __init__(self, translator_api_key):
        logger.info("Starting Compiler...")
        
        self._worksheet = None
        
        self._entries = None
        self._gs_entries = None
        
        self._crawler = CrawlerFactory.get_crawler("dwds")
        self._translator = TranslatorFactory.get_translator("deepl", translator_api_key)
        self._parser = ParserFactory.get_parser("dwds")
                      
    def compile(self, reload=False):
        # Step 1. Read word list.
        fetched = self._fetch_glossary(fetch_from_google_sheet=reload)
        if not fetched:
            logger.critical("Fetching glossary failed", exc_info=1) 
        
        # Step 2. Build scrape list.
        if reload or not util.file_exists(SCRAPE_QUEUE_FILE_NAME):
            self._prepare_for_scrape()
        
        # Step 3. Scrape.
        self._scrape_and_translate()
        
        # Step 5.
        self._cleanup()
                
    def _cleanup(self):
        _delete_file(SCRAPE_QUEUE_FILE_NAME)
        
    def _scrape_de_to_en(self, word):
        return self._crawler.crawl(word)
    
    def _translate_de_to_en(self, word):
        return self._translator.translate_from_deutsch(word)
    
    def _translate_en_to_de(self, word):
        return self._translator.translate_from_englisch(word)
        
    def _post_process_scrape(self, scrape_word, scrape_entry, event, source_greenlet):
        k = source_greenlet.name
        v = source_greenlet.value
        scrape_entry[k] = v
        logger.debug(f"Set {k} to {v} for {scrape_word}")
        
        if "translation" in scrape_entry and "file" in scrape_entry:
            logger.debug(f"Both keys set for {scrape_word}")
        
            t = threading.Thread(
                target=self._combine_scrape_data,
                name=scrape_word,
                args=(scrape_word, scrape_entry,))
            t.start()
            t.join()
            
            event.set()
        
    def _combine_scrape_data(self, scrape_word, scrape_entry):
        scrape_entry["examples"] = []
        scrape_entry["metadata"] = []

        scrape_entry["incorrect"] = False
        if scrape_entry['file'] is None:
            scrape_entry["incorrect"] = True
            logger.warning(f"No scrape file for {scrape_word} found")
            return
        
        file_name = scrape_entry['file']
        try:
            with open(file_name, 'r') as file:
                scrape_contents = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"File {file_name} not found for parsing.")
            return 

        examples = self._parser.parse_examples(scrape_contents)
        
        # Invoke greenlets to fetch the translations of the examples.
        greenlets = []
        idx = 0
        for eg in examples:
            g = gevent.spawn(self._translate_de_to_en, eg)
            g.name = str(idx)
            greenlets.append(g)
            idx += 1
            
        greenlets = gevent.joinall(greenlets, timeout=10)
        
        compiled_examples = []
        for g in greenlets:
            idx = int(g.name)
            compiled_examples.append((examples[idx], g.value))
            
        scrape_entry["examples"] = compiled_examples
        
        genus = self._parser.parse_genus(examples, scrape_word)
        scrape_entry["metadata"] = {"genus": genus}
    
    def _scrape_and_translate(self):
        try:
            with open(SCRAPE_QUEUE_FILE_NAME, 'r') as file:                
                to_be_scraped_queue = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"No scrape queue found")
            return

        events = []
        for scrape_word, scrape_entry in to_be_scraped_queue.items():
            if scrape_entry['de_to_en']:
                event = gevent.event.Event()
                events.append(event)
                
                greenlet1 = gevent.spawn(self._scrape_de_to_en, scrape_word)
                greenlet1.name = "file"
                greenlet2 = gevent.spawn(self._translate_de_to_en, scrape_word)
                greenlet2.name = "translation"

                greenlet1.link(partial(
                    self._post_process_scrape, 
                    scrape_word, scrape_entry, event))
                greenlet2.link(partial(
                    self._post_process_scrape,
                    scrape_word, scrape_entry, event))
            else:  # en to de
                # First get the German translation, then do the usual scraping
                # as is done for German words.                
                translation = self._translate_en_to_de(scrape_word)
                scrape_entry["translation"] = translation

                event = gevent.event.Event()
                events.append(event)
                greenlet = gevent.spawn(self._scrape_de_to_en, translation)
                greenlet.name = "file"
                greenlet.link(partial(
                    self._post_process_scrape, 
                    translation, scrape_entry, event))
                
                          
        gevent.wait(events)
        self._dump_metadata(to_be_scraped_queue)
        self._write_translations_to_gs(to_be_scraped_queue)
                
    def _dump_metadata(self, scraped_entries):
        dump_entries = []
        incorrect_words = []
        for word, entry in scraped_entries.items():
            if entry.get("incorrect", False):
                incorrect_words.append(word)
                continue
            
            # if not entry['de_to_en']:
            #     continue
            
            dump_entries.append({
                "word": word,
                "de_to_en": entry["de_to_en"],
                "translation": entry["translation"],
                "examples": entry["examples"],
                "metadata": entry["metadata"]
            })
            
        with open(DUMP_FILE_NAME, 'w') as file:
            logger.debug(f"Dumping all metadata to file.")
            json.dump(dump_entries, file)
            
        if not len(incorrect_words) > 0:            
            with open(INCORRECT_WORDS_FILE_NAME, 'w') as file:
                logger.debug(f"Writing incorrect words to file.")
                json.dump(incorrect_words, file)
                    
    def _prepare_for_scrape(self):  
        if self._gs_entries is None or len(self._gs_entries) == 0:
            logger.debug("No new entries from Google Spreadsheet")
            return
        
        # Schedule scraping for any word in GS not having a translation.
        to_be_scraped_queue = {}
        empty_dump_file = self._entries is None or len(self._entries) == 0
        for row in self._gs_entries:
            if len(row) >= 3 and row[2].strip() != '':
                # Already has a Bedeutung filled in.
                continue
            
            word1 = row[0] if len(row) > 0 and row[0].strip() != '' else None
            word2 = row[1] if len(row) > 1 and row[1].strip() != ''  else None
            
            word = None
            de_to_en = False
            
            if word1 is not None and word2 is not None:
                logger.critical(f"Found an incorrect entry with both words set: " +
                                f"{word1}, {word2}")
                exit(1)

            if word1 is not None and word1 != '':
                word = word1
                de_to_en = True
            else:
                word = word2
            
            if empty_dump_file or word not in self._entries:
                to_be_scraped_queue[word] = {'de_to_en': de_to_en}
                logger.debug(f"To be scraped: {word}, de_to_en={de_to_en}")
    
        if len(to_be_scraped_queue) > 0:
            with open(SCRAPE_QUEUE_FILE_NAME, 'w') as file:
                logger.debug(f"Writing scrape entries")
                json.dump(to_be_scraped_queue, file)
        
    def _fetch_glossary(self, fetch_from_google_sheet=False):
        # 1. Fetch from dump file first.
        # 2. If dump file not found or if fetch_from_google_sheet, then fetch
        #    Google spreadsheet contents.
        
        if fetch_from_google_sheet:
            return self._fetch_from_gsheet()
        
        try:
            # First try to read from a local dump file. Re-read if file is not
            # available or if the file is older than current date.        
            with open(DUMP_FILE_NAME, 'r') as file:                
                logger.debug(f"Loading entries from current dump file.")
                self._entries = json.load(file)
                return True
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read dump file {DUMP_FILE_NAME} due to: {e}")
        
        return False
        
    def _fetch_from_gsheet(self):
        try:
            logger.info(f"Reading Google Spreadsheet file")
            
            # Authenticate with Google Sheets API
            gc = gspread.oauth()

            # Open the spreadsheet by title
            spreadsheet = gc.open('Vokabeln und Phrasen')

            # Select the worksheet by title
            self._worksheet = spreadsheet.worksheet('Sheet1')

            # Get all values from the worksheet
            self._gs_entries = self._worksheet.get_all_values()[1:]
            
            logger.debug(f"Obtained values from GS: {self._gs_entries}")
                
            return True

        except Exception as e:
            # Catch any exception and print its contents
            logger.error(f"Fetching Google sheet failed")
            traceback.print_exc()
            return False
        
    def _write_translations_to_gs(self, scraped_entries):
        if self._worksheet is None:
            logger.critical("Worksheet is not set, this is unexpected.")

        column_to_update = 3  # Bedeutung column

        row_index = 2
        batch_updates = []
        for row in self._gs_entries:            
            if row[0] is not None and row[0] != '':
                word = row[0]
            elif row[1] is not None and row[1] != '':
                word = row[1]
                
            if word not in scraped_entries:
                logger.error(f"No translation found for {word}")
                continue

            entry = scraped_entries[word]
            cell_value = entry["translation"]

            batch_updates.append({
                'range': gspread.utils.rowcol_to_a1(row_index, column_to_update),
                'values': [[cell_value]],
            })
            row_index += 1            
  
        logger.debug(f"Batch updates to be issued: {batch_updates}")
        self._worksheet.batch_update(batch_updates)
        logger.debug("Batch updates completed.")
    
def _delete_file(file_name):
    try:
        os.remove(file_name)
        logger.debug(f"File '{file_name}' deleted successfully.")
    except FileNotFoundError:
        logger.error(f"File '{file_name}' not found.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":    
    api_key = None
    # Check if the environment variable exists
    if DEEPL_KEY_VAR in os.environ:
        # Access the value of the environment variable
        api_key = os.environ[DEEPL_KEY_VAR]
    else:
        exit(f"The environment variable {DEEPL_KEY_VAR} is not set.")
    
    o = Compiler(api_key)
    o.compile(reload=True)

    # from scraper.parser import DWDSParser    

    # o = DWDSParser()
    # o.parse_genus(["alle in die Buss kommen nach DER Wahrnehmung allgemeingesellschaftlicher Interessen"], "Wahrnehmung") 
    
