import re

from log import get_logger

logger = get_logger()

class Parser:
    def parse_examples(self, file_name):
        pass

class DWDSParser(Parser):
    def parse_examples(self, scrape_contents):
        ret = []
        for entry in scrape_contents:
            if "@type" in entry and entry["@type"] == "Quotation":
                ret.append(entry["text"])
                
        return ret
    
    def parse_genus(self, texts, word):
        results = []
        
        # Define the regex pattern
        pattern = re.compile(r'\b(?:der|die|das)\s*\w*\s*' + re.escape(word) + r'\b', re.IGNORECASE)
        for line in texts:
            match = re.search(pattern, line)
            if match:
                results.append(match.group(0))
                
        return results
    
class ParserFactory:
    @classmethod
    def get_parser(cls, parser_source):
        if parser_source.lower() == "dwds":
            return DWDSParser()
        else:
            raise ValueError(f"Invalid parser source type {parser_source}")    