import asyncio
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from tortoise.contrib.fastapi import register_tortoise
from loguru import logger
from pathlib import Path

from routers.scan_router import router as scan_router
from utils.queue_manager import scan_queue

# Configure loguru
logger.remove()
logger.add(
    sys.stdout,
    format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle FastAPI app startup and shutdown"""
    # Startup
    logger.info("Starting PortRecon API")
    queue_task = asyncio.create_task(scan_queue.process())
    yield
    # Shutdown
    logger.info("Shutting down PortRecon API")
    queue_task.cancel()
    try:
        await queue_task
    except asyncio.CancelledError:
        pass


# Initialize FastAPI app
app = FastAPI(
    title="PortRecon",
    description="Port reconnaissance scanner API",
    version="0.1.0",
    lifespan=lifespan,
)

# Register Tortoise ORM
register_tortoise(
    app,
    db_url="sqlite://db.sqlite3",
    modules={"models": ["models.scan"]},
    generate_schemas=True,
    add_exception_handlers=True,
)

# Include routers
app.include_router(scan_router)

# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/")
async def root():
    """Serve index.html"""
    return FileResponse("templates/index.html", media_type="text/html")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )