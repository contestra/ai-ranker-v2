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

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("Starting AI Ranker V2 - Prompter")
    logger.info(f"Phase-1 Mode: FastAPI + Neon (no Redis/Celery)")
    logger.info(f"Execution Mode: {os.getenv('EXECUTION_MODE', 'sync')}")
    yield
    logger.info("Shutting down AI Ranker V2")

# Create app
app = FastAPI(
    title="AI Ranker V2 - Prompter",
    version="2.0.0",
    description="Prompt Immutability Testing System",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "name": "AI Ranker V2",
        "version": "2.0.0",
        "phase": "1",
        "mode": os.getenv("EXECUTION_MODE", "sync"),
        "features": ["prompter", "immutability", "als"]
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "phase": "1",
        "database": "neon",
        "redis": False,
        "celery": False
    }

# TODO: Import routers once implemented
# from app.api import prompt_tracking_v2
# app.include_router(prompt_tracking_v2.router, prefix="/api/v2")
