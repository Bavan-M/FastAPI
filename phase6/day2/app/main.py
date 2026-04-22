import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from app.routes import router


def create_app() -> FastAPI:
    """
    Factory function — creates a fresh app instance.
    Critical for testing — each test gets a clean app.
    """
    app = FastAPI(title="Testable Gen AI API", version="1.0.0")
    app.include_router(router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()