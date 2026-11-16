"""Force metrics. Pure functions over (time, force) series; every window and
threshold is an explicit, documented parameter (see docs/requirements).

Definitions used here
---------------------
* Peak force: maximum of the series (optionally of a centred moving mean, to
  stop a single noisy sample from setting the peak).
* Onset: first sample at or above ``onset_n`` that stays there for
  ``hold_s``. A fixed absolute threshold is used because a relative one
  depends on the peak that the RFD is later compared with.
* RFD(t1,t2): (F(onset+t2) - F(onset+t1)) / (t2 - t1), force linearly
  interpolated between samples. Reported for 0-100 ms and 0-200 ms.
* Peak RFD: largest slope of a least-squares line over any ``window_s``
  window. With 80 Hz data a window shorter than ~50 ms holds fewer than four
  samples and is rejected.
* RFD 20-80 %: slope between the first crossings of 20 % and 80 % of peak.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RfdResult:
    onset_s: float
    rfd_0_100: float | None  # N/s
    rfd_0_200: float | None
    rfd_20_80: float | None
    peak_rfd: float | None
    peak_rfd_window_s: float


def _arr(t, f):
    t = np.asarray(t, dtype=float)
    f = np.asarray(f, dtype=float)
    if t.shape != f.shape or t.ndim != 1:
        raise ValueError("t and f must be 1-D and the same length")
    if t.size > 1 and np.any(np.diff(t) <= 0):
        raise ValueError("time must be strictly increasing")
    return t, f


def peak_force(t, f, smooth_s: float = 0.0) -> tuple[float, float]:
    """Returns (peak N, time s). ``smooth_s`` > 0 applies a centred moving mean."""
    t, f = _arr(t, f)
    if t.size == 0:
        raise ValueError("empty series")
    if smooth_s > 0 and t.size > 2:
        dt = float(np.median(np.diff(t)))
        n = max(1, int(round(smooth_s / dt)))
        if n > 1:
            f = np.convolve(f, np.ones(n) / n, mode="same")
    i = int(np.argmax(f))
    return float(f[i]), float(t[i])


def mean_force(t, f, t_start: float, t_end: float) -> float:
    """Time-weighted mean (trapezoidal) over [t_start, t_end]."""
    t, f = _arr(t, f)
    if not t_start < t_end:
        raise ValueError("empty interval")
    if t_start < t[0] or t_end > t[-1]:
        raise ValueError("interval outside the recording")
    grid = np.concatenate(([t_start], t[(t > t_start) & (t < t_end)], [t_end]))
    return float(np.trapezoid(np.interp(grid, t, f), grid) / (t_end - t_start))


def impulse(t, f, t_start: float, t_end: float) -> float:
    """Force-time integral in N*s."""
    return mean_force(t, f, t_start, t_end) * (t_end - t_start)


def time_under_tension(t, f, threshold_n: float) -> float:
    """Total time with force >= threshold, crossings linearly interpolated."""
    t, f = _arr(t, f)
    total = 0.0
    for i in range(t.size - 1):
        a, b = f[i] - threshold_n, f[i + 1] - threshold_n
        dt = t[i + 1] - t[i]
        if a >= 0 and b >= 0:
            total += dt
        elif a >= 0 > b:
            total += dt * a / (a - b)
        elif a < 0 <= b:
            total += dt * b / (b - a)
    return float(total)


def find_onset(t, f, onset_n: float = 20.0, hold_s: float = 0.05) -> float | None:
    """Interpolated time of the first sustained crossing of ``onset_n``."""
    t, f = _arr(t, f)
    above = f >= onset_n
    for i in np.flatnonzero(above):
        # first sample at or after the end of the hold window; it must exist
        # (recording long enough) and everything up to it must stay above
        j = int(np.searchsorted(t, t[i] + hold_s * 0.999, side="left"))
        if j < t.size and np.all(above[i:j + 1]):
            if i == 0:
                return float(t[0])
            f0, f1 = f[i - 1], f[i]
            return float(t[i - 1] + (onset_n - f0) / (f1 - f0) * (t[i] - t[i - 1]))
    return None


def _first_crossing(t, f, level: float, start: int = 0) -> float | None:
    for i in range(max(start, 1), t.size):
        if f[i - 1] < level <= f[i]:
            return float(t[i - 1] + (level - f[i - 1]) / (f[i] - f[i - 1]) * (t[i] - t[i - 1]))
    return None


def rfd(t, f, onset_n: float = 20.0, hold_s: float = 0.05, window_s: float = 0.05) -> RfdResult | None:
    """Rate of force development. Returns None when no onset is found."""
    t, f = _arr(t, f)
    onset = find_onset(t, f, onset_n, hold_s)
    if onset is None:
        return None

    def interval(t2: float) -> float | None:
        if onset + t2 > t[-1]:
            return None
        return float((np.interp(onset + t2, t, f) - np.interp(onset, t, f)) / t2)

    pk, t_pk = peak_force(t, f)
    i0 = int(np.searchsorted(t, onset))
    t20 = _first_crossing(t, f, 0.2 * pk, i0) if 0.2 * pk > onset_n else onset
    t80 = _first_crossing(t, f, 0.8 * pk, i0)
    r2080 = None
    if t20 is not None and t80 is not None and t80 > t20:
        r2080 = float(0.6 * pk / (t80 - t20))

    peak_rfd = None
    dt = float(np.median(np.diff(t))) if t.size > 1 else float("inf")
    n = int(round(window_s / dt)) + 1
    if n >= 4:  # a slope through fewer points is noise, not a rate
        end = int(np.searchsorted(t, t_pk, side="right"))
        best = None
        for i in range(i0, max(i0, end - n + 1)):
            tt, ff = t[i:i + n], f[i:i + n]
            slope = float(np.polyfit(tt - tt[0], ff, 1)[0])
            best = slope if best is None else max(best, slope)
        peak_rfd = best
    return RfdResult(onset, interval(0.1), interval(0.2), r2080, peak_rfd, window_s)


def fatigue_index(t, f, t_start: float, t_end: float) -> float:
    """Relative force loss across a sustained effort:
    1 - mean(last third) / mean(first third). 0 = no decline."""
    third = (t_end - t_start) / 3.0
    first = mean_force(t, f, t_start, t_start + third)
    last = mean_force(t, f, t_end - third, t_end)
    if first <= 0:
        raise ValueError("non-positive force in the first third")
    return 1.0 - last / first


def segment_contractions(t, f, threshold_n: float, min_duration_s: float = 0.5) -> list[tuple[float, float]]:
    """(start, end) of each effort above ``threshold_n`` — used for repeaters."""
    t, f = _arr(t, f)
    out, start = [], None
    for i in range(t.size):
        if f[i] >= threshold_n and start is None:
            start = t[i]
        elif f[i] < threshold_n and start is not None:
            if t[i] - start >= min_duration_s:
                out.append((float(start), float(t[i])))
            start = None
    if start is not None and t[-1] - start >= min_duration_s:
        out.append((float(start), float(t[-1])))
    return out
