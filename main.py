import sys
import os

# Ensure the 'backend' directory is in the Python path so absolute imports like 'from config import ...' work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# Import the FastAPI application instance
from backend.main import app

# This file serves as the official FastAPI entrypoint for hosting platforms (e.g., Vercel, Render)
