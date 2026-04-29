"""
Entry point — creates the FastAPI app, registers routers, and defines lifespan.

This file should stay small. If you're adding logic here, it probably belongs
in app/services/ or app/routes/ instead.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routes.chat import router as chat_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("copilot")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks. Wire long-lived resources here (e.g. DB pool, agent init)."""
    logger.info("Clinical Co-Pilot service starting up")
    logger.info("ANTHROPIC_API_KEY present: %s", bool(os.getenv("ANTHROPIC_API_KEY")))
    logger.info("LANGSMITH_API_KEY present:  %s", bool(os.getenv("LANGSMITH_API_KEY")))
    yield
    logger.info("Clinical Co-Pilot service shutting down")


app = FastAPI(
    title="Clinical Co-Pilot AI Service",
    description="AI reasoning layer for OpenEMR Clinical Co-Pilot. Not publicly exposed.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(chat_router)


# Global error handler — returns safe JSON instead of leaking a Python traceback
# to the PHP bridge (and potentially into the browser via the chat panel).
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception in %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "answer": "The AI service encountered an internal error. Please try again.",
            "citations": [],
            "verification_status": "fail",
            "warnings": ["Internal service error — see server logs"],
        },
    )
