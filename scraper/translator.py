import deepl

from log import get_logger

logger = get_logger()

class Translator:
    def __init__(self, api_key):
        self.api_key = api_key
        
        self._de_to_en_texts = []
        self._en_to_de_texts= []
        
        self._translator = None

        self._init(api_key)
        
    def _init(self, api_key):
        pass
    
    def translate_from_deutsch(self, german_text):
        pass
    
    def translate_from_englisch(self, english_text):
        pass
    
    def api_call_count(self):
        n1 = len(self._de_to_en_texts)
        n2 = len(self._en_to_de_texts)
        nc1 = sum(len(s) for s in self._de_to_en_texts)
        nc2 = sum(len(s) for s in self._en_to_de_texts)        
        
        print(f"DE to EN -> Call count: {n1}, character count: {nc1}")
        print(f"EN to DE -> Call count: {n2}, character count: {nc2}")
        print(f"Total -> Call count: {n1 + n2}, character count: {nc1 + nc2}")

    def api_call_list(self):
        print(f"DE to EN: {self._de_to_en_texts}")
        print(f"EN to DE: {self._en_to_de_texts}")
        
    def get_translator_call_stats(self):
        self.api_call_count()
        self.api_call_list()

class DeeplTranslator(Translator):        
    def _init(self, api_key):
        # Create a Deepl client
        self._translator = deepl.Translator(api_key)
    
    def translate_from_deutsch(self, german_text):
        # Translate the German text to English
        response = self._translator.translate_text(
            source_lang="de", target_lang="en-us", text=german_text)
        
        self._de_to_en_texts.append(german_text)
        logger.debug(f"Fetched translation {response.text} for {german_text}")

        return response.text
    
    def translate_from_englisch(self, english_text):
        # Translate the English text to German
        response = self._translator.translate_text(
            source_lang="en", target_lang="de", text=english_text)
        
        self._en_to_de_texts.append(english_text)
        logger.debug(f"Fetched translation {response.text} for {english_text}")

        return response.text

MOCK_RESPONSE_TEXT = None
class MockTranslator(Translator):      
    def _init(self, api_key):
        logger.debug("Mock translator created.")
            
    def translate_from_deutsch(self, german_text):       
        logger.debug(f"Mock DE_to_EN translation called for {german_text}")
        self._de_to_en_texts.append(german_text)

        return MOCK_RESPONSE_TEXT
    
    def translate_from_englisch(self, english_text):
        logger.debug(f"Mock EN_to_DE translation called for {english_text}")
        self._en_to_de_texts.append(english_text)

        return MOCK_RESPONSE_TEXT
    
class TranslatorFactory:
    @classmethod
    def get_translator(cls, translator_source, api_key):
        if translator_source.lower() == "deepl":
            return DeeplTranslator(api_key)
        elif translator_source.lower() == "mock":
            return MockTranslator(api_key)
        else:
            raise ValueError(f"Invalid translator source type {translator_source}")