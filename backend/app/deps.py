from fastapi import Request

from app.config import Settings
from app.store import Store


def get_store(request: Request) -> Store:
    return request.app.state.store


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings
