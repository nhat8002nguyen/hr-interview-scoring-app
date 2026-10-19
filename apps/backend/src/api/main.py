import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth.application.seed import seed_hr_account
from api.auth.application.service import AuthenticationService
from api.auth.infrastructure.refresh_token_storage import TransactionalRefreshTokenStorage
from api.auth.infrastructure.repository import TransactionalUserRepository
from api.auth.presentation.errors import register_authentication_exception_handlers
from api.auth.presentation.router import auth_router
from api.candidates.application.service import AnswersService, CandidatesService
from api.candidates.infrastructure.storage import LocalFileStorage
from api.candidates.infrastructure.unit_of_work import CandidatesUnitOfWork
from api.candidates.presentation.candidate_router import candidate_router
from api.candidates.presentation.errors import register_candidates_exception_handlers
from api.candidates.presentation.hr_router import hr_router
from api.catalog.application.service import CatalogService
from api.catalog.infrastructure.unit_of_work import CatalogUnitOfWork
from api.catalog.presentation.errors import register_catalog_exception_handlers
from api.catalog.presentation.router import catalog_router
from api.config import Settings
from api.health.router import router as health_router
from api.importing.application.service import ImportService
from api.importing.presentation.errors import register_importing_exception_handlers
from api.importing.presentation.router import import_router
from api.scoring.application.service import ScoringService
from api.scoring.application.worker import ScoringWorker
from api.scoring.infrastructure.llm import DeepSeekLlm
from api.scoring.infrastructure.reader import ScoringServiceReader
from api.scoring.infrastructure.unit_of_work import SqlAlchemyScoringUnitOfWork
from api.scoring.presentation.errors import register_scoring_exception_handlers
from api.scoring.presentation.router import scoring_router
from database import create_engine, create_session_factory
from iam import BcryptHashingService, JwtService, register_iam_exception_handlers


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings()
    engine = create_engine(configured.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        hashing = BcryptHashingService()
        jwt = JwtService(
            secret=configured.jwt_secret,
            algorithm=configured.jwt_algorithm,
            access_token_ttl_seconds=configured.jwt_access_token_ttl_seconds,
            refresh_token_ttl_seconds=configured.jwt_refresh_token_ttl_seconds,
        )
        auth = AuthenticationService(
            TransactionalUserRepository(session_factory),
            hashing,
            jwt,
            TransactionalRefreshTokenStorage(session_factory),
            min_password_length=configured.password_min_length,
        )
        candidates = CandidatesService(
            lambda: CandidatesUnitOfWork(session_factory),
            token_generator=lambda: secrets.token_urlsafe(32),
        )
        catalog = CatalogService(
            lambda: CatalogUnitOfWork(session_factory),
            counter=candidates,
        )
        scoring = ScoringService(lambda: SqlAlchemyScoringUnitOfWork(session_factory))
        file_storage = LocalFileStorage(configured.audio_storage_dir)
        answers = AnswersService(
            lambda: CandidatesUnitOfWork(session_factory),
            catalog,
            scoring,
            file_storage,
            max_submissions=configured.max_answer_submissions,
        )
        importing = ImportService(catalog, candidates, answers, file_storage)
        scoring_reader = ScoringServiceReader(scoring)
        llm = DeepSeekLlm(
            configured.deepseek_api_key,
            configured.deepseek_model,
            configured.deepseek_base_url,
        )

        app.state.hashing_service = hashing
        app.state.jwt_service = jwt
        app.state.authentication_service = auth
        app.state.candidates_service = candidates
        app.state.answers_service = answers
        app.state.catalog_service = catalog
        app.state.scoring_service = scoring
        app.state.scoring_reader = scoring_reader
        app.state.import_service = importing

        await scoring.reset_stale_claims(
            datetime.now(UTC) - timedelta(seconds=configured.scoring_lease_timeout_seconds)
        )

        stop_event = asyncio.Event()
        workers = [
            asyncio.create_task(
                ScoringWorker(
                    lambda: SqlAlchemyScoringUnitOfWork(session_factory),
                    llm,
                    max_attempts=configured.scoring_max_attempts,
                    poll_interval_seconds=configured.scoring_poll_interval_seconds,
                    stop_event=stop_event,
                ).run()
            )
            for _ in range(configured.scoring_workers)
        ]

        await seed_hr_account(
            session_factory,
            configured.seed_hr_email,
            configured.seed_hr_password,
            hashing,
        )

        try:
            yield
        finally:
            stop_event.set()
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            await llm.aclose()
            await engine.dispose()

    app = FastAPI(title="talotrace-api", lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = configured

    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["Content-Type", "Authorization", "X-Candidate-Token"],
    )

    register_iam_exception_handlers(app)
    register_authentication_exception_handlers(app)
    register_catalog_exception_handlers(app)
    register_candidates_exception_handlers(app)
    register_scoring_exception_handlers(app)
    register_importing_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(catalog_router)
    app.include_router(candidate_router)
    app.include_router(hr_router)
    app.include_router(scoring_router)
    app.include_router(import_router)

    return app


app = create_app()
