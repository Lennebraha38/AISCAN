"""Vercel serverless entry point — FastAPI uygulamasini sunar."""
import sys
import os

# Backend dizinini Python path'e ekle
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, backend_dir)

from app.main import app  # noqa: E402
