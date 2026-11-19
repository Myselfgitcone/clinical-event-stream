"""Small buffered parquet writer so a cohort never has to fit in memory at once."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


class ParquetSink:
    def __init__(self, path: Path, schema: pa.Schema, batch_rows: int = 50_000):
        self.path = path
        self.schema = schema
        self.batch_rows = batch_rows
        self._rows: list[dict[str, Any]] = []
        self._writer: pq.ParquetWriter | None = None
        self.count = 0

    def add(self, row: dict[str, Any]) -> None:
        self._rows.append(row)
        if len(self._rows) >= self.batch_rows:
            self.flush()

    def extend(self, rows: list[dict[str, Any]]) -> None:
        for r in rows:
            self.add(r)

    def flush(self) -> None:
        if not self._rows:
            return
        table = pa.Table.from_pylist(self._rows, schema=self.schema)
        if self._writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = pq.ParquetWriter(self.path, self.schema, compression="zstd")
        self._writer.write_table(table)
        self.count += len(self._rows)
        self._rows = []

    def close(self) -> int:
        """Flush and close. Always leaves a file behind, even an empty one, so
        downstream globs never see a missing table."""
        self.flush()
        if self._writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            pq.write_table(self.schema.empty_table(), self.path, compression="zstd")
        else:
            self._writer.close()
        return self.count


def read_rows(path: Path, columns: list[str] | None = None):
    """Yield rows as dicts, one record batch at a time."""
    pf = pq.ParquetFile(path)
    for batch in pf.iter_batches(batch_size=50_000, columns=columns):
        yield from batch.to_pylist()
