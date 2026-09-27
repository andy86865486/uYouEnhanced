#!/usr/bin/env python3
"""Collect compiled uYouEnhanced plugins and resources for TrollFools."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
    else:
        for child in sorted(path.rglob("*")):
            if child.is_file():
                hasher.update(child.relative_to(path).as_posix().encode())
                with child.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        hasher.update(chunk)
    return hasher.hexdigest()


def plugin_paths(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if any(parent.name.endswith((".bundle", ".framework")) for parent in path.parents if parent != root):
            continue
        if path.is_dir() and path.name.endswith((".bundle", ".framework")):
            yield path
        elif path.is_file() and path.name.endswith(".dylib"):
            yield path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roots", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    added: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="uyou-trollfools-") as temp:
        stage = Path(temp) / "plugins"
        stage.mkdir()

        for root in args.roots:
            for source in plugin_paths(root):
                target = stage / source.name
                if target.exists():
                    if digest(source) != digest(target):
                        raise SystemExit(f"Conflicting plugin with the same name: {source.name}")
                    continue
                if source.is_dir():
                    shutil.copytree(source, target, symlinks=True)
                else:
                    shutil.copy2(source, target)
                added.add(source.name)

        if not any(name.endswith(".dylib") for name in added):
            raise SystemExit("No compiled tweak dylibs were found in the build output")

        with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(stage.iterdir()):
                if item.is_dir():
                    archive.write(item, item.name + "/")
                    for child in sorted(item.rglob("*")):
                        archive.write(child, child.relative_to(stage).as_posix())
                else:
                    archive.write(item, item.name)

    print(f"Created {args.output} with {len(added)} top-level plugins:")
    for name in sorted(added):
        print(f"  {name}")


if __name__ == "__main__":
    main()
