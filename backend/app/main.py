"""FastAPI application entrypoint.

- Mounts every /api router, exposes GET /api/health.
- Bootstraps the first owner account from BOOTSTRAP_OWNER_EMAIL/PASSWORD
  when the profiles table is empty (one-shot; ignored afterwards).
- Serves the frontend statically: FRONTEND_DIR mounted at "/", with
  index.html as the SPA fallback (only if the directory exists).
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from contextlib import asynccontextmanager

from . import db as db_module
from .api import (
    audit, auth, branches, expenses, purchases, reports, returns,
    sales, stocktakes, transactions, transfers, users,
)
from .config import settings
from .models import Base, Profile
from .security.auth import hash_password

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.DB_AUTO_CREATE and db_module.engine is not None:
        Base.metadata.create_all(db_module.engine)
    _bootstrap_owner()
    yield


app = FastAPI(title="Sistem Manajemen Penjualan Telur 8 Cabang",
              version=settings.APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routers ───────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(branches.router)
app.include_router(purchases.router)
app.include_router(sales.router)
app.include_router(expenses.router)
app.include_router(returns.router)
app.include_router(stocktakes.router)
app.include_router(transfers.router)
app.include_router(transactions.router)
app.include_router(reports.router)
app.include_router(audit.router)


@app.get("/api/health")
def health():
    db_status = "down"
    if db_module.engine is not None:
        try:
            with db_module.engine.connect() as conn:
                conn.execute(select(1))
            db_status = "up"
        except Exception:
            db_status = "down"
    return {"status": "ok", "db": db_status, "version": settings.APP_VERSION}


def _bootstrap_owner() -> None:
    """Create the first owner from env, but ONLY when no profiles exist."""
    if db_module.SessionLocal is None:
        return
    email = settings.BOOTSTRAP_OWNER_EMAIL.strip().lower()
    password = settings.BOOTSTRAP_OWNER_PASSWORD
    if not email or not password:
        return
    session = db_module.SessionLocal()
    try:
        count = session.scalar(select(func.count()).select_from(Profile))
        if count and count > 0:
            return  # owner already exists — bootstrap is ignored
        session.add(Profile(
            email=email, full_name="Owner",
            role="owner", password_hash=hash_password(password)))
        session.commit()
    finally:
        session.close()


# ── Static frontend (served last so /api routes win) ──────────────
FRONTEND_DIR = settings.FRONTEND_DIR
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    @app.exception_handler(404)
    async def spa_fallback(request, exc):
        # API 404s stay JSON; everything else falls back to index.html.
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        index = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        return JSONResponse(status_code=404, content={"detail": "Not found"})
