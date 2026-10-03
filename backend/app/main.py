from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.chat import router as chat_router
from .api.routes import router
from .config import get_settings

settings = get_settings()
app = FastAPI(title="Swiggy AI Food Assistant API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(chat_router)
