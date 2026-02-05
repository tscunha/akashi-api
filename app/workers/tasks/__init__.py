"""
AKASHI MAM API - Worker Tasks
"""

from app.workers.tasks.metadata import extract_metadata
from app.workers.tasks.proxy import generate_proxy
from app.workers.tasks.thumbnail import generate_thumbnail

__all__ = [
    "extract_metadata",
    "generate_proxy",
    "generate_thumbnail",
]
