import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import json
from loguru import logger
from pathlib import Path

def setup_logging(environment:str="development",log_level:str="INFO"):
    logger.remove()
    
    if environment=="production":
        def json_sink(message):
            record=message.record
            entry={
                "timestamp":record["time"].isoformat(),
                "level":record["level"].name,
                "message":record["message"],
                "request_id":record["extra"].get("request_id",""),
                **{k:v for k,v in record["extra"].items() if k!="request_id"}
            }
            print(json.dumps(entry)) # converts json object dict to json string
        logger.add(json_sink,level=log_level)

    else:
        logger.add(
            sys.stdout,
            level="DEBUG",
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{extra[request_id]}</cyan> | "
                "{message}"
            ),
            colorize=True
        )

    script_dir=Path(__file__).parent
    log_dir=script_dir/"logs"
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir/"api_{time:YYYY-MM-DD}.log",
        level=log_level,
        rotation="00:00",
        retention="30 days",
        compression="zip"
    )

    logger.add(
        log_dir/"error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        rotation="1 week",
        retention="90 days",
        backtrace=True,
        diagnose=True
    )


auth_logger=logger.bind(subsystem="auth",request_id="")
db_logger=logger.bind(subsystem="db",request_id="")
llm_logger=logger.bind(subsystem="llm",request_id="")
api_logger=logger.bind(subsystem="api",request_id="")

    

