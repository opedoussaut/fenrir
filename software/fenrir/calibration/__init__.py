"""Calibration maths and report generation.

A calibration made with known masses is only as good as (a) how well the
masses are known, (b) local gravity, and (c) the range covered. This module
keeps those three things explicit in its result instead of hiding them behind
a single "calibrated" flag.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

CAPACITY_N = 2000.0
G_STANDARD = 9.80665
AIR_DENSITY = 1.2  # kg/m^3, typical indoor air


def local_gravity(latitude_deg: float, altitude_m: float = 0.0) -> float:
    """Normal gravity on the WGS84 ellipsoid (Somigliana) with a free-air
    altitude correction. Typical error vs. a surveyed value: < 5e-4 m/s^2
    (0.005 %), from local anomalies this formula cannot know."""
    s2 = math.sin(math.radians(latitude_deg)) ** 2
    g0 = 9.7803253359 * (1 + 0.00193185265241 * s2) / math.sqrt(1 - 0.00669437999013 * s2)
    return g0 - 3.086e-6 * altitude_m


def mass_to_force(mass_kg: float, g: float, density_kg_m3: float | None = None) -> float:
    """Weight of a mass hanging in air. ``density_kg_m3`` enables the air
    buoyancy correction (steel ~7850: -0.015 %; water ~1000: -0.12 %)."""
    buoyancy = 1.0 - AIR_DENSITY / density_kg_m3 if density_kg_m3 else 1.0
    return mass_kg * g * buoyancy


@dataclass(frozen=True)
class CalPoint:
    reference_n: float  # applied force
    mean_counts: float  # mean raw ADC counts over the dwell
    std_counts: float = 0.0  # standard deviation over the dwell
    n_samples: int = 0
    direction: str = "up"  # "up" (loading) or "down" (unloading)
    u_reference_n: float = 0.0  # standard uncertainty of the reference force


@dataclass
class CalResult:
    scale_n_per_count: float
    zero_counts: int
    n_points: int
    max_ref_n: float
    coverage: float  # max_ref_n / capacity
    residuals_n: list[float]
    max_abs_residual_n: float
    nonlinearity_pct_span: float  # max |residual| as % of the calibrated span
    hysteresis_n: float | None  # max |up - down| at matched loads
    repeatability_n: float | None  # max spread between repeats at one load/direction
    noise_n_rms: float | None  # median dwell std, in newtons
    u_scale_rel: float  # relative standard uncertainty of the slope (fit + reference)
    traceable_reference: bool
    status: str
    warnings: list[str] = field(default_factory=list)
    input_sha256: str = ""

    def firmware_args(self, unix_time: int) -> dict:
        return {"scale_n_per_count": self.scale_n_per_count, "zero_counts": self.zero_counts,
                "max_ref_n": int(round(self.max_ref_n)), "n_points": self.n_points, "unix_time": unix_time}


def _digest(points: list[CalPoint]) -> str:
    blob = json.dumps([asdict(p) for p in points], sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def fit(points: list[CalPoint], *, traceable_reference: bool = False, capacity_n: float = CAPACITY_N) -> CalResult:
    """Least-squares straight line through (counts, reference force)."""
    if len(points) < 2:
        raise ValueError("need at least two calibration points (zero and one load)")
    x = np.array([p.mean_counts for p in points], float)
    y = np.array([p.reference_n for p in points], float)
    if np.ptp(y) <= 0 or np.ptp(x) <= 0:
        raise ValueError("calibration points must span a non-zero load range")
    scale, intercept = np.polyfit(x, y, 1)  # y = scale * x + intercept
    zero = -intercept / scale
    resid = y - (scale * x + intercept)
    span = float(np.ptp(y))
    max_ref = float(np.max(np.abs(y)))

    def by_load(direction: str) -> dict[float, list[float]]:
        d: dict[float, list[float]] = {}
        for p in points:
            if p.direction == direction:
                d.setdefault(round(p.reference_n, 3), []).append(p.mean_counts * scale)
        return d

    up, down = by_load("up"), by_load("down")
    common = [k for k in up if k in down and k != round(float(np.min(y)), 3) and k != round(float(np.max(y)), 3)]
    hysteresis = max((abs(np.mean(up[k]) - np.mean(down[k])) for k in common), default=None)
    repeats = [float(np.ptp(v)) for d in (up, down) for v in d.values() if len(v) > 1]
    repeatability = max(repeats) if repeats else None
    stds = [p.std_counts for p in points if p.std_counts > 0]
    noise = float(np.median(stds) * abs(scale)) if stds else None

    # Slope uncertainty: statistical part from the fit + the reference itself
    # (taken at the largest load, where it dominates the slope).
    dof = len(points) - 2
    u_fit = math.sqrt(float(np.sum(resid ** 2)) / dof / float(np.sum((x - x.mean()) ** 2))) / abs(scale) if dof > 0 else float("nan")
    u_ref = max((p.u_reference_n / abs(p.reference_n) for p in points if p.reference_n), default=0.0)
    u_scale = math.hypot(0.0 if math.isnan(u_fit) else u_fit, u_ref)

    warnings: list[str] = []
    coverage = max_ref / capacity_n
    if coverage < 0.8:
        warnings.append(
            f"Calibrated up to {max_ref:.0f} N = {coverage:.0%} of the {capacity_n:.0f} N range. "
            "Readings above that are an extrapolation of a straight line and are NOT verified.")
    if not traceable_reference:
        warnings.append("Reference loads are not traceable to a calibrated standard; absolute accuracy "
                        "is bounded by how well the masses and local gravity are known.")
    if dof <= 0:
        warnings.append("Only two points: linearity cannot be assessed.")
    if hysteresis is None:
        warnings.append("No matched loading/unloading points: hysteresis not assessed.")
    if repeatability is None:
        warnings.append("No repeated points: repeatability not assessed.")
    if all(p.u_reference_n == 0 for p in points if p.reference_n):
        warnings.append("No reference uncertainty given: slope uncertainty covers fit scatter only.")

    if coverage >= 0.8 and traceable_reference:
        status = "VALID_FULL_RANGE"
    elif traceable_reference:
        status = "VALID_PARTIAL_RANGE_TRACEABLE"
    else:
        status = "VALID_PARTIAL_RANGE_UNTRACEABLE" if coverage < 0.8 else "VALID_FULL_RANGE_UNTRACEABLE"

    return CalResult(float(scale), int(round(zero)), len(points), max_ref, coverage, [float(r) for r in resid],
                     float(np.max(np.abs(resid))), float(np.max(np.abs(resid)) / span * 100),
                     None if hysteresis is None else float(hysteresis), repeatability, noise, u_scale,
                     traceable_reference, status, warnings, _digest(points))


# ---- I/O -------------------------------------------------------------------------
def load_points_csv(path: str | Path, g: float) -> list[CalPoint]:
    """CSV columns: ``mass_kg`` or ``force_n``; ``mean_counts``; optional
    ``std_counts``, ``n_samples``, ``direction``, ``u_mass_kg``/``u_force_n``,
    ``density_kg_m3``."""
    pts = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            num = lambda k, d=0.0: float(row[k]) if row.get(k) not in (None, "") else d  # noqa: E731
            if row.get("force_n") not in (None, ""):
                ref, u = num("force_n"), num("u_force_n")
            else:
                dens = num("density_kg_m3") or None
                ref = mass_to_force(num("mass_kg"), g, dens)
                u = num("u_mass_kg") * g
            pts.append(CalPoint(ref, num("mean_counts"), num("std_counts"), int(num("n_samples")),
                                row.get("direction") or "up", u))
    return pts


def write_report(result: CalResult, points: list[CalPoint], out_dir: str | Path, *, g: float,
                 title: str = "FENRIR calibration report", notes: str = "") -> Path:
    """Writes report.md, calibration.json and (if matplotlib is installed)
    calibration.png. Output depends only on the inputs, so it is reproducible."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "calibration.json").write_text(json.dumps(
        {"schema": "fenrir.calibration/1", "g_m_s2": g, "points": [asdict(p) for p in points], "result": asdict(result)},
        indent=2))

    def opt(v, unit="N", fmt=".2f"):
        return "not assessed" if v is None else f"{v:{fmt}} {unit}"

    lines = [f"# {title}", ""]
    if notes:
        lines += [notes, ""]
    lines += [
        f"- Status: **{result.status}**",
        f"- Scale: {result.scale_n_per_count:.9g} N/count; zero: {result.zero_counts} counts",
        f"- Points: {result.n_points}; largest reference: {result.max_ref_n:.1f} N "
        f"({result.coverage:.0%} of {CAPACITY_N:.0f} N)",
        f"- Gravity used: {g:.5f} m/s²",
        f"- Max residual: {result.max_abs_residual_n:.2f} N ({result.nonlinearity_pct_span:.3f} % of calibrated span)",
        f"- Hysteresis (matched loads): {opt(result.hysteresis_n)}",
        f"- Repeatability (repeat spread): {opt(result.repeatability_n)}",
        f"- Noise at rest (median dwell σ): {opt(result.noise_n_rms, 'N RMS', '.3f')}",
        f"- Slope standard uncertainty: {result.u_scale_rel * 100:.3f} %",
        f"- Input SHA-256: `{result.input_sha256}`",
        "", "## Limits of this calibration", ""]
    lines += [f"- {w}" for w in result.warnings] or ["- none recorded"]
    lines += ["", "## Points", "", "| reference N | direction | mean counts | σ counts | residual N |", "|---:|---|---:|---:|---:|"]
    for p, r in zip(points, result.residuals_n):
        lines.append(f"| {p.reference_n:.2f} | {p.direction} | {p.mean_counts:.1f} | {p.std_counts:.1f} | {r:+.2f} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return out / "report.md"
    fig, (a, b) = plt.subplots(2, 1, figsize=(7, 7), sharex=True)
    xs = np.array([p.reference_n for p in points])
    for direction, marker in (("up", "^"), ("down", "v")):
        sel = [i for i, p in enumerate(points) if p.direction == direction]
        a.plot(xs[sel], [points[i].mean_counts for i in sel], marker, label=f"{direction}loading" if direction == "up" else "unloading")
        b.plot(xs[sel], [result.residuals_n[i] for i in sel], marker)
    grid = np.linspace(xs.min(), xs.max(), 50)
    a.plot(grid, grid / result.scale_n_per_count + result.zero_counts, "-", lw=1, label="fit")
    a.set_ylabel("raw ADC counts")
    a.legend()
    b.axhline(0, lw=0.8)
    b.set_ylabel("residual (N)")
    b.set_xlabel("reference force (N)")
    a.set_title(f"{title}\n{result.status}, up to {result.max_ref_n:.0f} N")
    fig.tight_layout()
    fig.savefig(out / "calibration.png", dpi=120, metadata={"Software": None})
    plt.close(fig)
    return out / "report.md"
