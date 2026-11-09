import pytest
import requests

from client import ErpClient
from config import load_settings


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def client(settings):
    c = ErpClient(settings)
    try:
        c.login()
    except requests.ConnectionError as exc:
        pytest.exit(
            f"无法连接后端 {settings.base_url}，请先启动 jshERP-boot（9999）后重试。\n{exc}",
            returncode=2,
        )
    return c
