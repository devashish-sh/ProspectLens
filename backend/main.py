# backend/main.py
# ProspectLens — FastAPI Application Entry Point
#
# This is the file that STARTS the entire backend server.
# Run it with: uvicorn main:app --reload --port 8000
#
# What happens when you start this file:
# 1. FastAPI app is created
# 2. Database tables are created (if they don't exist yet)
# 3. All API routes are registered
# 4. Server starts listening on http://localhost:8000

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database.db import create_db_and_tables
from api.routes_health  import router as health_router
from api.routes_leads   import router as leads_router
from api.routes_batches import router as batches_router
from api.routes_export  import router as export_router


# ==============================================================================
# LIFESPAN — runs on startup and shutdown
# create_db_and_tables() is called once when server starts
# Safe to call multiple times — never drops existing data
# ==============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[ProspectLens] Starting backend server...")
    create_db_and_tables()
    print("[ProspectLens] Backend ready at http://localhost:8000")
    yield
    print("[ProspectLens] Backend shutting down.")


# ==============================================================================
# FASTAPI APP
# ==============================================================================

app = FastAPI(
    title="ProspectLens API",
    description="Local backend for ProspectLens Chrome Extension — Indian B2B Lead Collection",
    version="1.0.0",
    lifespan=lifespan
)


# ==============================================================================
# CORS MIDDLEWARE
# Allows the Chrome Extension to call this API.
# Without this, the browser will block all requests from the extension.
# ==============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Chrome extension can call from any origin
    allow_credentials=True,
    allow_methods=["*"],        # GET, POST, PUT, DELETE all allowed
    allow_headers=["*"],
)


# ==============================================================================
# REGISTER ALL ROUTES
# Each router handles a specific group of endpoints
# ==============================================================================

app.include_router(health_router,   prefix="/api")
app.include_router(leads_router,    prefix="/api")
app.include_router(batches_router,  prefix="/api")
app.include_router(export_router,   prefix="/api")


# ==============================================================================
# ROOT ENDPOINT
# Quick check — visit http://localhost:8000 in browser
# ==============================================================================

@app.get("/")
def root():
    return {
        "app": "ProspectLens",
        "version": "1.0.0",
        "status": "running",
        "docs": "http://localhost:8000/docs"
    }