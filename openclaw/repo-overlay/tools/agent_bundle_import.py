#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path


PLACEHOLDER_RE = re.compile(r"__SECRET_[A-Z0-9_]+__")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore a sanitized OpenClaw agent bundle into target repo/config roots."
    )
    parser.add_argument(
        "--bundle-dir",
        default=None,
        help="Path to extracted bundle root. Defaults to directory next to this script named 'bundle'.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Target OpenClaw repo root. Defaults to $OPENCLAW_REPO_ROOT or current working directory.",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Target config dir. Defaults to $OPENCLAW_CONFIG_DIR or ~/.openclaw.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without writing files.",
    )
    return parser.parse_args()


def resolve_bundle_dir(arg_value: str | None) -> Path:
    script_dir = Path(__file__).resolve().parent
    if arg_value:
        return Path(arg_value).resolve()
    return (script_dir / "bundle").resolve()


def load_manifest(bundle_dir: Path) -> dict:
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Missing manifest: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def substitute_placeholders(text: str, source_path: Path) -> str:
    missing: list[str] = []

    def replacer(match: re.Match[str]) -> str:
        placeholder = match.group(0)
        env_name = placeholder[len("__SECRET_") : -len("__")]
        value = os.environ.get(env_name)
        if value is None:
            missing.append(env_name)
            return placeholder
        return value

    result = PLACEHOLDER_RE.sub(replacer, text)
    if missing:
        missing_list = ", ".join(sorted(set(missing)))
        raise SystemExit(
            f"Missing required environment variables for {source_path}: {missing_list}"
        )
    return result


def collect_placeholders(path: Path) -> set[str]:
    if not path.exists():
        return set()
    if path.is_file():
        return {
            match.group(0)[len("__SECRET_") : -len("__")]
            for match in PLACEHOLDER_RE.finditer(path.read_text(encoding="utf-8"))
        }
    found: set[str] = set()
    for file_path in path.rglob("*"):
        if file_path.is_file():
            found.update(collect_placeholders(file_path))
    return found


def sync_directory(source_dir: Path, target_dir: Path, dry_run: bool) -> None:
    if not source_dir.exists():
        return
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    expected_paths: set[Path] = set()
    for src in sorted(source_dir.rglob("*")):
        rel = src.relative_to(source_dir)
        dst = target_dir / rel
        expected_paths.add(dst)
        if src.is_dir():
            if dry_run:
                print(f"mkdir {dst}")
            else:
                dst.mkdir(parents=True, exist_ok=True)
            continue
        if src.is_symlink():
            raise SystemExit(f"Symlinks are not supported in bundle import: {src}")
        data = src.read_text(encoding="utf-8")
        restored = substitute_placeholders(data, src)
        if dry_run:
            print(f"write {dst}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(restored, encoding="utf-8")

    if not target_dir.exists():
        return

    existing = sorted(target_dir.rglob("*"), reverse=True)
    for path in existing:
        if path == target_dir:
            continue
        if path not in expected_paths:
            if dry_run:
                print(f"remove {path}")
            else:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()


def sync_file(source_file: Path, target_file: Path, dry_run: bool) -> None:
    if not source_file.exists():
        return
    restored = substitute_placeholders(source_file.read_text(encoding="utf-8"), source_file)
    if dry_run:
        print(f"write {target_file}")
        return
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(restored, encoding="utf-8")


def apply_removals(target_root: Path, relative_paths: list[str], dry_run: bool) -> None:
    for rel in relative_paths:
        path = target_root / rel
        if not path.exists():
            continue
        if dry_run:
            print(f"remove {path}")
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def main() -> int:
    args = parse_args()
    bundle_dir = resolve_bundle_dir(args.bundle_dir)
    manifest = load_manifest(bundle_dir)

    repo_root = Path(
        args.repo_root or os.environ.get("OPENCLAW_REPO_ROOT") or Path.cwd()
    ).resolve()
    config_dir = Path(
        args.config_dir
        or os.environ.get("OPENCLAW_CONFIG_DIR")
        or (Path.home() / ".openclaw")
    ).resolve()

    print(f"Bundle: {bundle_dir}")
    print(f"Repo target: {repo_root}")
    print(f"Config target: {config_dir}")
    if args.dry_run:
        print("Mode: dry-run")

    source_repo = bundle_dir / "repo"
    source_config = bundle_dir / "config"

    required_env = collect_placeholders(source_repo) | collect_placeholders(source_config)
    missing_env = sorted(name for name in required_env if os.environ.get(name) is None)
    if missing_env:
        raise SystemExit(
            "Missing required environment variables: " + ", ".join(missing_env)
        )

    for rel_dir in manifest.get("repo_sync_dirs", []):
        sync_directory(source_repo / rel_dir, repo_root / rel_dir, args.dry_run)
    for rel_file in manifest.get("repo_sync_files", []):
        sync_file(source_repo / rel_file, repo_root / rel_file, args.dry_run)
    apply_removals(repo_root, manifest.get("repo_remove_paths", []), args.dry_run)

    for rel_dir in manifest.get("config_sync_dirs", []):
        sync_directory(source_config / rel_dir, config_dir / rel_dir, args.dry_run)
    for rel_file in manifest.get("config_sync_files", []):
        sync_file(source_config / rel_file, config_dir / rel_file, args.dry_run)
    apply_removals(config_dir, manifest.get("config_remove_paths", []), args.dry_run)

    if not args.dry_run:
        print("Import completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
