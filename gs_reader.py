import gspread
import traceback

from log import get_logger

logger = get_logger()

class FileReadError(Exception):
    """Custom exception for file reading errors."""
    def __init__(self, message, original_exception=None):
        super().__init__(message)
        self.original_exception = original_exception

def fetch_from_gsheet(spreadsheet, sheet):
    try:
        logger.debug(f"Reading Google Spreadsheet file {spreadsheet},{sheet}")
        
        # Authenticate with Google Sheets API
        gc = gspread.oauth()

        # Open the spreadsheet by title
        spreadsheet = gc.open(spreadsheet)

        # Select the worksheet by title
        worksheet = spreadsheet.worksheet(sheet)

        # Get all values from the worksheet
        gs_entries = worksheet.get_all_records()
        
        logger.debug(f"Obtained values from GS: {gs_entries}")
        
        return gs_entries
    except Exception as e:
        # Catch any exception and print its contents
        logger.error(f"Fetching Google sheet failed")
        traceback.print_exc()
        raise FileReadError(f"Error reading file at {spreadsheet},{sheet}: {str(e)}", e)