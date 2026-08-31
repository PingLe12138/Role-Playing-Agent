from routers.auth_routes import router as auth_router
from routers.characters import router as characters_router
from routers.chat import router as chat_router
from routers.config import router as config_router
from routers.misc import router as misc_router
from routers.sessions import router as sessions_router
from routers.worldview import router as worldview_router

__all__ = [
    "auth_router",
    "characters_router",
    "chat_router",
    "config_router",
    "misc_router",
    "sessions_router",
    "worldview_router",
]