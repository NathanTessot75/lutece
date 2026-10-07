"""Typed tables shared by the pipeline steps: one explicit Arrow schema per output."""

from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def from_rows(rows: Sequence[Mapping[str, object]], schema: pa.Schema) -> pd.DataFrame:
    """Build an Arrow-backed frame from plain Python rows, enforcing the schema."""
    table = pa.Table.from_pylist(list(rows), schema=schema)
    return table.to_pandas(types_mapper=pd.ArrowDtype)


def write_parquet(frame: pd.DataFrame, schema: pa.Schema, destination: Path) -> None:
    """Write a frame as Parquet with exactly the given schema."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False)
    # Drop the pandas metadata: it records the Arrow list dtypes under names that
    # pandas cannot parse back, which breaks a plain pd.read_parquet of the file.
    pq.write_table(table.replace_schema_metadata(None), destination)
