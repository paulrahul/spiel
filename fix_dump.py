import json
import traceback

import gspread

DUMP_FILE_PATH = "_dump.txt"

def fetch_from_gsheet():
    try:
        print(f"Reading Google Spreadsheet file")
        
        # Authenticate with Google Sheets API
        gc = gspread.oauth()

        # Open the spreadsheet by title
        spreadsheet = gc.open('Vokabeln und Phrasen')

        # Select the worksheet by title
        worksheet = spreadsheet.worksheet('Vokabeln')

        # Get all values from the worksheet
        return worksheet.get_all_records()

    except Exception as e:
        # Catch any exception and print its contents
        print(f"Fetching Google sheet failed")
        traceback.print_exc()
        return None

def fix_dump_synonyms():    
    rows = fetch_from_gsheet()
    if rows is None:
        print("No rows found in spreadsheet")
    else:
        synonyms = {}
        for row in rows:
            word = None
            if row["Deutsch"].strip() != '':
                word = row["Deutsch"].strip()
            elif row["Englisch"].strip() != '':
                word = row["Englisch"].strip()
                
            if row["Synonyms"].strip() != '':
                if word is not None:
                    synonyms[word] = row["Synonyms"].strip()
                    
    # Read the existing JSON list from the file
    with open(DUMP_FILE_PATH, 'r') as file:
        existing_data = json.load(file)

    # Modify
    for row in existing_data:
        if "word" in row and row["word"] in synonyms:
            print(f"Writing {synonyms[row['word']]} for {row['word']}")
            row["synonyms"] = synonyms[row["word"]]
        else:
            row["synonyms"] = ''

    # Write the updated list back to the file
    with open(DUMP_FILE_PATH, 'w') as file:
        json.dump(existing_data, file)

    print("New entries added and file updated successfully.")

def fix_dump_rows():
    rows = fetch_from_gsheet()

    if rows is None:
        print("No rows found in spreadsheet")
    else:
        word_map = {}
        for row in rows:
            word = None
            if row["Deutsch"].strip() != '':
                word = row["Deutsch"].strip()
            elif row["Englisch"].strip() != '':
                word = row["Englisch"].strip()
            
            word_map[word] = {}
            if row["Bedeutung"].strip() != '':
                if word is not None:
                    word_map[word]["bedeutung"] = row["Bedeutung"].strip()
               
            if row["Synonyms"].strip() != '':
                if word is not None:
                    word_map[word]["synonyms"] = row["Synonyms"].strip()        
        
        # Read the existing JSON list from the file
        with open(DUMP_FILE_PATH, 'r') as file:
            existing_data = json.load(file)

        # Modify
        extra_dump_words = set()
        new_data = []
        for row in existing_data:
            word = row["word"]
            
            if word not in word_map:
                extra_dump_words.add(word)
                continue
            
            word_map[word]["both"] = True
            
            if "bedeutung" in word_map[word]:
                translation = word_map[word]["bedeutung"]
                if translation != row["translation"]:
                    print(f"Updating translation of {word} from {row['translation']} to {translation}")
                row["translation"] = word_map[word]["bedeutung"]
        
            if "synonyms" in word_map[word]:
                synonyms = word_map[word]["synonyms"]
                if synonyms != row["synonyms"]:
                    print(f"Updating synonyms of {word} from {row['synonyms']} to {synonyms}")
                
                row["synonyms"] = word_map[word]["synonyms"]
                
            new_data.append(row)

        # Write the updated list back to the file
        with open(DUMP_FILE_PATH, 'w') as file:
            json.dump(new_data, file)
        
        print(f"Words found in GS but not in dump file. These words most likely need to be corrected. :\n{[word for word in word_map if 'both' not in word_map[word]]}")
        print(f"Words found in dump file but not in GS:\n{extra_dump_words}")
            
def dedupe():
    with open(DUMP_FILE_PATH, 'r') as file:
        existing_data = json.load(file)
        
    written_words = {}
    new_data = []
    for row in existing_data:  
        word = row["word"]
      
        keys = ["word", "de_to_en", "translation", "examples", "metadata", "synonyms"]
        for k in keys:
            if k not in row:
                print(f"{k} not found in {word}")
        
        if word in written_words:
            written_words[word] += 1
            continue

        new_data.append(row)
        written_words[word] = 1
        
    print(f"Existing data length: {len(existing_data)}")
    print(f"New data length: {len(new_data)}")
    for word in written_words:
        if written_words[word] > 1:
            print(f"{word} is repeated {written_words[word]} times")
    
    # Write the updated list back to the file
    with open(DUMP_FILE_PATH, 'w') as file:
        json.dump(new_data, file)    

if __name__ == "__main__":
    fix_dump_rows()
    dedupe()
