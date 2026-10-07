"""Filesystem locations shared by all pipeline steps."""

from pathlib import Path

PIPELINE_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PIPELINE_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
# Hand-made review decisions, versioned with the code.
REVIEW_DIR = PIPELINE_ROOT / "review"
