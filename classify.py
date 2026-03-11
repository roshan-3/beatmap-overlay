"""
CLI entry point.

Usage:
    python classify.py map.osu
    python classify.py maps/          # processes all .osu files in a directory
    python classify.py maps/ --out results.json
    python classify.py maps/ --pretty
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from osu_parser import parse_osu_file
from feature_extractor import extract_features


def process_file(path: Path) -> dict:
    try:
        bm = parse_osu_file(path)
        feats = extract_features(bm)
        feats["file"] = str(path)
        return feats
    except Exception as exc:
        return {"file": str(path), "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract osu! beatmap features")
    parser.add_argument("input", help=".osu file or directory of .osu files")
    parser.add_argument("--out", help="Write JSON output to this file")
    parser.add_argument("--pretty", action="store_true",
                        help="Pretty-print JSON (indent=2)")
    args = parser.parse_args()

    target = Path(args.input)
    if target.is_dir():
        paths = sorted(target.rglob("*.osu"))
    elif target.is_file():
        paths = [target]
    else:
        print(f"Error: '{target}' is not a file or directory.", file=sys.stderr)
        sys.exit(1)

    if not paths:
        print("No .osu files found.", file=sys.stderr)
        sys.exit(1)

    results = [process_file(p) for p in paths]
    indent = 2 if args.pretty else None
    output = json.dumps(results if len(results) > 1 else results[0],
                        indent=indent)

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"Wrote {len(results)} result(s) to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
