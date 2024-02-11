import functools
import logging

logging.basicConfig(
    level=logging.INFO,  # Set the global logging level
    format='[%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d] %(message)s'
    # handlers=[
    #     logging.FileHandler('logfile.log'),  # Specify the file name for logging
    # ]    
)

def logger_wrapper(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(__name__, *args, **kwargs)
    
    return wrapper

@logger_wrapper
def get_logger(module_name):
    return logging.getLogger(module_name)

def update_logging_level(logger, log_level):
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % log_level)
    
    logger.setLevel(numeric_level)