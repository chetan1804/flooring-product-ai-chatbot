"""Bounded-memory iteration over a top-level JSON array."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TextIO


class CatalogFormatError(ValueError):
    """Raised when a catalog does not have the required JSON structure."""


def _read_more(stream: TextIO, buffer: str, chunk_size: int) -> tuple[str, bool]:
    chunk = stream.read(chunk_size)
    return buffer + chunk, chunk == ""


def iter_json_array(path: str | Path, *, chunk_size: int = 1024 * 1024) -> Iterator[dict[str, Any]]:
    """Yield product objects without materializing the complete JSON array."""

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    decoder = json.JSONDecoder()
    with Path(path).open("r", encoding="utf-8-sig", newline=None) as stream:
        buffer = ""
        position = 0
        eof = False

        while True:
            if position >= len(buffer) and not eof:
                buffer, eof = _read_more(stream, "", chunk_size)
                position = 0
            while position < len(buffer) and buffer[position].isspace():
                position += 1
            if position < len(buffer):
                break
            if eof:
                raise CatalogFormatError("catalog is empty; expected a JSON array")

        if buffer[position] != "[":
            raise CatalogFormatError("catalog top-level value must be a JSON array")
        position += 1
        expect_value = True
        record_number = 0

        while True:
            if position:
                buffer = buffer[position:]
                position = 0
            while True:
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if position < len(buffer) or eof:
                    break
                buffer, eof = _read_more(stream, buffer, chunk_size)

            if position < len(buffer) and buffer[position] == "]":
                if expect_value and record_number:
                    raise CatalogFormatError("trailing comma is not valid JSON")
                position += 1
                break
            if not expect_value:
                if position >= len(buffer) or buffer[position] != ",":
                    raise CatalogFormatError(f"expected ',' after product {record_number}")
                position += 1
                expect_value = True
                continue
            if eof and position >= len(buffer):
                raise CatalogFormatError("unexpected end of file inside JSON array")

            while True:
                try:
                    value, end = decoder.raw_decode(buffer, position)
                    break
                except json.JSONDecodeError as error:
                    if eof:
                        raise CatalogFormatError(
                            f"invalid JSON near product {record_number + 1}: {error.msg}"
                        ) from error
                    buffer, eof = _read_more(stream, buffer, chunk_size)

            record_number += 1
            if not isinstance(value, dict):
                raise CatalogFormatError(f"product {record_number} must be a JSON object")
            yield value
            position = end
            expect_value = False

        while True:
            while position < len(buffer) and buffer[position].isspace():
                position += 1
            if position < len(buffer):
                raise CatalogFormatError("unexpected content after the top-level JSON array")
            if eof:
                return
            buffer, eof = _read_more(stream, "", chunk_size)
            position = 0

