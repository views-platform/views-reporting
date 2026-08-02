#!/usr/bin/env python
"""Generate forecast HTML reports from the test fixtures using the REAL
metadata accessors (no mocks), for human inspection of views-reporting output.

This regenerates the forecast side of the `demo_reports/` set with the current
code so it can be eyeballed / compared against earlier outputs. Evaluation
reports come from the real pipeline run (--evaluate --report).

FULLY OFFLINE since C-22 (epic #204): the metadata accessors read the bundled
parquet assets (views_reporting/metadata/data/) — no viewser, no VIEWS DB
access, no VPN needed. Any environment with the package installed works:

    uv run python scripts/generate_demo_reports.py
    uv run python scripts/generate_demo_reports.py --models average_cmbaseline

Output: demo_reports/forecast_<model>_postmigration.html  (gitignored)
Maps use the real get_isoab_for_index/get_name_for_index — full coverage of the
bundled snapshot (see metadata/data/stamp.json), not mocks.
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import shutil
from pathlib import Path
from types import SimpleNamespace

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("generate_demo_reports")

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "data"
OUT = REPO / "demo_reports"

# model -> how to drive ForecastReportTemplate (declared-format loader path, ADR-012)
MODELS = {
    "average_cmbaseline": {"level": "cm", "format": "dataframe", "historical": True},
    "red_ranger": {"level": "cm", "format": "prediction_frame", "historical": True},
    "average_pgmbaseline": {"level": "pgm", "format": "dataframe", "historical": False},
}


def _manifest(model: str) -> dict:
    return json.loads((FIXTURES / model / "manifest.json").read_text())


def _first_origin(model: str, spec: dict) -> Path:
    """First rolling origin: a parquet file (dataframe) or an origin dir (prediction_frame)."""
    base = FIXTURES / model
    if spec["format"] == "prediction_frame":
        d = base / "predictions_calibration" / "origin_0"
        if not d.exists():
            raise FileNotFoundError(f"missing {d}")
        return d
    files = sorted(glob.glob(str(base / "predictions_calibration_*_00.parquet")))
    if not files:
        files = sorted(glob.glob(str(base / "predictions_calibration_*.parquet")))
    if not files:
        raise FileNotFoundError(f"no parquet origins under {base}")
    return Path(files[0])


def generate_one(model: str, spec: dict, suffix: str) -> Path | None:
    import pandas as pd
    from views_pipeline_core.configs.pipeline import PipelineConfig

    from views_reporting.templates.reports.forecast import ForecastReportTemplate

    # Footer stamp (report.py reads PipelineConfig.current_version). Best-effort:
    # newer pipeline-core exposes current_version as a read-only property.
    try:
        if not getattr(PipelineConfig, "current_version", None):
            PipelineConfig.current_version = "0.1.0-demo"
    except AttributeError:
        pass

    manifest = _manifest(model)
    targets = manifest["targets"]
    origin = _first_origin(model, spec)

    historical_df = None
    if spec["historical"]:
        hist = FIXTURES / model / "calibration_viewser_df.parquet"
        historical_df = pd.read_parquet(hist) if hist.exists() else None
        if historical_df is None:
            log.warning("%s: no historical parquet; CM line graphs will be skipped", model)

    model_path = SimpleNamespace(target="model", model_name=model, reports=OUT)
    config = {"name": model, "level": spec["level"], "targets": targets}

    log.info("Generating forecast report: %s (%s/%s) from %s",
             model, spec["level"], spec["format"], origin.name)
    # The bundled fixtures are calibration rolling-origin predictions, so the
    # reports are hindcasts; run_type drives the partition name in the caption.
    template = ForecastReportTemplate(config, model_path, run_type="calibration")
    # Declared-format loader path (exercises the migrated loaders); real metadata (no mocks).
    produced = template.generate(
        prediction_path=origin,
        prediction_format=spec["format"],
        historical_dataframe=historical_df,
    )

    friendly = OUT / f"forecast_{model}{suffix}.html"
    if produced.resolve() != friendly.resolve():
        shutil.move(str(produced), str(friendly))
    return friendly


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", nargs="*", default=list(MODELS), choices=list(MODELS))
    ap.add_argument("--suffix", default="_postmigration",
                    help="appended to forecast_<model><suffix>.html (preserves originals)")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    results = []
    for model in args.models:
        try:
            path = generate_one(model, MODELS[model], args.suffix)
            size_mb = path.stat().st_size / 1e6
            results.append((model, path, size_mb, None))
            log.info("  -> %s (%.1f MB)", path, size_mb)
        except Exception as e:  # noqa: BLE001 - demo tool: report and continue
            log.exception("  FAILED %s", model)
            results.append((model, None, 0.0, repr(e)))

    print("\n=== demo forecast reports ===")
    for model, path, size_mb, err in results:
        if err:
            print(f"  ✗ {model}: {err}")
        else:
            print(f"  ✓ {model}: file://{path}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
