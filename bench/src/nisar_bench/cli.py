import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from nisar_bench.cases import build_matrix
from nisar_bench.metrics_benchmark import benchmark_metrics
from nisar_bench.reader import load_lab
from nisar_bench.report import (
    build_report,
    compare_to_baseline,
    recommend_defaults,
    write_stage_chart,
)

BUDGET_S = 22.0
DEFAULT_SHAPES = ["500x500x5", "900x900x10"]
REGRESSION_TOLERANCE = 0.2
RESULTS_DIR = Path("results")


def _csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _shape(value: str) -> tuple[int, int, int]:
    height, width, dates = (int(part) for part in value.lower().split("x"))
    return dates, height, width


def _load_records(paths: list[Path]) -> pd.DataFrame:
    return pd.concat([pd.read_csv(path) for path in paths], ignore_index=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nisar-bench")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run the benchmark matrix on a runtime")
    run.add_argument("--runtime", choices=["local", "modal"], required=True)
    run.add_argument("--region", choices=["default", "us-west"], default="default")
    run.add_argument("--sites", default="qadirabad,chokwe,richmond")
    run.add_argument("--threads", default="5")
    run.add_argument("--readers", default="pyfive")
    run.add_argument("--block-mb", type=float, default=1.0)
    run.add_argument("--multilook", type=int, default=2)
    run.add_argument("--run-id")
    run.add_argument("--out", type=Path)

    report = commands.add_parser("report", help="write the markdown report and chart")
    report.add_argument("--input", nargs="+", type=Path, required=True)
    report.add_argument("--out", type=Path, default=Path("REPORT.md"))
    report.add_argument("--chart", type=Path, default=RESULTS_DIR / "stage-breakdown.png")
    report.add_argument("--budget", type=float, default=BUDGET_S)

    defaults = commands.add_parser("defaults", help="write the recommended defaults as JSON")
    defaults.add_argument("--input", nargs="+", type=Path, required=True)
    defaults.add_argument("--out", type=Path, default=Path("defaults.json"))

    metrics = commands.add_parser("metrics", help="time the vectorized metrics offline")
    metrics.add_argument("--shapes", default=",".join(DEFAULT_SHAPES))

    compare = commands.add_parser("compare", help="fail when a stage regresses against a baseline")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--input", nargs="+", type=Path, required=True)
    compare.add_argument("--tolerance", type=float, default=REGRESSION_TOLERANCE)
    return parser


def _run(args: argparse.Namespace) -> int:
    region = None if args.region == "default" else args.region
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = f"-{region}" if region else ""
    run_id = args.run_id or f"{args.runtime}{suffix}-{stamp}"
    specs = build_matrix(
        sites=_csv_list(args.sites),
        threads=[int(count) for count in _csv_list(args.threads)],
        readers=_csv_list(args.readers),
        block_mb=args.block_mb,
        multilook=args.multilook,
    )
    if args.runtime == "local":
        from nisar_bench.runtime_local import run_local

        records = run_local(specs=specs, run_id=run_id)
    else:
        from nisar_bench.runtime_modal import run_modal

        records = run_modal(specs=specs, run_id=run_id, region=region)
    out = args.out or RESULTS_DIR / f"{run_id}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(out, index=False)
    failed = sum(1 for record in records if record["error"])
    print(f"{len(records)} runs ({failed} failed) written to {out}")
    return 0


def _report(args: argparse.Namespace) -> int:
    records = _load_records(args.input)
    args.out.write_text(build_report(records=records, budget_s=args.budget), encoding="utf-8")
    args.chart.parent.mkdir(parents=True, exist_ok=True)
    write_stage_chart(records=records, path=args.chart)
    print(f"report written to {args.out} and chart to {args.chart}")
    return 0


def _defaults(args: argparse.Namespace) -> int:
    defaults = recommend_defaults(records=_load_records(args.input))
    args.out.write_text(json.dumps(defaults, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(defaults, indent=2))
    return 0


def _metrics(args: argparse.Namespace) -> int:
    results = benchmark_metrics(lab=load_lab(), shapes=[_shape(s) for s in _csv_list(args.shapes)])
    print(json.dumps(results, indent=2))
    return 0


def _compare(args: argparse.Namespace) -> int:
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    regressions = compare_to_baseline(
        records=_load_records(args.input), baseline=baseline, tolerance=args.tolerance
    )
    if regressions:
        print(
            f"regressed more than {args.tolerance:.0%}: {', '.join(regressions)}", file=sys.stderr
        )
        return 1
    print("no stage regressed")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    handlers = {
        "run": _run,
        "report": _report,
        "defaults": _defaults,
        "metrics": _metrics,
        "compare": _compare,
    }
    return handlers[args.command](args)
