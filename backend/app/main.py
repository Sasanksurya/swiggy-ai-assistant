from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.chat import router as chat_router
from .api.routes import router
from .api.swiggy_auth import router as swiggy_auth_router
from .config import get_settings
from .observability import configure_tracing

settings = get_settings()
configure_tracing(settings)
app = FastAPI(title="Swiggy AI Food Assistant API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(chat_router)
app.include_router(swiggy_auth_router)
