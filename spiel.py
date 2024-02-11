from colorama import Back, Fore, Style
import json
import math
from numpy import polyfit
import os
import random

from log import get_logger, update_logging_level
from translation_compiler import Compiler, DUMP_FILE_NAME, DEEPL_KEY_VAR
import util

logger = get_logger()

SCORE_FILE_NAME = "_scores.txt"

class DeutschesSpiel:
    def __init__(self, reload=False, use_semantic=False):
        self._reload = reload
        self._use_semantic = use_semantic
        
        self._rows = {}  #{<word>: {"de_to_en":<>, "translation":<>,...}}
        self._basic_scores = {}  #{<word>:[90.0, 45.0,...]}
        
        self._sorted_words = []

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
            compiler.compile(self._reload)
            
            if not util.file_exists(DUMP_FILE_NAME):
                exit("No dump file found and could not create one inline.")
            
        with open(DUMP_FILE_NAME, 'r') as file:
            logger.debug(f"Loading entries from current dump file.")
            self._rows = json.load(file)
            
        if util.file_exists(SCORE_FILE_NAME):
            with open(SCORE_FILE_NAME, 'r') as file:
                logger.debug(f"Loading entries from scores dump file.")
                self._basic_scores = json.load(file)
        else:
            logger.debug("No scores file found.")
                
        self._prepare_game()            
                
    def _prepare_game(self):
        # Calculate the slope of the trend line for each word's scores
        word_slopes = {}
        for word, scores in self._basic_scores.items():
            x = list(range(1, len(scores) + 1))  # Assuming scores are given in chronological order
            slope, _ = polyfit(x, scores, 1)
            word_slopes[word] = slope

        # Sort the words based on their slopes in descending order
        self._sorted_words = sorted(word_slopes, key=word_slopes.get)

        # Print the sorted words along with their slopes
        for word in self._sorted_words:
            logger.debug(f'{word}: {word_slopes[word]}')

    def _get_next_spiel_word(self):
        n = len(self._rows)
        sn = len(self._sorted_words)
        ideal_interval = math.ceil(sn / n - sn) if sn > n - sn else 1
        
        interval = random.randint(1, ideal_interval)
        
        index = 0
        asked = 0
        used_words = set()
        question_indices = set()
        
        while True:        
            if index >= sn or asked >= interval:
                idx = random.randint(0, n - 1)
                entry = self._rows[idx]
                word = entry["word"]

                if word in used_words or idx in question_indices:
                    continue
                
                if asked >= interval:
                    asked = 0
                    interval = random.randint(1, ideal_interval)

                question_indices.add(idx)
                yield word
            else:
                used_words.add(self._sorted_words[index])
                yield self._sorted_words[index]
                index += 1
                asked += 1

    def show_scores(self):
        print("SCORES")
        print("======")
        for word in self._sorted_words:
            print(f"{word}: {self._basic_scores[word]}")
            
    def get_next_entry(self):
        spiel_dict = {}
        for entry in self._rows:
            word = entry["word"]
            spiel_dict[word] = entry
        
        next_spiel = self._get_next_spiel_word()

        while True:
            word = next(next_spiel)
            yield spiel_dict[word] 
        
    def exit_game(self):
        with open(SCORE_FILE_NAME, 'w') as file:
            logger.debug(f"Dumping all scores to file.")
            json.dump(self._basic_scores, file)
            
    def get_answer_score(self, answer, translation):
        similarity_score = find_similarity(answer, translation, self._use_semantic)
        score = normalized_score(similarity_score, self._use_semantic)
        return (correctness_string(score), score)
     
    def play_game(self):
        next_entry = self.get_next_entry()
        while True:
            entry = next(next_entry)
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
    parser.add_argument('--reload', action='store_true', help='Load new translations')    
    args = parser.parse_args()

    if args.debug:
        update_logging_level(logger, "debug")
        logger.info("Enabled debug logging")

    use_semantic = False
    if args.semantic:
        SemanticComparator.load()
        use_semantic = True
        
    if args.reload:
        api_key = None
        # Check if the environment variable exists
        if DEEPL_KEY_VAR in os.environ:
            # Access the value of the environment variable
            api_key = os.environ[DEEPL_KEY_VAR]
        else:
            exit(f"The environment variable {DEEPL_KEY_VAR} is not set.")
                        
        compiler = Compiler(api_key)
        compiler.compile(reload=True)

    spiel = DeutschesSpiel(use_semantic)
    if prompt('Möchtest du ein Spiel spielen?'):
        spiel.play_game()
    elif prompt('Möchtest du deine Notizen überarbeiten?'):
        spiel.show_scores()