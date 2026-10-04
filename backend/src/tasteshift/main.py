import asyncio
import hashlib
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tasteshift.config import Settings
from tasteshift.domain import (
    Category,
    Coverage,
    Discovery,
    DiscoveryRequest,
    FeedbackRequest,
)
from tasteshift.qloo import ProviderError, QlooClient
from tasteshift.ranking import rank
from tasteshift.storage import DiscoveryRecord, FeedbackRecord, SessionRecord


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_app(settings: Settings | None = None, transport=None) -> FastAPI:
    settings = settings or Settings()
    engine = create_async_engine(settings.database_url.get_secret_value())
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            base_url=settings.qloo_base_url,
            timeout=settings.qloo_timeout,
            transport=transport,
            follow_redirects=False,
        ) as http:
            key = settings.qloo_api_key.get_secret_value() if settings.qloo_api_key else None
            app.state.qloo = QlooClient(http, key)
            yield
        await engine.dispose()

    app = FastAPI(title="TasteShift", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"detail": {"code": exc.code}})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content={"detail": {"code": "storage_unavailable"}})

    async def get_session(request: Request, response: Response, *, create=False) -> str:
        token = request.cookies.get("tasteshift_session")
        async with sessions() as db:
            if token:
                record = await db.scalar(
                    select(SessionRecord).where(
                        SessionRecord.token_hash == digest(token),
                        SessionRecord.expires_at > datetime.now(UTC),
                    )
                )
                if record:
                    return record.id
            if not create:
                raise HTTPException(404, "Discovery not found")
            token = secrets.token_urlsafe(32)
            record = SessionRecord(
                id=str(uuid4()),
                token_hash=digest(token),
                expires_at=datetime.now(UTC) + timedelta(days=settings.session_days),
            )
            db.add(record)
            await db.commit()
        response.set_cookie(
            "tasteshift_session",
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.session_days * 86400,
        )
        return record.id

    def check_origin(request: Request):
        if request.headers.get("origin") != settings.app_origin:
            raise HTTPException(403, "Invalid request origin")

    async def owned_discovery(id: UUID, session_id: str) -> DiscoveryRecord:
        async with sessions() as db:
            record = await db.scalar(
                select(DiscoveryRecord).where(
                    DiscoveryRecord.id == str(id),
                    DiscoveryRecord.session_id == session_id,
                )
            )
        if not record:
            raise HTTPException(404, "Discovery not found")
        return record

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "qloo_configured": bool(settings.qloo_api_key)}

    @app.get("/api/ready")
    async def ready():
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            await connection.execute(select(SessionRecord.id).limit(1))
        return {"status": "ready"}

    @app.get("/api/entities/search")
    async def search(
        request: Request,
        q: str = Query(min_length=2, max_length=120),
        category: Category = Category.artist,
    ):
        if len(q.strip()) < 2:
            raise HTTPException(422, "Enter at least two characters")
        return {"items": await request.app.state.qloo.search(q.strip(), category)}

    @app.post("/api/discoveries", response_model=Discovery)
    async def discover(body: DiscoveryRequest, request: Request, response: Response):
        check_origin(request)
        request_key = request.headers.get("idempotency-key")
        if not request_key or not 1 <= len(request_key) <= 64:
            raise HTTPException(422, "Provide an Idempotency-Key of 1–64 characters")
        if not settings.qloo_api_key:
            raise ProviderError("provider_not_configured")
        session_id = await get_session(request, response, create=True)
        input_hash = digest(body.model_dump_json())
        async with sessions() as db:
            existing = await db.scalar(
                select(DiscoveryRecord).where(
                    DiscoveryRecord.session_id == session_id,
                    DiscoveryRecord.request_key == request_key,
                )
            )
            if existing:
                if existing.input_hash != input_hash:
                    raise HTTPException(
                        409, "Idempotency-Key already used for another request"
                    ) from None
                return Discovery.model_validate(existing.result)
            feedback = list(
                (
                    await db.scalars(
                        select(FeedbackRecord).where(
                            FeedbackRecord.session_id == session_id,
                        )
                    )
                ).all()
            )
        excluded = set(body.seed_ids) | {
            UUID(item.entity_id) for item in feedback if item.action != "save"
        }
        # Positive signals are deliberately bounded; hard exclusions win.
        positives = [UUID(item.entity_id) for item in feedback if item.action == "save"]
        signal_ids = list(dict.fromkeys(body.seed_ids + positives))[:8]
        qloo = request.app.state.qloo
        try:
            async with asyncio.timeout(settings.discovery_timeout):
                seeds = await qloo.entities(signal_ids)
                if {e.id for e in seeds} != set(signal_ids):
                    raise HTTPException(422, "Some interests could not be resolved")
                results = await asyncio.gather(
                    *(qloo.candidates(signal_ids, category, excluded) for category in Category),
                    return_exceptions=True,
                )
        except TimeoutError as exc:
            raise ProviderError("provider_timeout") from exc
        items, coverage = [], []
        failures = []
        for category, result in zip(Category, results, strict=True):
            if isinstance(result, ProviderError):
                failures.append(result)
                coverage.append(Coverage(category=category, status=result.code))
            elif isinstance(result, BaseException):
                raise result
            else:
                selected, supported = rank(result, seeds, excluded, body.level)
                items.extend(selected)
                coverage.append(
                    Coverage(
                        category=category,
                        status="ok" if selected else "empty",
                        exploration_supported=supported,
                    )
                )
        if len(failures) == len(Category):
            raise failures[0]
        discovery = Discovery(id=uuid4(), level=body.level, items=items, coverage=coverage)
        async with sessions() as db:
            db.add(
                DiscoveryRecord(
                    id=str(discovery.id),
                    session_id=session_id,
                    request_key=request_key,
                    input_hash=input_hash,
                    created_at=datetime.now(UTC),
                    result=discovery.model_dump(mode="json"),
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                existing = await db.scalar(
                    select(DiscoveryRecord).where(
                        DiscoveryRecord.session_id == session_id,
                        DiscoveryRecord.request_key == request_key,
                    )
                )
                if existing is None:
                    raise
                if existing.input_hash != input_hash:
                    raise HTTPException(
                        409, "Idempotency-Key already used for another request"
                    ) from None
                return Discovery.model_validate(existing.result)
        return discovery

    @app.get("/api/discoveries/{id}", response_model=Discovery)
    async def retrieve(id: UUID, request: Request, response: Response):
        session_id = await get_session(request, response)
        return (await owned_discovery(id, session_id)).result

    @app.post("/api/discoveries/{id}/feedback")
    async def react(id: UUID, body: FeedbackRequest, request: Request, response: Response):
        check_origin(request)
        session_id = await get_session(request, response)
        discovery = await owned_discovery(id, session_id)
        allowed = {item["entity"]["id"] for item in discovery.result["items"]}
        if str(body.entity_id) not in allowed:
            raise HTTPException(422, "Choose an item from this discovery")
        async with sessions() as db:
            item = await db.scalar(
                select(FeedbackRecord).where(
                    FeedbackRecord.session_id == session_id,
                    FeedbackRecord.entity_id == str(body.entity_id),
                )
            )
            if item:
                item.action = body.action.value
                item.discovery_id = str(id)
            else:
                db.add(
                    FeedbackRecord(
                        id=str(uuid4()),
                        session_id=session_id,
                        discovery_id=str(id),
                        entity_id=str(body.entity_id),
                        action=body.action.value,
                    )
                )
            await db.commit()
        return {"status": "saved"}

    return app


app = create_app()
