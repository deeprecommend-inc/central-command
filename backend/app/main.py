from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

from .core.config import settings
from .models.database import init_db
from .services.redis_service import redis_service
from .api import oauth, runs, drafts, metrics, schedules, exports, account_generation, proxy_ips, personas, browser_actions, user_agent, llm_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager"""
    # Startup
    await init_db()
    await redis_service.connect()

    yield

    # Shutdown
    await redis_service.disconnect()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(browser_actions.router, tags=["Browser Actions"])  # New prompt-based API
app.include_router(oauth.router, prefix="/oauth", tags=["OAuth (Legacy)"])
app.include_router(runs.router, prefix="/runs", tags=["Runs"])
app.include_router(drafts.router, prefix="/drafts", tags=["AI Drafts"])
app.include_router(metrics.router, prefix="/metrics", tags=["Metrics"])
app.include_router(schedules.router, tags=["Campaigns"])
app.include_router(exports.router, tags=["Exports"])
app.include_router(account_generation.router, tags=["Account Generation"])
app.include_router(proxy_ips.router, tags=["Proxy IPs"])
app.include_router(personas.router, tags=["Personas"])
app.include_router(user_agent.router, tags=["User-Agent"])
app.include_router(llm_settings.router, tags=["LLM Settings"])


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8006,
        reload=settings.DEBUG
    )
