import json

def file_exists(file_name):
    try:
        with open(file_name, 'r'):
            return True
    except FileNotFoundError:
        return False
    
def append_to_file(file_name, new_entries):
    existing_data = []
    
    try:
        # Read the existing JSON list from the file
        with open(file_name, 'r') as file:
            existing_data = json.load(file)
    except FileNotFoundError:
        pass

    existing_data.extend(new_entries)

    # Write the updated list back to the file
    with open(file_name, 'w') as file:
        json.dump(existing_data, file)

def upsert_to_file(file_name, new_entries, key):
    existing_data = []

    try:
        with open(file_name, 'r') as file:
            existing_data = json.load(file)
    except FileNotFoundError:
        pass

    entry_indices = {
        entry[key]: index
        for index, entry in enumerate(existing_data)
        if isinstance(entry, dict) and key in entry
    }

    for entry in new_entries:
        entry_key = entry[key]
        if entry_key in entry_indices:
            existing_data[entry_indices[entry_key]] = entry
        else:
            entry_indices[entry_key] = len(existing_data)
            existing_data.append(entry)

    with open(file_name, 'w') as file:
        json.dump(existing_data, file)
