#!/usr/bin/env python3
"""Create an auditable release manifest for packaged Pia artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_files(root: Path, paths: Iterable[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        candidate = path if path.is_absolute() else root / path
        if candidate.is_file():
            files.add(candidate)
        elif candidate.is_dir():
            files.update(item for item in candidate.rglob("*") if item.is_file())
    return sorted(files)


def build_manifest(root: Path, paths: Iterable[Path], generated_at: str) -> dict:
    artifacts = []
    for path in artifact_files(root, paths):
        artifacts.append({
            "path": Path(os.path.relpath(path, root)).as_posix(),
            "size": path.stat().st_size,
            "sha256": sha256(path),
        })
    return {
        "product": "pia",
        "version": "0.1.0",
        "generated_at": generated_at,
        "artifacts": artifacts,
    }


def sign_manifest(manifest_path: Path, key_path: Path, signature_path: Path) -> None:
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(key_path),
            "-out",
            str(signature_path),
            str(manifest_path),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at")
    parser.add_argument("--sign-key", type=Path)
    parser.add_argument("--signature-output", type=Path)
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    generated_at = args.generated_at or datetime.now(timezone.utc).isoformat()
    manifest = build_manifest(root, args.artifacts, generated_at)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    if args.sign_key:
        if not args.signature_output:
            parser.error("--signature-output is required with --sign-key")
        signature = (
            args.signature_output
            if args.signature_output.is_absolute()
            else root / args.signature_output
        )
        sign_manifest(output, args.sign_key, signature)
    print(json.dumps({
        "status": "created",
        "manifest": str(output),
        "artifact_count": len(manifest["artifacts"]),
        "signed": bool(args.sign_key),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
