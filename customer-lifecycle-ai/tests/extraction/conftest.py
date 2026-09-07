"""Ensure project root is on sys.path for extraction tests."""
import sys
from pathlib import Path

_proj = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_proj))
