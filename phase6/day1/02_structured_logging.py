import os,sys
from pathlib import Path
import json
from loguru import logger
from datetime import datetime,timezone



# ============================================================
# JSON FORMATTER — production standard
# ============================================================
def json_formatter(record:dict)->str:
    """
    Format log record as JSON.
    Every field becomes queryable in log aggregation tools.
    """
    log_entry = {
        "timestamp":  record["time"].isoformat(),
        "level":      record["level"].name,
        "logger":     record["name"],
        "function":   record["function"],
        "line":       record["line"],
        "message":    record["message"],
    }

    # Add any extra fields from .bind()
    if record["extra"]:
        log_entry.update(record["extra"])

    # Add exception info if present
    if record["exception"]:
        log_entry["exception"]={
            "type":str(record["exception"].type),
            "value":str(record["exception"].value)
        }
    return json.dumps(log_entry)+"\n"

def setup_json_logger(log_dir:Path):
    """Setup JSON structured logging for production"""
    logger.remove()

    # Console — JSON for production (parse by log aggregators)
    logger.add(
        sys.stdout,
        #format=json_formatter,
        level="INFO",
        serialize=True # if Falsewe handle serialization manually because we are handling the json in json_formatter
    )

    # File — JSON logs
    logger.add(
        log_dir/"structured_{time:YYYY-MM-DD}.json",
        #format=json_formatter,
        level="DEBUG",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        serialize=True
    )

    logger.info("JSON structured logging ready")


# ============================================================
# REQUEST LOGGER — one logger per HTTP request
# ============================================================
class RequestLogger:
    """
    Creates a request-scoped logger.
    Every log line from this request includes request_id.
    Makes it trivial to trace a single request in logs.
    """
    def __init__(self,request_id:str,method:str,path:str,user:str=None):
        self.request_id=request_id
        self.method=method
        self.path=path
        self.user=user
        self.start_time=datetime.now(timezone.utc)
        self._logger=logger.bind(
            request_id=request_id,
            method=method,
            path=path,
            user=user
        )
    
    def info(self,message:str,**kwargs):
        self._logger.bind(**kwargs).info(message)

    def debug(self, message: str, **kwargs):
        self._logger.bind(**kwargs).debug(message)

    def warning(self, message: str, **kwargs):
        self._logger.bind(**kwargs).warning(message)

    def error(self, message: str, **kwargs):
        self._logger.bind(**kwargs).error(message)

    def complete(self,status_code:int,**kwargs):
        duration=(datetime.now(timezone.utc)-self.start_time).total_seconds()*1000
        self._logger.bind(
            status_code=status_code,
            duration_ms=round(duration),
            **kwargs
        ).info("Request complete")

    def failed(self, error: str, status_code: int = 500, **kwargs):
        duration = (datetime.utcnow() - self.start_time).total_seconds() * 1000
        self._logger.bind(
            status_code=status_code,
            duration_ms=round(duration),
            error=error,
            **kwargs
        ).error("Request failed")


# ============================================================
# DOMAIN LOGGERS — one per subsystem
# ============================================================
auth_logger=logger.bind(subsystem="auth")
llm_logger     = logger.bind(subsystem="llm")
db_logger      = logger.bind(subsystem="database")
ws_logger      = logger.bind(subsystem="websocket")
rag_logger     = logger.bind(subsystem="rag")


def demo_domain_logger():
    print("\n=== Domain Loggers ===")

    auth_logger.bind(username="alice",ip="192.168.1.1").info("Login successfully")
    auth_logger.bind(username="bob",   ip="10.0.0.5", attempts=3).warning("Failed login attempt")
    auth_logger.bind(username="eve",   ip="1.2.3.4",  attempts=5).error("Account locked — brute force detected")

    # LLM events
    llm_logger.bind(model="gpt-4",    prompt_tokens=150, completion_tokens=500, cost_usd=0.02).info("Generation complete")
    llm_logger.bind(model="gpt-4",    timeout_s=10, retry=3).error("LLM call failed — all retries exhausted")
    llm_logger.bind(model="claude-3", tokens=800, fallback=True).warning("Using fallback model — OpenAI circuit open")

    # DB events
    db_logger.bind(query="SELECT users", duration_ms=45,  rows=10).debug("Query executed")
    db_logger.bind(query="INSERT post",  duration_ms=120, rows=1).debug("Insert completed")
    db_logger.bind(query="SELECT *",     duration_ms=8500).warning("Slow query detected")

    # RAG events
    rag_logger.bind(doc_id="doc_123", chunks=42, tokens=8500).info("Document ingested")
    rag_logger.bind(query="RAG pipelines", results=5, duration_ms=230).info("Retrieval complete")


# ============================================================
# SENSITIVE DATA MASKING
# ============================================================

class SafeLogger:
    """
    Logger that masks sensitive data automatically.
    NEVER log passwords, tokens, credit cards, SSNs.
    """

    SENSITIVE_FIELDS = {"password", "token", "api_key", "secret", "credit_card", "ssn"}

    def __init__(self):
        self._logger = logger.bind(subsystem="safe")

    def _mask(self, data: dict) -> dict:
        masked = {}
        for key, value in data.items():
            if any(sensitive in key.lower() for sensitive in self.SENSITIVE_FIELDS):
                masked[key] = "***MASKED***"
            else:
                masked[key] = value
        return masked

    def log_request(self, data: dict):
        safe_data = self._mask(data)
        self._logger.bind(**safe_data).info("Request data")

    def log_user_action(self, action: str, user: str, **kwargs):
        safe_kwargs = self._mask(kwargs)
        self._logger.bind(user=user, action=action, **safe_kwargs).info("User action")


def demo_safe_logging():
    print("\n=== Safe Logging (Sensitive Data Masking) ===")

    safe = SafeLogger()

    # This would be DANGEROUS without masking
    safe.log_request({
        "username":    "alice",
        "password":    "super_secret_123",    # ← masked
        "email":       "alice@example.com",
        "api_key":     "sk-abc123...",         # ← masked
        "action":      "login"
    })

    safe.log_user_action(
        action="update_profile",
        user="bob",
        new_email="bob@example.com",
        token="eyJhbGci...",                   # ← masked
        old_password="oldpass123"              # ← masked
    )






if __name__=="__main__":
    script_dir=Path(__file__).parent
    log_dir=script_dir/"logs"
    log_dir.mkdir(exist_ok=True)
    setup_json_logger(log_dir)
    demo_domain_logger()
    demo_safe_logging()