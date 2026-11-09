import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))


@dataclass(frozen=True)
class Settings:
    base_url: str
    login_name: str
    password: str
    timeout: float


def load_settings() -> Settings:
    base_url = os.getenv("BASE_URL", "http://localhost:9999/jshERP-boot").rstrip("/")
    login_name = os.getenv("LOGIN_NAME", "").strip()
    password = os.getenv("PASSWORD", "")
    missing = [name for name, value in (("LOGIN_NAME", login_name), ("PASSWORD", password)) if not value]
    if missing:
        raise RuntimeError(f"缺少环境变量 {', '.join(missing)}；请复制 .env.example 为 .env 并填写")
    return Settings(
        base_url=base_url,
        login_name=login_name,
        password=password,
        timeout=float(os.getenv("TIMEOUT", "10")),
    )
