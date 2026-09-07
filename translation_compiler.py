# from gevent import monkey
# monkey.patch_all()
import argparse
import gevent
from gevent.event import Event

from functools import partial
import json
import os
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
DUMP_BATCH_SIZE = 15

DEEPL_KEY_VAR = "DEEPL_KEY"

logger = get_logger()

class Compiler:
    def __init__(self, translator_api_key, simulation=False):
        logger.info("Starting Compiler...")
        
        self._worksheet = None
        
        self._entries = None
        self._gs_entries = None
        
        self._crawler = CrawlerFactory.get_crawler("dwds")
        
        self._simulation = simulation
        if self._simulation:
            self._translator = TranslatorFactory.get_translator("mock", translator_api_key)
        else:
            self._translator = TranslatorFactory.get_translator("deepl", translator_api_key)

        self._parser = ParserFactory.get_parser("dwds")
                      
    def scrape_new(self, reload=False):
        # Step 1. Read word list.
        fetched = self._fetch_glossary(fetch_from_google_sheet=reload)
        if not fetched:
            logger.critical("Fetching glossary failed", exc_info=1)
            return
        
        # Step 2. Build scrape list.
        if reload or not util.file_exists(SCRAPE_QUEUE_FILE_NAME):
            self._prepare_for_scrape()
        
        # Step 3. Scrape.
        self._scrape_and_translate()

        # Step 4.
        self._cleanup()
                
    def _cleanup(self):
        _delete_file(SCRAPE_QUEUE_FILE_NAME)
        
    def _scrape_de_to_en(self, word):
        return self._crawler.crawl(word)
    
    def _translate_de_to_en(self, word):
        return self._translator.translate_from_deutsch(word)

    def _translate_many_de_to_en(self, texts):
        return self._translator.translate_many_from_deutsch(texts)
    
    def _translate_en_to_de(self, word):
        return self._translator.translate_from_englisch(word)
        
    def _post_process_scrape(self, scrape_word, scrape_entry, event, source_greenlet):
        k = source_greenlet.name
        v = source_greenlet.value
        scrape_entry[k] = v

        if source_greenlet.exception is not None:
            scrape_entry["incorrect"] = True
            logger.error(
                f"Fetching {k} for {scrape_word} failed: "
                f"{source_greenlet.exception}")
        elif v is None and not self._simulation:
            scrape_entry["incorrect"] = True
            logger.error(f"Fetching {k} for {scrape_word} returned no result")

        logger.debug(f"Set {k} to {v} for {scrape_word}")
        
        if "translation" in scrape_entry and "file" in scrape_entry:
            logger.debug(f"Both keys set for {scrape_word}")

            def combine_scrape_data():
                try:
                    self._combine_scrape_data(scrape_word, scrape_entry)
                except Exception as e:
                    scrape_entry["incorrect"] = True
                    logger.exception(
                        f"Combining fetched data for {scrape_word} failed: {e}")

            t = threading.Thread(
                target=combine_scrape_data,
                name=scrape_word)
            t.start()
            t.join()
            
            event.set()
        
    def _combine_scrape_data(self, scrape_word, scrape_entry):
        scrape_entry["examples"] = []
        scrape_entry["metadata"] = []
        scrape_entry["grammar"] = ""

        scrape_entry.setdefault("incorrect", False)
        if scrape_entry["incorrect"]:
            return

        if scrape_entry['file'] is None:
            scrape_entry["incorrect"] = True
            logger.warning(f"No scrape file for {scrape_word} found")
            return
        
        file_name = scrape_entry['file']
        try:
            with open(file_name, 'r') as file:
                scrape_contents = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            scrape_entry["incorrect"] = True
            logger.error(f"File {file_name} not found for parsing.")
            return

        examples = self._parser.parse_examples(scrape_contents)
        scrape_entry["grammar"] = self._parse_grammar(scrape_contents)
        
        try:
            translated_examples = self._translate_many_de_to_en(examples)
        except Exception as e:
            scrape_entry["incorrect"] = True
            logger.error(
                f"Fetching example translations for {scrape_word} failed: {e}")
            return

        if len(translated_examples) != len(examples):
            scrape_entry["incorrect"] = True
            logger.error(
                f"DeepL returned {len(translated_examples)} of {len(examples)} "
                f"example translations for {scrape_word}")
            return

        if not self._simulation and any(
                translation is None for translation in translated_examples):
            scrape_entry["incorrect"] = True
            logger.error(
                f"Fetching example translations for {scrape_word} "
                "returned an empty result")
            return

        scrape_entry["examples"] = list(zip(examples, translated_examples))
        
        genus = self._parser.parse_genus(examples, scrape_word)
        scrape_entry["metadata"] = {"genus": genus}

    @staticmethod
    def _parse_grammar(scrape_contents):
        if isinstance(scrape_contents, dict):
            return scrape_contents.get("grammar", "")

        for item in reversed(scrape_contents):
            if isinstance(item, dict) and "grammar" in item:
                return item["grammar"]

        return ""

    @staticmethod
    def backfill_existing_grammar():
        """Refresh grammar in every scrape cache without calling DeepL."""
        crawler = CrawlerFactory.get_crawler("dwds")
        words = crawler.existing_crawl_words()
        grammar_by_word = {}
        failed_words = []

        logger.info(f"Backfilling grammar for {len(words)} existing scrape files")
        for index, word in enumerate(words, start=1):
            grammar = crawler.backfill_grammar(word)
            if grammar is None:
                failed_words.append(word)
            else:
                grammar_by_word[word] = grammar

            if index % DUMP_BATCH_SIZE == 0 or index == len(words):
                logger.info(f"Processed grammar for {index}/{len(words)} files")

        updated_dump_entries = 0
        try:
            with open(DUMP_FILE_NAME, 'r') as file:
                dump_entries = json.load(file)

            for entry in dump_entries:
                if not isinstance(entry, dict):
                    continue

                word = entry.get("word")
                if word in grammar_by_word:
                    entry["grammar"] = grammar_by_word[word]
                    updated_dump_entries += 1

            with open(DUMP_FILE_NAME, 'w') as file:
                json.dump(dump_entries, file)
        except FileNotFoundError:
            logger.warning(
                f"Compiled dump {DUMP_FILE_NAME} was not found; "
                "only scrape files were updated")
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Updating compiled dump {DUMP_FILE_NAME} failed: {e}")

        if failed_words:
            util.append_to_file(INCORRECT_WORDS_FILE_NAME, failed_words)

        logger.info(
            f"Grammar backfill complete: {len(grammar_by_word)} scrape files "
            f"updated, {updated_dump_entries} compiled entries updated, "
            f"{len(failed_words)} failures")

        return {
            "scrape_files": len(grammar_by_word),
            "dump_entries": updated_dump_entries,
            "failed_words": failed_words,
        }
    
    def _scrape_and_translate(self):
        try:
            with open(SCRAPE_QUEUE_FILE_NAME, 'r') as file:                
                to_be_scraped_queue = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"No scrape queue found")
            return

        events = []
        event_entries = {}
        completed_entries = {}

        def add_completed(word, entry):
            if entry.get("incorrect", False):
                # Failures should be available for manual correction as soon as
                # they are known; they do not count toward the success batch.
                self._dump_metadata({word: entry})
                return

            completed_entries[word] = entry
            if len(completed_entries) >= DUMP_BATCH_SIZE:
                self._dump_metadata(completed_entries)
                completed_entries.clear()

        for scrape_word, scrape_entry in to_be_scraped_queue.items():
            if scrape_entry['de_to_en']:
                event = Event()
                events.append(event)
                event_entries[event] = (scrape_word, scrape_entry)
                
                greenlet1 = gevent.spawn(self._scrape_de_to_en, scrape_word)
                greenlet1.name = "file"
                greenlet1.link(partial(
                    self._post_process_scrape, 
                    scrape_word, scrape_entry, event))
                
                if "translation" not in scrape_entry:                
                    greenlet2 = gevent.spawn(self._translate_de_to_en, scrape_word)
                    greenlet2.name = "translation"

                    greenlet2.link(partial(
                        self._post_process_scrape,
                        scrape_word, scrape_entry, event))
            else:  # en to de
                # First get the German translation, then do the usual scraping
                # as is done for German words.
                scrape_entry["incorrect"] = False
                try:
                    if "translation" not in scrape_entry:
                        translation = self._translate_en_to_de(scrape_word)
                        scrape_entry["translation"] = translation
                        if translation is None and not self._simulation:
                            scrape_entry["incorrect"] = True
                            logger.error(
                                f"Fetching translation for {scrape_word} "
                                "returned no result")
                except Exception as e:
                    scrape_entry["incorrect"] = True
                    logger.error(
                        f"Fetching translation for {scrape_word} failed: {e}")

                add_completed(scrape_word, scrape_entry)

                # event = Event()
                # events.append(event)
                # greenlet = gevent.spawn(self._scrape_de_to_en, translation)
                # greenlet.name = "file"
                # greenlet.link(partial(
                #     self._post_process_scrape, 
                #     translation, scrape_entry, event))
                
                          
        for completed_event in gevent.iwait(events):
            scrape_word, scrape_entry = event_entries[completed_event]
            add_completed(scrape_word, scrape_entry)

        # Persist the final partial batch as well.
        if completed_entries:
            self._dump_metadata(completed_entries)
        
        self._translator.get_translator_call_stats()
        self._write_translations_to_gs(to_be_scraped_queue)
                
    def _dump_metadata(self, scraped_entries):
        dump_entries = []
        incorrect_words = []
        for word, entry in scraped_entries.items():
            if entry.get("incorrect", False):
                incorrect_words.append(word)
                continue
            
            examples = entry["examples"] if entry["de_to_en"] else []
            metadata = entry["metadata"] if entry["de_to_en"] else []
            grammar = entry["grammar"] if entry["de_to_en"] else ""
            
            logger.debug(f"Adding {word} to dump.")
            
            dump_entries.append({
                "word": word,
                "de_to_en": entry["de_to_en"],
                "translation": entry["translation"],
                "examples": examples,
                "grammar": grammar,
                "metadata": metadata,
                "synonyms": entry["synonyms"]
            })
        
        if not self._simulation and dump_entries:
            util.upsert_to_file(DUMP_FILE_NAME, dump_entries, key="word")
            
        if not self._simulation and incorrect_words:
            util.append_to_file(INCORRECT_WORDS_FILE_NAME, incorrect_words)
                    
    def _prepare_for_scrape(self):  
        if self._gs_entries is None or len(self._gs_entries) == 0:
            logger.debug("No new entries from Google Spreadsheet")
            return

        dumped_words = self._load_dumped_words()
        
        # Schedule scraping for any word in GS not having a translation.
        to_be_scraped_queue = {}
        for row in self._gs_entries:            
            word1 = row["Deutsch"].strip() if row["Deutsch"].strip() != '' else None
            word2 = row["Englisch"].strip() if row["Englisch"].strip() != '' else None
            
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

            if word is None:
                logger.warning(
                    "Skipping Google Sheets row with neither Deutsch nor "
                    f"Englisch set: {row}")
                continue

            if word.casefold() in dumped_words:
                logger.debug(f"{word} is already present in the compiled dump.")
                continue

            if row["Bedeutung"].strip() == '':
                logger.info(f"{word} has no Bedeutung, hence translating.")
            elif de_to_en and not self._crawler.crawl_file_exists(word):
                logger.info(f"{word} has no scrape file, hence scraping.")
            else:
                logger.info(
                    f"{word} is missing from the compiled dump; "
                    "reusing its existing translation and scrape file.")
                                
            synonyms = ""
            if row["Synonyms"].strip() != '':
                synonyms = row["Synonyms"].strip()
            
            to_be_scraped_queue[word] = {
                'de_to_en': de_to_en,
                'synonyms': synonyms
            }
            if row["Bedeutung"].strip() != '':
                to_be_scraped_queue[word]["translation"] = row["Bedeutung"].strip()
            logger.debug(f"To be scraped: {word}: {to_be_scraped_queue[word]}")
    
        # Always replace the queue so an older interrupted run cannot be
        # processed again when the current glossary is already complete.
        with open(SCRAPE_QUEUE_FILE_NAME, 'w') as file:
            logger.debug(f"Writing scrape entries")
            json.dump(to_be_scraped_queue, file)

    @staticmethod
    def _load_dumped_words():
        try:
            with open(DUMP_FILE_NAME, 'r') as file:
                dump_entries = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            return set()

        return {
            entry["word"].strip().casefold()
            for entry in dump_entries
            if isinstance(entry, dict) and isinstance(entry.get("word"), str)
        }
        
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
            self._worksheet = spreadsheet.worksheet('Vokabeln')

            # Get all values from the worksheet
            # self._gs_entries = self._worksheet.get_all_values()[1:]
            self._gs_entries = self._worksheet.get_all_records()
            
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
            if row["Deutsch"].strip() != '':
                word = row["Deutsch"].strip()
            elif row["Englisch"].strip() != '':
                word = row["Englisch"].strip()
                
            row_index += 1                
            if row["Bedeutung"].strip():
                # Already has a Bedeutung filled in.
                continue
                
            if word not in scraped_entries:
                logger.error(f"No translation found for {word}")
                continue

            entry = scraped_entries[word]
            if entry.get("incorrect", False):
                logger.warning(f"Skipping failed entry {word} in Google Sheets update")
                continue

            cell_value = entry["translation"]

            logger.debug(f"Batch update writing {word} in {row_index - 1} with {cell_value}")

            if not self._simulation:
                batch_updates.append({
                    'range': gspread.utils.rowcol_to_a1(row_index - 1, column_to_update),
                    'values': [[cell_value]],
                })
  
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
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument(
        "--backfill-grammar",
        action="store_true",
        help="Refresh grammar for all existing DWDS scrape files without DeepL")
    args = argument_parser.parse_args()

    if args.backfill_grammar:
        Compiler.backfill_existing_grammar()
        exit(0)

    api_key = None
    # Check if the environment variable exists
    if DEEPL_KEY_VAR in os.environ:
        # Access the value of the environment variable
        api_key = os.environ[DEEPL_KEY_VAR]
    else:
        exit(f"The environment variable {DEEPL_KEY_VAR} is not set.")
    
    o = Compiler(api_key)
    o.scrape_new(reload=True)

    # from scraper.parser import DWDSParser    

    # o = DWDSParser()
    # o.parse_genus(["alle in die Buss kommen nach DER Wahrnehmung allgemeingesellschaftlicher Interessen"], "Wahrnehmung") 
    
