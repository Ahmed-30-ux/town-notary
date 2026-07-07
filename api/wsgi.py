"""WSGI entry point for Vercel deployment of FastAPI app."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from asgiref.wsgi import WsgiToAsgi
# FastAPI app is ASGI, wrap for WSGI
# Vercel Python runtime expects a WSGI callable named 'app'
from starlette.middleware.wsgi import WSGIMiddleware

# Use WSGI middleware approach - expose FastAPI through WSGI
# Actually, we re-export the FastAPI ASGI app directly
# Vercel supports ASGI natively since 2024
handler = app
