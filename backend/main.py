from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from graph.models import HealthResponse
from api.routes import router
from api.websocket import ws_router
from graph.redis_store import store
from db.mongo import mongo_db

app = FastAPI(
    title="AgentOS",
    description="Multi-agent task orchestration framework",
    version="0.1.0",
    debug=settings.debug,
)

# ---------------------------------------------------------------------------
# CORS — allow the React dev server + production Vercel URL
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "https://*.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Startup / Shutdown events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    """Connect to Redis and MongoDB on startup"""
    await store.connect()
    await mongo_db.connect()
    print(f"✅ Connected to Redis")
    
    # Safe check for MongoDB connection
    if hasattr(mongo_db, '_client') and mongo_db._client is not None:
        print("✅ MongoDB connected")
    else:
        print("⚠️ MongoDB not connected (runs will not be saved to history)")


@app.on_event("shutdown")
async def shutdown():
    """Disconnect from Redis and MongoDB"""
    await store.disconnect()
    await mongo_db.disconnect()
    print("🔌 Disconnected")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(router, prefix="/api")
app.include_router(ws_router, prefix="/api")  # ✅ ADD THIS LINE


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health():
    return HealthResponse()


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)