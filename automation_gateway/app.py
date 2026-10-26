import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from automation_gateway.api.jobs import router as jobs_router
from automation_gateway.core.config import get_settings


settings = get_settings()
app = FastAPI(title=settings.app_name, version=settings.app_version)

# --- CORS ---
default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

raw_origins = os.getenv("CORS_ORIGINS")
if raw_origins:
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
else:
    origins = default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "automation-gateway",
        "version": settings.app_version,
    }
