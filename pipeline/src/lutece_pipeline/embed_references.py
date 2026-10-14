"""Turn the reference photos into vectors with the image model.

Each photo that the fetch step downloaded goes through the model, in the
form of the model and with the framing asked for. The vectors of one form and
one framing make one file, so that the retrieval evaluation can compare them.

Run with: uv run python -m lutece_pipeline.embed_references
"""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from lutece_pipeline import export_model, fetch_reference_photos, vision
from lutece_pipeline.paths import INTERIM_DIR

logger = logging.getLogger(__name__)

INDEX_PARQUET = fetch_reference_photos.INDEX_PARQUET
PHOTOS_FOLDER = fetch_reference_photos.PHOTOS_FOLDER
MODELS_FOLDER = export_model.MODELS_FOLDER
EMBEDDINGS_FOLDER = INTERIM_DIR / "embeddings"

EMBEDDINGS_SCHEMA = pa.schema(
    [
        ("title", pa.string()),
        ("vector", pa.list_(pa.float32(), vision.DIMENSIONS)),
    ]
)


def embeddings_name(model: str, framing: str) -> str:
    """Name the file of the vectors that a form of the model gives with a framing."""
    return f"{model}-{framing}.parquet"


def write_embeddings(
    titles: Sequence[str], vectors: vision.Vectors, path: Path
) -> None:
    """Write one line per photo: its title and its vector."""
    flat = pa.array(vectors.astype(np.float32).ravel(), type=pa.float32())
    column = pa.FixedSizeListArray.from_arrays(flat, vision.DIMENSIONS)
    table = pa.Table.from_arrays(
        [pa.array(list(titles), type=pa.string()), column], schema=EMBEDDINGS_SCHEMA
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def read_embeddings(path: Path) -> tuple[list[str], vision.Vectors]:
    """Read the titles of the photos and their vectors, one line each."""
    table = pq.read_table(path)
    flat = table["vector"].combine_chunks().values.to_numpy(zero_copy_only=False)
    return table["title"].to_pylist(), flat.reshape(-1, vision.DIMENSIONS)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Turn the reference photos into vectors with the image model."
    )
    parser.add_argument(
        "--model",
        choices=sorted(export_model.FILES),
        default="float32",
        help="the form of the model to run (default: as trained)",
    )
    parser.add_argument(
        "--framing",
        choices=vision.FRAMINGS,
        default="crop",
        help="how a photo is brought to a square (default: its centre)",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    index = pd.read_parquet(INDEX_PARQUET).drop_duplicates("title")
    titles = list(index["title"])
    paths = [PHOTOS_FOLDER / path for path in index["path"]]
    model = vision.open_model(MODELS_FOLDER / export_model.FILES[args.model])
    vectors = vision.embed_photos(model, paths, args.framing)

    destination = EMBEDDINGS_FOLDER / embeddings_name(args.model, args.framing)
    write_embeddings(titles, vectors, destination)
    logger.info("Wrote the vectors of %d photos to %s", len(titles), destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
