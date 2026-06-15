import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    ambulances,
    analytics,
    auth,
    dispatch,
    driver,
    hospitals,
    incidents,
    notifications,
    tracking,
    users,
)
from app.core.config import settings
from app.core.database import Base, engine
from app.ws import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (idempotent) and capture the running loop so sync
    # route handlers can broadcast websocket events from the threadpool.
    Base.metadata.create_all(bind=engine)
    manager.set_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="LifeLine AI", version="1.0.0", lifespan=lifespan)

origins = ["*"] if settings.CORS_ORIGINS == "*" else [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (
    auth.router,
    users.router,
    hospitals.router,
    ambulances.router,
    incidents.router,
    dispatch.router,
    driver.router,
    tracking.router,
    analytics.router,
    notifications.router,
    admin.router,
):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "lifeline-ai"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep the socket open; clients may send pings. We don't require any
            # particular inbound payload — this is a broadcast-only channel.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
