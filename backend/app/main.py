"""
AI Ranker V2 - Prompter Only
Phase-1: FastAPI + Neon (no Redis/Celery)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Import our database and models
from app.db.database import init_db
from app.api.routes import api_router
from app.api.errors import APIError
from app.core.config import get_settings

# Get settings
settings = get_settings()

# Configure logging
log_level = settings.log_level.upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("Starting AI Ranker V2 - version 2.7, phase 1")
    logger.info("Phase-1 Mode: FastAPI + Neon (no Redis/Celery)")
    
    # Initialize database
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    
    yield
    
    logger.info("Shutting down AI Ranker V2")

# Create app
app = FastAPI(
    title="AI Ranker V2",
    version="2.7.0",
    description="Prompt Immutability Testing Platform",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["https://airanker.ai"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add API error handler
from fastapi.responses import JSONResponse

@app.exception_handler(APIError)
async def api_error_handler(request, exc: APIError):
    """Handle structured API errors"""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    """Global JSON error handler to prevent HTML 500s"""
    request_id = request.headers.get("x-request-id", "-")
    logger.exception("Unhandled exception rid=%s", request_id)
    return JSONResponse(
        content={"error": "internal_error", "request_id": request_id},
        status_code=500
    )

# Include API routes
app.include_router(api_router)

# Include preflight routes
from app.routers import preflight
app.include_router(preflight.router)

@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "service": "AI Ranker V2",
        "version": "2.7.0",
        "phase": "Phase-1 (FastAPI + Neon)",
        "docs": "/docs",
        "health": "/health",
        "api": "/v1"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.7.0",
        "phase": "1",
        "components": {
            "database": "operational",
            "canonicalization": "operational",
            "provider_cache": "operational"
        }
    }