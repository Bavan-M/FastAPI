import os,sys
from loguru import logger
from datetime import datetime
from pathlib import Path

# ============================================================
# LOG LEVELS — when to use each
# ============================================================

# TRACE    → extremely detailed, even more than DEBUG
# DEBUG    → developer info, variable values, flow tracking
# INFO     → normal operation, user actions, milestones
# SUCCESS  → explicit success confirmations (Loguru-specific)
# WARNING  → something unexpected but not breaking
# ERROR    → something failed but app is still running
# CRITICAL → something failed and app may not recover

def demo_log_levels():
    print("\n=== Log Levels ===")

    logger.trace("Tracing execution very detailed")
    logger.debug("Debug info variable x=42")
    logger.info("User alice logged in")
    logger.success("Payment processed successfully")
    logger.warning("API rate limit at 80% _ approaching threshold")
    logger.error("LLM call failed - timeout after 10s")
    logger.critical("Database connection pool exhausted - system degraded")


# ============================================================
# CONFIGURATION — customize output format and destinations
# ============================================================

def setup_logger(log_dir:Path):
    """Configure Loguru for production use.
    Called once at app startup.
    """

    # Remove default handler
    logger.remove()

    # Handler 1 — Console output (human readable during development)
    logger.add(
        sys.stdout,
        level="DEBUG",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
            "{message}"
        ),
        colorize=True
    )

    # Handler 2 — All logs to file (rotating daily)
    log_file_path=log_dir/"app_{time:YYYY-MM-DD}.log"
    logger.add(
        log_file_path,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} | {message} | {extra}",
        rotation="00:00", # new file every midnight
        retention="30 days", # keep last 30 days    
        compression="zip", # compress old files
        enqueue=True # async write — won't slow down app
    )

    # Handler 3 — Errors only to separate file (easy monitoring)
    error_file_path=log_dir/"errors_{time:YYYY-MM-DD}.log"
    logger.add(
        error_file_path,
        level="ERROR",
        format="{time} | {level} | {name}:{function}:{line} | {message} | {extra}",
        rotation="1 week",
        retention="90 days",
        compression="zip",
        backtrace=True, # full traceback in error logs
        diagnose=True # variable values in traceback
    ) 
    logger.info("Logger configured successfully")



# ============================================================
# CONTEXT BINDING — add fields to all logs in a scope
# ============================================================
def demo_context_binding():
    print("\n=== Context Binding ===")
    # bind() creates a child logger with extra fields
    # All logs from this logger include request_id and user

    request_logger=logger.bind(
        request_id="abc-123",
        user="alice",
        path="/api/v1/generate"
    )

    request_logger.info("Request recieved")
    request_logger.debug("Calling LLM with prompt length=50")
    request_logger.info("LLM responds in 2.2 sec")
    request_logger.success("Request completed")

    # Original logger is unaffected
    logger.info("This log has no request id or user")



# ============================================================
# EXCEPTION LOGGING
# ============================================================

def demo_exception_handling():
    print("\n=== Exception Logging ===")

    # Option 1 — logger.exception() inside except block
    try:
        result=1/0
    except ZeroDivisionError:
        logger.exception("Division failed") # Automatically includes full traceback

    # Option 2 — logger.opt(exception=True)
    try:
        data={"key":"value"}
        _=data["missing_key"]
    except Exception as e:
        logger.opt(exception=True).error(f"Key not found {e}")

    # Option 3 — @logger.catch decorator
    @logger.catch
    def risky_fumction(x:int)->int:
        return 10/x
    risky_fumction(0) # caught and logged automatically



# ============================================================
# STRUCTURED DATA IN LOGS
# ============================================================
def demo_structured_data():
    print("\n=== Structured Data ===")

    # Log with extra context using bind
    logger.bind(
        user_id=42,
        model="gpt-4",
        tokens_used=1500,
        duration_ms=2300,
        cost_used=0.045
    ).info("LLM generation completed")

    # Log performance metrics
    logger.bind(
        endpoint="/api/v1/generate",
        method="POST",
        status_code=200,
        duration_ms=1234,
        request_size_bytes=256,
        response_size_bytes=1024
    ).info("HTTP request completed")

    # Log error with full context
    logger.bind(
        error_code="LLM_TIMEOUT",
        model="gpt-4",
        timeout_seconds=10,
        prompt_length=500,
        retry_attempt=3
    ).error("LLM call failed after all retries")


# ============================================================
# LOG LEVELS FILTERING — different levels per environment
# ============================================================
def setup_env_based_logging(environment:str="development"):
    """
    Development → show DEBUG and above
    Staging     → show INFO and above
    Production  → show WARNING and above (less noise)
    """
    logger.remove()

    level_map={
        "development":"DEBUG",
        "staging":"INFO",
        "production":"WARNING"
    }
    level=level_map.get(environment,"INFO")
    logger.add(
        sys.stdout,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        colorize=True
    )
    logger.info(f"Logging configured for environment: {environment} (level: {level})")

    


if __name__=="__main__":
    script_dir=Path(__file__).parent
    log_dir=script_dir/"logs"
    log_dir.mkdir(exist_ok=True)
    setup_logger(log_dir)
    setup_env_based_logging()
    demo_structured_data()
    demo_log_levels()
    demo_context_binding()
    demo_exception_handling()
    
