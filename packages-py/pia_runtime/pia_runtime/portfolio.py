from __future__ import annotations

import csv
import base64
import io
import json
import zipfile
from datetime import date
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .models import new_id

REQUIRED_COLUMNS = {"symbol", "quantity", "avg_cost", "market_value"}


def normalize_positions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = []
    total_value = sum(float(row.get("market_value", 0) or 0) for row in rows)
    for row in rows:
        market_value = float(row.get("market_value", 0) or 0)
        normalized.append({
            "symbol": str(row["symbol"]).strip(),
            "quantity": float(row.get("quantity", 0) or 0),
            "avg_cost": float(row.get("avg_cost", 0) or 0),
            "market_value": market_value,
            "weight": market_value / total_value if total_value else 0,
            "sector": row.get("sector") or "unknown",
            "asset_type": row.get("asset_type") or ("etf" if str(row["symbol"]).startswith(("5", "1")) else "stock"),
        })
    return {
        "snapshot_id": new_id("portfolio"),
        "user_id": "default",
        "as_of": date.today().isoformat(),
        "source": "import",
        "cash": 0,
        "total_value": total_value,
        "drawdown": 0,
        "positions": normalized,
    }


def parse_csv(content: str) -> dict[str, Any]:
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    if not rows or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames or [])):
        raise ValueError(f"CSV must contain columns: {', '.join(sorted(REQUIRED_COLUMNS))}")
    return normalize_positions(rows)


def parse_manual(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("manual portfolio input cannot be empty")
    if not REQUIRED_COLUMNS.issubset(rows[0]):
        raise ValueError(f"manual input must contain: {', '.join(sorted(REQUIRED_COLUMNS))}")
    return normalize_positions(rows)


def parse_xlsx(content: bytes) -> dict[str, Any]:
    # Minimal dependency-free reader for the first worksheet used by MVP imports.
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root]
        sheet_name = "xl/worksheets/sheet1.xml"
        root = ElementTree.fromstring(archive.read(sheet_name))
        rows: list[list[str]] = []
        for row in root.findall(".//{*}row"):
            values = []
            for cell in row.findall("{*}c"):
                reference = cell.get("r", "").rstrip("0123456789")
                if len(reference) > 3 or any(not "A" <= letter <= "Z" for letter in reference):
                    raise ValueError("Invalid Excel cell reference")
                column = 0
                for letter in reference:
                    column = column * 26 + ord(letter) - ord("A") + 1
                if column > len(values) + 1:
                    values.extend([""] * (column - len(values) - 1))
                value = cell.find("{*}v")
                raw = value.text if value is not None and value.text else ""
                if cell.attrib.get("t") == "s" and raw:
                    raw = shared[int(raw)]
                elif cell.attrib.get("t") == "inlineStr":
                    raw = "".join(part.text or "" for part in cell.findall(".//{*}t"))
                values.append(raw)
            rows.append(values)
    if not rows:
        raise ValueError("Excel workbook is empty")
    headers = [str(item).strip() for item in rows[0]]
    return parse_manual([dict(zip(headers, row)) for row in rows[1:] if any(row)])


def parse_portfolio(format_name: str, content: Any) -> dict[str, Any]:
    if format_name == "csv":
        return parse_csv(str(content))
    if format_name in {"xlsx", "excel"}:
        if isinstance(content, dict) and content.get("encoding") == "base64":
            content = base64.b64decode(str(content.get("data", "")), validate=True)
        if isinstance(content, str):
            content = content.encode("latin1")
        return parse_xlsx(content)
    if format_name == "manual":
        return parse_manual(json.loads(content) if isinstance(content, str) else content)
    raise ValueError(f"unsupported portfolio format: {format_name}")
