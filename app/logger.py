from loguru import logger
import logging
import sys
from contextvars import ContextVar

# Context variable to hold the request ID
request_id_context = ContextVar("request_id", default="-")

# logger.add('data/bot.log', format='{time} {level} {file} {function} {line} {message}',
#            rotation='1 MB', encoding='utf-8') # Commented out old file logger

class InterceptHandler(logging.Handler):
    LEVELS_MAP = {
        logging.CRITICAL: "CRITICAL",
        logging.ERROR: "ERROR",
        logging.WARNING: "WARNING",
        logging.INFO: "INFO",
        logging.DEBUG: "DEBUG",
    }

    def _get_level(self, record):
        return self.LEVELS_MAP.get(record.levelno, record.levelno)

    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# Custom formatter to include request_id from context
def formatter(record):
    record["extra"]["request_id"] = request_id_context.get()
    # Keep original formatting but add request_id
    return "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {extra[request_id]} | {name}:{function}:{line} - {message}\n{exception}"

def setup():
    logger.remove() # Remove default handler to avoid duplicate logs
    
    # Add stdout sink with new formatter
    logger.add(
        sys.stdout,
        level="INFO", # Set appropriate level
        format=formatter,
        enqueue=True
    )
    
    # Add file sink with JSON format (optional, uncomment and configure if needed)
    # logger.add(
    #     "logs/app.log", 
    #     level="INFO", 
    #     rotation="10 MB", 
    #     retention="10 days", 
    #     serialize=True, # Output as JSON
    #     enqueue=True,
    #     # Add patcher to include request_id in JSON output correctly
    #     patcher=lambda record: record["extra"].update(request_id=request_id_context.get())
    # )
    
    # Configure standard logging to use the InterceptHandler
    # This should come AFTER configuring loguru sinks if you want stdlib logs 
    # to go through the new sinks.
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO)
    # Disable verbose SQLAlchemy logs if desired
    # logger.disable("sqlalchemy.engine.base")

setup()
