from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.config import get_settings
from app.database import init_db
from app.api import upload, problems, lessons, users

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.LESSON_DIR, exist_ok=True)
    await init_db()  # Uncomment for dev without Alembic
    yield
    # Shutdown


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for uploaded images and lessons
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.LESSON_DIR, exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")
app.mount("/static/lessons", StaticFiles(directory=settings.LESSON_DIR), name="lessons")

# API Routes
app.include_router(upload.router, prefix="/api/v1", tags=["Upload"])
app.include_router(problems.router, prefix="/api/v1", tags=["Problems"])
app.include_router(lessons.router, prefix="/api/v1", tags=["Lessons"])
app.include_router(users.router, prefix="/api/v1", tags=["Users"])


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": "0.1.0"}
