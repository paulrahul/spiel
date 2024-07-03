from gevent import monkey
monkey.patch_all()

from colorama import Back, Fore, Style
import json
import math
from numpy import polyfit
import os
import random

import gs_reader
from log import get_logger, update_logging_level
from translation_compiler import Compiler, DUMP_FILE_NAME, DEEPL_KEY_VAR
import util

logger = get_logger()

SCORE_FILE_NAME = "_scores.txt"
PREPOSITIONS_FILE_NAME = "_prepositions.txt"

GS_SHEET_NAME = "Vokabeln und Phrasen"

class DeutschesSpiel:
    def __init__(self, reload=False, use_semantic=False, use_multimode=False):
        self.SPIEL_MODES = {
            "word": self._get_next_spiel_word,
            "preposition": self._get_next_preposition
        }        
        
        self._reload = reload
        self._use_semantic = use_semantic
        self._use_multimode = use_multimode
        
        self._rows = {}  # {"word":<word>, "de_to_en":<>, "translation":<>,...}
        self._spiel_dict = {} # {<word>: <original word entry>}
        
        self._prepositions = []
        
        self._basic_scores = {}  # {<word>:[90.0, 45.0,...]}
        
        self._sorted_words = []
        
        self._mode_handlers = {}
        
        self._init()

    def _init(self):
        print("Initialising game...\n\n")
        
        if not util.file_exists(DUMP_FILE_NAME):
            api_key = None
            # Check if the environment variable exists
            if DEEPL_KEY_VAR in os.environ:
                # Access the value of the environment variable
                api_key = os.environ[DEEPL_KEY_VAR]
            else:
                exit(f"The environment variable {DEEPL_KEY_VAR} is not set.")
                          
            compiler = Compiler(api_key)
            compiler.scrape_new(self._reload)
            
            if not util.file_exists(DUMP_FILE_NAME):
                exit("No dump file found and could not create one inline.")
            
        with open(DUMP_FILE_NAME, 'r') as file:
            logger.debug(f"Loading entries from current dump file.")
            self._rows = json.load(file)

            self._spiel_dict = {}
            for entry in self._rows:
                word = entry["word"]
                self._spiel_dict[word.lower()] = entry            
            
        if util.file_exists(SCORE_FILE_NAME):
            with open(SCORE_FILE_NAME, 'r') as file:
                logger.debug(f"Loading entries from scores dump file.")
                self._basic_scores = json.load(file)
        else:
            logger.debug("No scores file found.")
        
        for k, v in self.SPIEL_MODES.items():
            self._mode_handlers[k] = {
                "random": v(serial=False),
                "serial": v(serial=True)
            }
        
        self._init_prepositions()
                
        self._prepare_game()        
    
    def _init_prepositions(self):
        if not util.file_exists(PREPOSITIONS_FILE_NAME):
            self._prepositions = gs_reader.fetch_from_gsheet(
                GS_SHEET_NAME, "Prepositions")
            
            with open(PREPOSITIONS_FILE_NAME, 'w') as file:
                logger.debug(f"Dumping prepositions to file.")
                json.dump(self._prepositions, file)
        else:
            with open(PREPOSITIONS_FILE_NAME, 'r') as file:
                self._prepositions = json.load(file)
    
    def sort_words(self, basic_scores):
        # Calculate the slope of the trend line for each word's scores
        word_slopes = {}
        for word, scores in basic_scores.items():
            x = list(range(1, len(scores) + 1))  # Assuming scores are given in chronological order
            slope, _ = polyfit(x, scores, 1)
            word_slopes[word] = slope

        # Sort the words based on their slopes in descending order
        self._sorted_words = sorted(word_slopes, key=word_slopes.get)

        # Print the sorted words along with their slopes
        for word in self._sorted_words:
            logger.debug(f'{word}: {word_slopes[word]}')      
                
    def _prepare_game(self):
        # self.sort_words(self._basic_scores)
        pass

    def _get_spiel_word(self, serial):
        n = len(self._rows)
        sn = len(self._sorted_words)
        ideal_interval = math.ceil(sn / n - sn) if sn > n - sn else 1
        
        interval = random.randint(1, ideal_interval)
        
        logger.debug(f"{n=}, {sn=}, {ideal_interval=}, {interval=}")
        
        index = 0
        asked = 0
        used_words = set()
        question_indices = set()
        
        while True:
            if not serial and (index >= sn or asked >= interval):
                # I guess the idea was that we serially show the 'sorted words'
                # or basically the words that are sorted by previous scores
                # except when an 'interval' number of words have already been
                # asked or if all scored words have already been asked. In that
                # case, just return a random word index. 
                
                logger.debug("Returning a random index word")
                idx = random.randint(0, n - 1)
                entry = self._rows[idx]
                word = entry["word"]
                
                logger.debug(f"{idx=}, {word=}")

                if word in used_words or idx in question_indices:
                    logger.debug(f"Word is already used.")
                    continue
                
                if asked >= interval:
                    asked = 0
                    interval = random.randint(1, ideal_interval)
                    
                logger.debug(f"{word=}")

                question_indices.add(idx)
                yield word
            else:
                logger.debug(f"Returning serial order {index} word.")
                if index < sn:
                    used_words.add(self._sorted_words[index])
                    yield self._sorted_words[index]
                else:
                    if index >= n:
                        index = 0
                    entry = self._rows[index]
                    word = entry["word"]
                    
                    used_words.add(word)
                    yield word
                    
                index += 1
                asked += 1
                
    def get_scores(self):
        return [(w, self._basic_scores[w]) for w in self._sorted_words]
        
    def show_scores(self):
        print("SCORES")
        print("======")
        sw = self.get_scores()
        for row in sw:
            print(f"{row[0]} -> {row[1]}")
            
    def lookup(self, word):
        word = word.lower()
        try:
            return self._spiel_dict[word]
        except KeyError:
            return None
        
    '''
    Returns the full list of words.
    '''
    def list(self):
        return list(self._spiel_dict.keys())
    
    
    '''
    Start of next iterator methods.
    '''
    def _get_next_spiel_word(self, serial):
        next_spiel = self._get_spiel_word(serial)

        while True:
            word = next(next_spiel)
            yield self._spiel_dict[word.lower()]

    def _get_next_preposition(self, serial):
        idx = -1
        
        while True:
            if serial:
                idx += 1
                if idx >= len(self._prepositions):
                    idx = 0
            else:
                idx = random.randint(0, len(self._prepositions))

            yield self._prepositions[idx]
    '''
    End of next iterator methods.
    '''

    '''
    Main methods to return next question.
    '''
    def get_next_entry(self, mode=None, serial=False, start=None):
        if start:
            if not serial:
                raise Exception("Start value provided but order is not serial.")            
            if not mode:
                raise Exception("No mode provided for start value.")

        if mode:
            next_spiel_mode = mode
        elif self._use_multimode:
            next_spiel_mode = random.choice(list(self.SPIEL_MODES.keys()))
        else:           
            raise Exception("No mode provided")
        
        logger.debug(f"Returning question of mode {next_spiel_mode}, serial {serial}, start {start}")

        if serial:
            cnt = 0
            while True:
                val = next(self._mode_handlers[next_spiel_mode]["serial"])
                cnt += 1
                if start:
                    # TODO: Clean up this rubbish implementation.
                    if next_spiel_mode == "word":
                        if cnt > len(self._rows):
                            raise Exception(f"Could not find word {start}")
                        qn = val["word"]
                    elif next_spiel_mode == "preposition":
                        if cnt > len(self._prepositions):
                            raise Exception(f"Could not find preposition {start}")
                        qn = val["verb"]
                        
                    if start.lower() == qn.lower():
                        break                    
                    logger.debug(f"Looking for {start} in mode {next_spiel_mode}, reached till {qn}")
                else:
                    break            
        else:
            val = next(self._mode_handlers[next_spiel_mode]["random"])

        return {"mode": next_spiel_mode, "value": val}
        
    def exit_game(self):
        with open(SCORE_FILE_NAME, 'w') as file:
            logger.debug(f"Dumping all scores to file.")
            json.dump(self._basic_scores, file)
            
    def get_answer_score(self, answer, translation):
        similarity_score = find_similarity(answer, translation, self._use_semantic)
        score = normalized_score(similarity_score, self._use_semantic)
        return (correctness_string(score), score)
     
    def play_game(self):
        while True:
            next_entry = self.get_next_entry(serial=True, start="Ereignis", mode="word")        
            entry = next_entry["value"]
            
            if next_entry["mode"] == "word":
                word = entry["word"]
                
                user_answer = input(
                    Fore.CYAN + f'Was bedeutet {word}?: ' + Style.RESET_ALL).strip().lower()
                if len(user_answer) > 0:
                    (score_string, score) = self.get_answer_score(
                        user_answer, entry["translation"])
                    print(
                        f"Deine Antwort ist {score_string}, " +
                        f"Ähnlichkeitwert {score}")
                else:
                    score = 0
                    
                if word in self._basic_scores:
                    self._basic_scores[word].append(score)
                else:
                    self._basic_scores[word] = [score]
                    
                print(Fore.GREEN + f"\nEchte Antwort: {entry['translation'].upper()}" + Style.RESET_ALL + 
                    Back.GREEN + Style.BRIGHT + "\n\nExamples:" + Style.RESET_ALL)
                _print_examples(entry["examples"])
                
                if "genus" in entry['metadata']:
                    print(Back.GREEN + Style.BRIGHT + f"\nGenus:" + Style.RESET_ALL + " " + str(entry['metadata']['genus']))

            elif next_entry["mode"] == "preposition":
                verb = entry["verb"]
                user_preposition_answer = input(
                    Fore.CYAN + f'Welche Präposition soll mit {verb} verwendet werden?: ' + Style.RESET_ALL).strip().lower()
                user_akkdat_answer = ""
                while user_akkdat_answer.lower() not in ["a", "d"]:
                    user_akkdat_answer = input(
                        Fore.CYAN + f'Akkusativ oder Dativ. Gibst bitte "A" oder "D" an?: ' + Style.RESET_ALL).strip().lower()

                if len(user_preposition_answer) > 0:
                    (score_string, score) = self.get_answer_score(
                        user_preposition_answer, entry["preposition"])
                    print(
                        f"Deine Antwort ist {score_string}, " +
                        f"Ähnlichkeitwert {score}")
                    
                    user_akkdat_answer = "acc" if user_akkdat_answer.lower() == "a" else "dat"
                    (score_string, score) = self.get_answer_score(
                        user_akkdat_answer, entry["akk_dat"])
                    print(
                        f"Deine Antwort ist {score_string}, " +
                        f"Ähnlichkeitwert {score}")                    
                else:
                    score = 0
                    
                print(Fore.GREEN + f"\nEchte Antwort: {entry['verb']} {entry['preposition']} + {entry['akk_dat']}" + Style.RESET_ALL + 
                    Back.GREEN + Style.BRIGHT + "\n\nExamples:" + Style.RESET_ALL)                    
            
            if not prompt('\nWeiter?'):                    
                print(f"\nThank You!!\n")
                self.exit_game()
                break

