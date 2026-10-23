"""
CLI entrypoint for `sancscreen`.

Usage:
  python -m sancscreen bench
  python -m sancscreen serve --port 8016
  python -m sancscreen screen --name "विक्टर बुट" --country RU --dob 1967-01-13
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional

import uvicorn

from sancscreen.bench import (
    SanctionsScreeningPipeline,
    format_benchmark_report,
    run_benchmark,
)
from sancscreen.matcher import ScreeningQuery


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="sancscreen",
        description="Cross-Script Phonetic, Transliteration & UBO Graph Sanctions Screening Engine",
    )
    sub = parser.add_subparsers(dest="command")

    # bench subcommand
    bench_p = sub.add_parser("bench", help="Run the 300-wire benchmark suite")
    bench_p.add_argument("--json", action="store_true", help="Output raw JSON benchmark metrics")

    # serve subcommand
    serve_p = sub.add_parser("serve", help="Start the FastAPI server and interactive web console")
    serve_p.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    serve_p.add_argument("--port", type=int, default=8016, help="Bind port (default: 8016)")

    # screen subcommand
    screen_p = sub.add_parser("screen", help="Screen a single wire transfer party")
    screen_p.add_argument("--name", required=True, help="Party or entity name (any script)")
    screen_p.add_argument("--dob", default=None, help="Date of Birth (YYYY-MM-DD)")
    screen_p.add_argument("--country", default=None, help="ISO-2 Country code")
    screen_p.add_argument("--id", dest="identifier", default=None, help="Passport / BIC / LEI")

    args = parser.parse_args(argv)

    if args.command == "serve":
        if args.host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("SANCSCREEN_API_KEY"):
            print("Refusing to listen on a non-loopback address without SANCSCREEN_API_KEY set.", file=sys.stderr)
            return 2
        uvicorn.run("sancscreen.api:app", host=args.host, port=args.port, reload=False)
        return 0

    if args.command == "screen":
        pipeline = SanctionsScreeningPipeline()
        res = pipeline.screen_wire(
            ScreeningQuery(
                query_id="CLI-001",
                name=args.name,
                dob=args.dob,
                country=args.country,
                identifier=args.identifier,
            )
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    # Default or "bench": run benchmark
    res = run_benchmark()
    if getattr(args, "json", False):
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(format_benchmark_report(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
