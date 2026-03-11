from __future__ import annotations

import argparse
import sys

from src.orchestrator import analyze
from src.agents.hydrologist import run_hydrologist


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cartographer",
        description="Ingest any GitHub repository (or local path) and produce a queryable knowledge graph.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    analyze_p = sub.add_parser("analyze", help="Run Phase 1 Surveyor analysis")
    analyze_p.add_argument(
        "repo",
        help="Local path or GitHub (e.g. https://github.com/owner/repo) to analyze",
    )
    analyze_p.add_argument(
        "--branch", "-b",
        default=None,
        help="Branch/ref to use when cloning a remote repo (default: default branch)",
    )
    analyze_p.add_argument(
        "--depth",
        type=int,
        default=1,
        metavar="N",
        help="Clone depth for remote repos (default: 1); use 0 for full history",
    )

    lineage_p = sub.add_parser("lineage", help="Run Phase 2 Hydrologist (data lineage)")
    lineage_p.add_argument(
        "repo",
        help="Local path to the repository to analyze for lineage",
    )

    args = parser.parse_args(argv)

    if args.cmd == "analyze":
        depth = args.depth if args.depth > 0 else None
        out = analyze(args.repo, branch=args.branch, clone_depth=depth)
        print(out)
        return 0

    if args.cmd == "lineage":
        from pathlib import Path
        # Write lineage_graph.json to project .cartography (cwd) so latest analysis is kept there
        project_root = Path.cwd().resolve()
        graph = run_hydrologist(Path(args.repo), project_data_dir=project_root)
        out_path = project_root / ".cartography" / "lineage_graph.json"
        print(str(out_path))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

