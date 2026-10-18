from fastapi import FastAPI

from api.config import Settings
from api.health.router import router as health_router
from database import create_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings()

    app = FastAPI(title="talotrace-api")
    app.state.engine = create_engine(configured.database_url)
    app.include_router(health_router)
    return app


app = create_app()
