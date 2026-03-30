from contextlib import asynccontextmanager
import logging
import subprocess

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.chapters import router as chapters_router
from .api.acx import router as acx_router
from .api.exports import router as exports_router
from .api.issues import router as issues_router
from .api.jobs import router as jobs_router
from .api.projects import router as projects_router
from .config import settings
from .db import init_db

logger = logging.getLogger(__name__)
ffmpeg_available = False
ffprobe_available = False


def check_command_available(command: str) -> bool:
    try:
        completed = subprocess.run(
            [command, "-version"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        logger.warning("%s is not available on PATH.", command)
        return False

    if completed.returncode != 0:
        logger.warning("%s returned a non-zero exit code during startup health check.", command)
        return False

    return True


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    startup_health_checks()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)
app.include_router(chapters_router)
app.include_router(acx_router)
app.include_router(issues_router)
app.include_router(exports_router)
app.include_router(jobs_router)

def startup_health_checks():
    global ffmpeg_available, ffprobe_available

    ffmpeg_available = check_command_available("ffmpeg")
    ffprobe_available = check_command_available("ffprobe")


@app.get("/health")
def health():
    return {
        "ok": True,
        "app": settings.app_name,
        "ffmpeg_available": ffmpeg_available,
        "ffprobe_available": ffprobe_available,
    }
