# src/__init__.py

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

from .process_lineup import yahoo_dfs
__all__ = ["yahoo_dfs"]  # Specifies the public API for this package