#!/usr/bin/env python3
"""Collect uYouEnhanced and its tweak dependencies for TrollFools."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
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
    for path in sorted(root.rglob("*")):
        if any(parent.name.endswith((".bundle", ".framework")) for parent in path.parents if parent != root):
            continue
        if path.is_dir() and path.name.endswith((".bundle", ".framework")):
            yield path
        elif path.is_file() and path.name.endswith(".dylib"):
            yield path


def add_plugin(source: Path, stage: Path, added: set[str]) -> None:
    target = stage / source.name
    if target.exists():
        if digest(source) != digest(target):
            raise RuntimeError(f"Conflicting plugin with the same name: {source.name}")
        return
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True)
    else:
        shutil.copy2(source, target)
    added.add(source.name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--built-app", type=Path, required=True)
    parser.add_argument("--baseline-app", type=Path, required=True)
    parser.add_argument("--debs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.built_app.is_dir() or not args.baseline_app.is_dir():
        raise SystemExit("Built and baseline YouTube.app directories are required")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    added: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="uyou-trollfools-") as temp:
        temp_path = Path(temp)
        stage = temp_path / "plugins"
        stage.mkdir()

        # The IPA build adds the primary uYouEnhanced injection files.
        for item in plugin_paths(args.built_app):
            relative = item.relative_to(args.built_app)
            original = args.baseline_app / relative
            if original.exists() and digest(item) == digest(original):
                continue
            add_plugin(item, stage, added)

        # Subproject tweak packages carry the other dylibs, bundles, and frameworks.
        debs = sorted(args.debs.glob("*.deb"))
        if not debs:
            raise SystemExit("No subproject .deb files were produced by the build")
        for index, deb in enumerate(debs):
            extracted = temp_path / f"deb-{index}"
            extracted.mkdir()
            subprocess.run(["dpkg-deb", "-x", str(deb), str(extracted)], check=True)
            for item in plugin_paths(extracted):
                add_plugin(item, stage, added)

        if not any(name.endswith(".dylib") for name in added):
            raise SystemExit("No tweak dylibs were found in the build output")

        with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(stage.iterdir()):
                if item.is_dir():
                    for child in sorted(item.rglob("*")):
                        if child.is_file():
                            archive.write(child, child.relative_to(stage).as_posix())
                        elif child.is_dir():
                            archive.write(child, child.relative_to(stage).as_posix() + "/")
                    archive.write(item, item.name + "/")
                else:
                    archive.write(item, item.name)

    print(f"Created {args.output} with {len(added)} top-level plugins:")
    for name in sorted(added):
        print(f"  {name}")


if __name__ == "__main__":
    main()
