from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers.dashboard import router as dashboard_router
from routers.exfil import router as exfil_router, sessions_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Epidemic Lab // Mock C2", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(exfil_router, prefix="/exfil")
app.include_router(sessions_router)
app.include_router(dashboard_router)
