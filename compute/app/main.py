"""FastAPI entrypoint for the compute service.

Run it standalone:   uvicorn app.main:app --reload --port 8000
Then open http://localhost:8000/ — the service also serves the dashboard so the whole
vertical slice runs from one process during development. In the full architecture the
frontend is fronted by the Spring Boot gateway instead; CORS is open to localhost so either
wiring works.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(
    title="Route Resilience — Compute Service",
    description="Graph-theoretic criticality analysis for urban road networks.",
    version="0.1.0",
)

# Local dev origins (vanilla frontend on :5500/:8000, Spring gateway on :8080).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router)


@app.middleware("http")
async def no_store_static(request, call_next):
    # The dashboard is served straight off disk during development; tell the browser not to
    # cache it so an edit to the CSS/JS shows up on a plain reload instead of going stale.
    response = await call_next(request)
    if not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


# Serve the dashboard last so /api/* keeps priority over the catch-all static mount.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
