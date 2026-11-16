"""Calibration command line.

  python -m fenrir.calibration fit points.csv --lat 43.6 --alt 150 --out cal/
  python -m fenrir.calibration demo --out cal-demo/     (SIMULATED data)

The CSV for ``fit`` is produced by recording each dwell with the diagnostic
tool (``python -m fenrir.diagnostics --dwell``) and noting the reference load.
"""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np

from . import CalPoint, fit, load_points_csv, local_gravity, mass_to_force, write_report


def simulated_points(masses_kg: list[float], g: float, seed: int = 3) -> list[CalPoint]:
    from ..simulator import LoadCellModel

    cell = LoadCellModel(seed=seed)
    seq = [(m, "up") for m in masses_kg] + [(m, "down") for m in reversed(masses_kg[:-1])]
    pts = []
    t = 0.0
    for m, direction in seq:
        f = mass_to_force(m, g, 7850.0)
        vals = []
        for _ in range(240):  # 3 s dwell at 80 SPS
            vals.append(cell.counts(f, t))
            t += 1 / 80
        pts.append(CalPoint(f, float(np.mean(vals)), float(np.std(vals)), len(vals), direction, u_reference_n=0.0005 * f))
    return pts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fenrir.calibration")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit", help="fit calibration points from a CSV file")
    f.add_argument("csv")
    d = sub.add_parser("demo", help="run the workflow on SIMULATED data")
    d.add_argument("--masses", default="0,5,10,20,30,40", help="kg, comma separated")
    for p in (f, d):
        p.add_argument("--lat", type=float, help="latitude in degrees, for local gravity")
        p.add_argument("--alt", type=float, default=0.0, help="altitude in metres")
        p.add_argument("--g", type=float, help="local gravity in m/s² (overrides --lat/--alt)")
        p.add_argument("--traceable", action="store_true", help="reference loads are traceable to a calibrated standard")
        p.add_argument("--out", default="calibration-out")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if a.g is not None:
        g = a.g
    elif a.lat is not None:
        g = local_gravity(a.lat, a.alt)
    else:
        ap.error("give --lat (and --alt) or --g: standard gravity is not your local gravity")
    if a.cmd == "fit":
        pts, title, notes = load_points_csv(a.csv, g), "FENRIR calibration report", ""
    else:
        pts = simulated_points([float(m) for m in a.masses.split(",")], g)
        title = "FENRIR calibration report — SIMULATED DATA"
        notes = "**This report was generated from the software simulator. It says nothing about a real device.**"
    res = fit(pts, traceable_reference=a.traceable)
    report = write_report(res, pts, a.out, g=g, title=title, notes=notes)
    print(report.read_text(encoding="utf-8"))
    print("CAL_WRITE arguments:", res.firmware_args(int(time.time())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
