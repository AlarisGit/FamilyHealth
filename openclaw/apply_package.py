#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path


PLACEHOLDER_RE = re.compile(r"__SET_[A-Z0-9_]+__")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply the FamilyHealth OpenClaw reproduction package to a target repo/config pair."
    )
    parser.add_argument("--repo-root", required=True, help="Target OpenClaw git checkout.")
    parser.add_argument("--config-dir", required=True, help="Target OpenClaw config dir.")
    parser.add_argument(
        "--secrets-file",
        default=None,
        help="Optional env-style file with secret values. Falls back to process environment.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions only.")
    return parser.parse_args()


def package_root() -> Path:
    return Path(__file__).resolve().parent


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit(f"Invalid line in secrets file: {raw_line}")
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_secret_values(secrets_file: str | None) -> dict[str, str]:
    values = dict(os.environ)
    if secrets_file:
        values.update(load_env_file(Path(secrets_file).resolve()))
    return values


def substitute_placeholders(text: str, source_path: Path, values: dict[str, str]) -> str:
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        placeholder = match.group(0)
        key = placeholder[len("__SET_") : -len("__")]
        value = values.get(key)
        if value is None or value == "":
            missing.append(key)
            return placeholder
        return value

    rendered = PLACEHOLDER_RE.sub(repl, text)
    if missing:
        missing_list = ", ".join(sorted(set(missing)))
        raise SystemExit(f"Missing values for {source_path}: {missing_list}")
    return rendered


def sync_text_tree(source_root: Path, target_root: Path, values: dict[str, str], dry_run: bool) -> None:
    if not source_root.exists():
        return
    for src in sorted(source_root.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(source_root)
        dst = target_root / rel
        rendered = substitute_placeholders(src.read_text(encoding="utf-8"), src, values)
        if dry_run:
            print(f"write {dst}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(rendered, encoding="utf-8")


def apply_removals(target_root: Path, removals_file: Path, dry_run: bool) -> None:
    if not removals_file.exists():
        return
    for raw_line in removals_file.read_text(encoding="utf-8").splitlines():
        rel = raw_line.strip()
        if not rel or rel.startswith("#"):
            continue
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
    root = package_root()
    repo_root = Path(args.repo_root).resolve()
    config_dir = Path(args.config_dir).resolve()
    values = load_secret_values(args.secrets_file)

    print(f"Package: {root}")
    print(f"Repo target: {repo_root}")
    print(f"Config target: {config_dir}")
    if args.dry_run:
        print("Mode: dry-run")

    sync_text_tree(root / "repo-overlay", repo_root, values, args.dry_run)
    sync_text_tree(root / "config-overlay", config_dir, values, args.dry_run)
    apply_removals(repo_root, root / "repo-remove-paths.txt", args.dry_run)

    if not args.dry_run:
        print("Package applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
