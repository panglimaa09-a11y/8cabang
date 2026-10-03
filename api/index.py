"""Vercel serverless entrypoint.
Vercel's Python runtime treats files under ``api/`` as serverless functions
and serves an exported ASGI ``app`` directly — no Mangum adapter needed.
All ``/api/*`` requests are rewritten here by ``vercel.json``; the static
frontend (index.html + frontend/) is served by Vercel's CDN.
"""
from backend.app.main import app  # noqa: F401  (Vercel looks for `app`)
