from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import admin_users, chat, conversations, documents, health
from app.core.config import get_settings

settings = get_settings()
# create application instance (Swagger)
app = FastAPI(
    title="KnowVeris IA",
    description=(
        "Self-hosted RAG assistant for bank employees. "
        "Answers are grounded in indexed internal documents only."
    ),
    version="0.1.0",
)
# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(documents.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
app.include_router(admin_users.router, prefix="/api/v1")
