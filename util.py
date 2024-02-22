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