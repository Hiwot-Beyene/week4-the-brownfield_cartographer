from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from src.agents.navigator import ask_navigator
from src.orchestrator import analyze, AnalysisResult
from src.agents.hydrologist import run_hydrologist
from src.repo_resolver import resolve_repo
from src.store import sqlite_store

logger = logging.getLogger("cartographer.cli")

# Exit codes: 0 success, 1 input/usage, 2 agent failure, 3 partial (later stage failed)
EXIT_SUCCESS = 0
EXIT_INPUT_ERROR = 1
EXIT_AGENT_FAILURE = 2
EXIT_PARTIAL = 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cartographer",
        description="Ingest any GitHub repository (or local path) and produce a queryable knowledge graph.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    analyze_p = sub.add_parser(
        "analyze",
        help="Run full analysis pipeline (Surveyor → Hydrologist → Semanticist)",
    )
    analyze_p.add_argument(
        "repo",
        nargs="?",
        default=".",
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
    analyze_p.add_argument(
        "--output-dir", "-o",
        default=None,
        metavar="DIR",
        help="Output directory for .cartography (default: cwd)",
    )
    analyze_p.add_argument(
        "--skip-lineage",
        action="store_true",
        help="Run only Surveyor (no Hydrologist); omit lineage_graph.json",
    )
    analyze_p.add_argument(
        "--no-incremental",
        action="store_true",
        help="Disable incremental update mode and force full re-analysis.",
    )
    analyze_p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable progress logging",
    )

    lineage_p = sub.add_parser("lineage", help="Run Phase 2 Hydrologist (data lineage)")
    lineage_p.add_argument(
        "repo",
        help="Local path or GitHub URL (e.g. https://github.com/owner/repo) to analyze for lineage",
    )
    lineage_p.add_argument(
        "--branch", "-b",
        default=None,
        help="Branch/ref when cloning a remote repo",
    )
    lineage_p.add_argument(
        "--depth",
        type=int,
        default=1,
        metavar="N",
        help="Clone depth for remote repos (default: 1); use 0 for full history",
    )
    lineage_p.add_argument(
        "--output-dir", "-o",
        default=None,
        metavar="DIR",
        help="Write lineage_graph.json to DIR/.cartography (default: cwd)",
    )
    lineage_p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable progress logging",
    )
    query_p = sub.add_parser("query", help="Ask Navigator questions over the latest analysis")
    query_p.add_argument(
        "repo",
        help="Local path or GitHub URL (e.g. https://github.com/owner/repo)",
    )
    query_p.add_argument("question", help="Natural-language question for Navigator")
    query_p.add_argument(
        "--branch", "-b",
        default=None,
        help="Branch/ref when cloning a remote repo",
    )
    query_p.add_argument(
        "--depth",
        type=int,
        default=1,
        metavar="N",
        help="Clone depth for remote repos (default: 1); use 0 for full history",
    )

    args = parser.parse_args(argv)

    # Show progress logs for analyze by default so long-running runs have visible status.
    # Verbose currently maps to the same level and preserves existing behavior for other commands.
    if getattr(args, "cmd", None) == "analyze" or getattr(args, "verbose", False):
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.cmd == "analyze":
        depth = args.depth if args.depth > 0 else None
        try:
            result = analyze(
                args.repo,
                branch=args.branch,
                clone_depth=depth,
                output_dir=Path(args.output_dir) if getattr(args, "output_dir", None) else None,
                skip_lineage=getattr(args, "skip_lineage", False),
                incremental=not getattr(args, "no_incremental", False),
            )
        except ValueError as e:
            logger.error("analyze: %s", e)
            return EXIT_INPUT_ERROR
        if not result.success:
            if result.failed_stage:
                logger.error("analyze failed at stage: %s — %s", result.failed_stage, result.error or "")
                if result.partial_artifacts and args.verbose:
                    logger.info("Partial artifacts written: %s", ", ".join(result.partial_artifacts))
            print(result.output or "")
            # Resolve failure is input error; Surveyor failure is full failure; later stages are partial
            if result.failed_stage == "resolve":
                return EXIT_INPUT_ERROR
            if result.failed_stage == "Surveyor":
                return EXIT_AGENT_FAILURE
            return EXIT_PARTIAL
        if args.verbose:
            logger.info("Survey complete. Output: %s", result.output)
        print(result.output)
        return EXIT_SUCCESS

    if args.cmd == "lineage":
        from pathlib import Path
        output_dir = Path(args.output_dir).resolve() if getattr(args, "output_dir", None) else Path.cwd().resolve()
        try:
            repo_path = resolve_repo(args.repo, branch=getattr(args, "branch", None), depth=getattr(args, "depth", 1))
        except ValueError as e:
            logger.error("lineage: %s", e)
            return 1
        if args.verbose:
            logger.info("Analyzing lineage for %s (%d files)...", repo_path, len(list(repo_path.rglob("*"))))
        graph = run_hydrologist(repo_path, project_data_dir=output_dir)
        out_path = output_dir / ".cartography" / "lineage_graph.json"
        if args.verbose:
            logger.info("Lineage graph: %d nodes, %d edges -> %s", graph._g.number_of_nodes(), graph._g.number_of_edges(), out_path)
        print(str(out_path))
        return 0

    if args.cmd == "query":
        try:
            repo_path = resolve_repo(
                args.repo,
                branch=getattr(args, "branch", None),
                depth=getattr(args, "depth", 1),
            )
        except ValueError as e:
            logger.error("query: %s", e)
            return 1
        repo_id = sqlite_store.get_repo_id(repo_path)
        analyses = sqlite_store.get_analyses(repo_id=repo_id, limit=1, repo_root=Path.cwd().resolve())
        if not analyses:
            logger.error("query: no analyses found for %s; run analyze first", repo_path)
            return 1
        analysis_id = int(analyses[0]["id"])
        answer = ask_navigator(
            analysis_id=analysis_id,
            query=args.question,
            repo_root=Path.cwd().resolve(),
            artifacts_dir=Path.cwd().resolve() / ".cartography",
        )
        print(json.dumps(answer, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