WIDTH = 5

def _print_examples(examples):
    n = len(examples)
    n = 5 if n > 5 else n
    
    for i in range(0, n):
        print(f"{i+1}.{'':<{WIDTH-2}}{examples[i][0]}")
        print(f"{'':<{WIDTH}}{examples[i][1]}")
        print()
            
from fuzzywuzzy import fuzz

def normalized_score(score, semantic=False):
    if semantic:
        return score*100
    else:
        return score

def correctness_string(score):
    if score >= 90:
        return "richtig"
    elif score < 90 and score >= 70:
        return "fast richtig"
    else:
        return "nicht ganz richtig"

def find_similarity(str1, str2, semantic=False):
    # Convert strings to lowercase for case-insensitive comparison
    str1_lower = str1.lower()
    str2_lower = str2.lower()

    if not semantic:
        # Use the fuzz.ratio() method to get a similarity score
        return fuzz.ratio(str1_lower, str2_lower)
    else:
        return SemanticComparator.semantic_similarity(str1_lower, str2_lower)

THRESHOLD = 80
def are_strings_similar(str1, str2):
    score = find_similarity(str1, str2)
    return (score >= THRESHOLD, score)

import spacy

class SemanticComparator:
    _nlp = None
    
    @classmethod
    def load(cls):
        # Load the pre-trained word embeddings model from spaCy
        logger.info("Loading Spacy model..")
        cls._nlp = spacy.load("en_core_web_md")

    @classmethod
    def semantic_similarity(cls, str1, str2):
        # Process the strings with spaCy to get their word embeddings
        doc1 = cls._nlp(str1)
        doc2 = cls._nlp(str2)

        # Compute the similarity between the two strings based on their word embeddings
        similarity = doc1.similarity(doc2)

        return similarity

