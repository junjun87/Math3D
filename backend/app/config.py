from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Math3D API"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://math3d:math3d_secret@localhost:5432/math3d"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://math3d:math3d_secret@localhost:5432/math3d"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.anthropic.com"
    LLM_MODEL: str = "claude-sonnet-5"

    # Alibaba Cloud OCR
    ALIBABA_CLOUD_ACCESS_KEY_ID: str = ""
    ALIBABA_CLOUD_ACCESS_KEY_SECRET: str = ""
    SERVER_HOST: str = "http://59.110.93.243:8000"  # OCR API 通过 URL 下载图片

    # File Storage
    UPLOAD_DIR: str = "./uploads"
    LESSON_DIR: str = "./lessons"
    MAX_UPLOAD_SIZE_MB: int = 10
    OCR_MAX_IMAGE_DIMENSION: int = 4096

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://59.110.93.243:5173", "http://59.110.93.243"]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
