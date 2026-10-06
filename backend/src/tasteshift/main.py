import hashlib
import secrets
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tasteshift.agent import AgentAdmission, AgentRunner
from tasteshift.config import Settings
from tasteshift.discovery import DiscoveryService, UnresolvedInterests, feedback_signals
from tasteshift.domain import (
    Category,
    Discovery,
    DiscoveryRequest,
    FeedbackRequest,
)
from tasteshift.model import gemini_model
from tasteshift.qloo import ProviderError, QlooClient
from tasteshift.storage import DiscoveryRecord, FeedbackRecord, SessionRecord


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_app(settings: Settings | None = None, transport=None, *, agent_model=None) -> FastAPI:
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
            async with AsyncExitStack() as stack:
                stack.push_async_callback(engine.dispose)
                model = agent_model
                if model is None and settings.gemini_api_key:
                    model = await stack.enter_async_context(gemini_model(settings))
                app.state.runner = AgentRunner(settings, model) if model is not None else None
                app.state.admission = AgentAdmission(settings)
                app.state.discovery = DiscoveryService(settings, app.state.qloo, app.state.runner)
                yield

    app = FastAPI(title="TasteShift", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine

    @app.exception_handler(ProviderError)
    async def provider_error(request, exc):
        from fastapi.responses import JSONResponse

        status = 429 if exc.code == "agent_rate_limit" else 503
        return JSONResponse(status_code=status, content={"detail": {"code": exc.code}})

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
        return {
            "status": "ok",
            "qloo_configured": bool(settings.qloo_api_key),
            "agent_configured": app.state.runner is not None,
        }

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
        if body.intent is not None and request.app.state.runner is None:
            raise ProviderError("agent_not_configured")
        if not settings.qloo_api_key:
            raise ProviderError("provider_not_configured")
        session_id = await get_session(request, response, create=True)
        input_hash = digest(body.model_dump_json(exclude_none=True))
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
        excluded, positives = feedback_signals(body, feedback)
        try:
            if body.intent:
                async with request.app.state.admission.enter(session_id):
                    discovery = await request.app.state.discovery.create(body, excluded, positives)
            else:
                discovery = await request.app.state.discovery.create(body, excluded, positives)
        except UnresolvedInterests as exc:
            raise HTTPException(422, "Some interests could not be resolved") from exc
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
            try:
                await db.commit()
            except IntegrityError:
                # Another request may have inserted this same feedback key after our read.
                await db.rollback()
                existing = await db.scalar(
                    select(FeedbackRecord).where(
                        FeedbackRecord.session_id == session_id,
                        FeedbackRecord.entity_id == str(body.entity_id),
                    )
                )
                if existing is None:
                    raise
                existing.action = body.action.value
                existing.discovery_id = str(id)
                await db.commit()
        return {"status": "saved"}

    return app


app = create_app()
