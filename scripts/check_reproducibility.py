#!/usr/bin/env python3
"""Check that the processed tables can be rebuilt from a clean clone of the repository.

Steps:
1. Clone the repository into a temporary directory and check out ``--ref``. Only
   committed files take part; uncommitted changes in the source checkout are ignored.
2. Restore the git-ignored raw inputs from ``--raw-dir``, as described in
   docs/ingestion_notes.md section 10.
3. Run the documented commands in the clone: ``make install`` (only with ``--install``)
   and ``make run-pipeline``.
4. Report one line per processed table:
   - PASS: the stage produced a valid table; a committed table was rebuilt identically,
     or was kept because its module is not implemented yet.
   - BLOCKED: the stage waits on another member's issue.
   - FAIL: the stage failed or did not run, or a committed table came out different.

Without ``--install`` the clone runs with this interpreter and the clone's ``src/`` first
on ``PYTHONPATH``, which skips the dependency download but not the clone's code.

  python scripts/check_reproducibility.py
  python scripts/check_reproducibility.py --ref develop --install
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PASS, BLOCKED, FAIL = "PASS", "BLOCKED", "FAIL"


def classify(stage: dict, committed: bool) -> tuple[str, str]:
    """Turn one run_pipeline.py result into a (verdict, reason) pair."""
    status, detail = stage["status"], stage["detail"]
    if status == "DONE":
        if committed and stage["changed"]:
            return FAIL, "rebuilt table differs from the committed copy"
        reason = "rebuilt identically to the committed copy" if committed else detail
        return PASS, reason
    if status == "EXISTING":
        return PASS, f"committed copy kept: {detail}"
    if status == "BLOCKED":
        return BLOCKED, detail
    if status == "NOT_RUN":
        return FAIL, "not run because an earlier stage failed"
    return FAIL, detail


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def _restore_raw_inputs(clone: Path, raw_dir: Path) -> None:
    config = yaml.safe_load((clone / "config/default_config.yaml").read_text(encoding="utf-8"))
    target_dir = clone / config["paths"]["data_raw_dir"]
    target_dir.mkdir(parents=True, exist_ok=True)
    name = config["stations"]["snapshot_file"]
    source = raw_dir / name
    if source.exists():
        shutil.copy2(source, target_dir / name)
        print(f"restored {name} from {raw_dir}")
    else:
        print(f"WARNING: {source} not found; the stations stage will report it as missing")


def check(repo: Path, ref: str, raw_dir: Path, install: bool, workdir: Path) -> int:
    clone = workdir / "repo"
    report_path = workdir / "pipeline_report.json"
    if subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip():
        print("NOTE: the source checkout has uncommitted changes; they are not checked.")

    _run(["git", "clone", "--quiet", "--no-hardlinks", str(repo), str(clone)], cwd=workdir)
    _run(["git", "checkout", "--quiet", ref], cwd=clone)
    _restore_raw_inputs(clone, raw_dir)
    committed = {path.relative_to(clone).as_posix() for path in clone.glob("data/processed/*")}

    make_run = ["make", "run-pipeline", f"PIPELINE_ARGS=--report-json {report_path}"]
    env = None
    if install:
        _run(["make", "install"], cwd=clone)
    else:
        env = {**os.environ, "PYTHONPATH": str(clone / "src")}
        make_run.append(f"PYTHON={sys.executable}")
    try:
        _run(make_run, cwd=clone, env=env)
    except subprocess.CalledProcessError as exc:
        # run_pipeline.py exits 1 when a stage fails; its report still says which one.
        print(f"make run-pipeline exited with {exc.returncode}")

    if not report_path.exists():
        print(f"{FAIL}: the pipeline wrote no report, so no table can be checked")
        return 1

    print("\nReproducibility per processed table:")
    verdicts = []
    for stage in json.loads(report_path.read_text(encoding="utf-8")):
        verdict, reason = classify(stage, stage["output"] in committed)
        verdicts.append(verdict)
        print(f"  {verdict:<8} {stage['output']}  {reason}")
    return 1 if FAIL in verdicts else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help="repository to clone")
    parser.add_argument("--ref", default="HEAD", help="commit, branch or tag to check")
    parser.add_argument(
        "--raw-dir", type=Path, help="where the raw inputs are (default: <repo>/data/raw)"
    )
    parser.add_argument("--install", action="store_true", help="run `make install` in the clone")
    parser.add_argument("--keep", action="store_true", help="keep the temporary directory")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    ref = subprocess.run(
        ["git", "rev-parse", args.ref], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    raw_dir = (args.raw_dir or repo / "data/raw").resolve()

    workdir = Path(tempfile.mkdtemp(prefix="bubi-repro-"))
    try:
        return check(repo, ref, raw_dir, args.install, workdir)
    finally:
        if args.keep:
            print(f"kept {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
