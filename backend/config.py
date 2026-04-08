import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/studio.db")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
AGENTS_DIR = os.getenv("AGENTS_DIR", "./agents")
PROJECTS_DIR = os.getenv("PROJECTS_DIR", "./projects")
