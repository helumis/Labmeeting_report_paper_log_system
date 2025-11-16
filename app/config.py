# /app/app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str

    # 👇 Add the missing environment variables as fields
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_port: str # Keeping this as str because the trace shows input_type=str

    class Config:
        env_file = ".env"

settings = Settings()