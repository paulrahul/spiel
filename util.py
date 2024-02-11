def file_exists(file_name):
    try:
        with open(file_name, 'r'):
            return True
    except FileNotFoundError:
        return False