def prompt(text):
    user_input = input(f'{text} [j/n] : ').strip().lower()
    print()
    
    return user_input == 'j' or user_input == ''

if __name__ == "__main__":
    import argparse
    import os
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', '-d', action='store_true', help='Enable debug logging level')
    parser.add_argument('--semantic', '-s', action='store_true', help='Enable semantic comparison')
    parser.add_argument('--scrape_new', action='store_true', help='Load new translations')
    parser.add_argument('--simulate', '-sm', action='store_true', help='Enable simulation mode')
    parser.add_argument('--multi', '-m', action='store_true', help='Enable multi mode')      
    args = parser.parse_args()

    if args.debug:
        update_logging_level(logger, "debug")
        logger.info("Enabled debug logging")

    use_semantic = False
    if args.semantic:
        SemanticComparator.load()
        use_semantic = True
        
    simulate = args.simulate
    if simulate:
        logger.info("Enabled simulation mode")
        
    use_multimode = args.multi
    if use_multimode:
        logger.info("Enabled use_multimode mode")
        
    if args.scrape_new:
        api_key = None
        # Check if the environment variable exists
        if DEEPL_KEY_VAR in os.environ:
            # Access the value of the environment variable
            api_key = os.environ[DEEPL_KEY_VAR]
        else:
            exit(f"The environment variable {DEEPL_KEY_VAR} is not set.")
                        
        compiler = Compiler(api_key, simulate)
        compiler.scrape_new(reload=True)

    spiel = DeutschesSpiel(use_semantic=use_semantic, use_multimode=use_multimode)
    if prompt('Möchtest du ein Spiel spielen?'):
        spiel.play_game()
    elif prompt('Möchtest du deine Notizen überarbeiten?'):
        spiel.show_scores()