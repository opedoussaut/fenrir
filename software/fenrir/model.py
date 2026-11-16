"""Force-data model: turns a stream of protocol packets into a timestamped
recording, tracking sequence gaps and device-reported faults.

The model is transport-independent (BLE, simulator, replayed file) and is the
reference for the LeBlond-side TypeScript implementation.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, field

from .protocol import FAULT_FLAGS, ForcePacket, Status

N_PER_KGF = 9.80665  # exact, by definition of the kilogram-force
N_PER_LBF = 4.4482216152605  # exact, by definition of the pound-force


def n_to_kgf(n: float) -> float:
    return n / N_PER_KGF


def n_to_lbf(n: float) -> float:
    return n / N_PER_LBF


@dataclass
class Sample:
    t_s: float  # seconds since the first sample of the recording (device clock)
    force_n: float | None  # None when the device flagged the value invalid
    raw: int | None  # untouched ADC counts when the stream carries them
    flags: int  # Status bits of the packet that carried the sample


@dataclass
class LinkStats:
    packets: int = 0
    samples: int = 0
    lost_packets: int = 0  # from sequence-number gaps
    lost_samples_est: int = 0  # estimated from the timestamp gap
    duplicate_or_reordered: int = 0
    fault_packets: int = 0

    @property
    def packet_loss_ratio(self) -> float:
        total = self.packets + self.lost_packets
        return self.lost_packets / total if total else 0.0


@dataclass
class Recording:
    """An ordered force recording plus everything needed to judge its quality."""
    samples: list[Sample] = field(default_factory=list)
    stats: LinkStats = field(default_factory=LinkStats)
    metadata: dict = field(default_factory=dict)
    filtered: bool = False  # True if the device applied a filter to force values
    calibrated: bool = True  # False as soon as one packet lacked CAL_VALID
    _last_seq: int | None = field(default=None, repr=False)
    _t_origin_us: int | None = field(default=None, repr=False)
    _last_t0: int | None = field(default=None, repr=False)
    _epoch_us: int = field(default=0, repr=False)  # accumulated 32-bit wraps
    _expected_next_us: int | None = field(default=None, repr=False)

    def add_packet(self, p: ForcePacket) -> None:
        st = self.stats
        if self._last_seq is not None:
            gap = (p.seq - self._last_seq) & 0xFFFF
            if gap == 0 or gap > 0x8000:
                st.duplicate_or_reordered += 1
                return  # never insert out-of-order data into the time series
            if gap > 1:
                st.lost_packets += gap - 1
        self._last_seq = p.seq

        # Unwrap the 32-bit microsecond clock (wraps every ~71.6 min).
        if self._last_t0 is not None and p.t0_us < self._last_t0 and self._last_t0 - p.t0_us > 1 << 31:
            self._epoch_us += 1 << 32
        self._last_t0 = p.t0_us
        t0 = self._epoch_us + p.t0_us
        if self._t_origin_us is None:
            self._t_origin_us = t0
        if self._expected_next_us is not None and p.dt_us:
            missing = round((t0 - self._expected_next_us) / p.dt_us)
            if missing > 0:
                st.lost_samples_est += missing
        self._expected_next_us = t0 + p.count * p.dt_us

        st.packets += 1
        st.samples += p.count
        if p.status & FAULT_FLAGS:
            st.fault_packets += 1
        if p.status & Status.FILTERED:
            self.filtered = True
        if not p.status & Status.CAL_VALID:
            self.calibrated = False
        for i in range(p.count):
            f = p.force_cn[i]
            self.samples.append(Sample(
                t_s=(t0 - self._t_origin_us + i * p.dt_us) / 1e6,
                force_n=None if f is None else f / 100.0,
                raw=p.raw[i] if p.raw else None,
                flags=int(p.status)))

    # ---- views ---------------------------------------------------------------
    def valid_series(self) -> tuple[list[float], list[float]]:
        t = [s.t_s for s in self.samples if s.force_n is not None]
        f = [s.force_n for s in self.samples if s.force_n is not None]
        return t, f

    def measured_rate_hz(self) -> float | None:
        if len(self.samples) < 2:
            return None
        span = self.samples[-1].t_s - self.samples[0].t_s
        return (len(self.samples) - 1 + self.stats.lost_samples_est) / span if span > 0 else None

    # ---- export --------------------------------------------------------------
    def to_csv(self) -> str:
        out = io.StringIO()
        w = csv.writer(out, lineterminator="\n")
        w.writerow(["t_s", "force_n", "raw_counts", "status_flags"])
        for s in self.samples:
            w.writerow([f"{s.t_s:.6f}", "" if s.force_n is None else f"{s.force_n:.2f}",
                        "" if s.raw is None else s.raw, s.flags])
        return out.getvalue()

    def to_json(self) -> str:
        return json.dumps({
            "schema": "fenrir.recording/1",
            "metadata": self.metadata,
            "filtered": self.filtered,
            "calibrated": self.calibrated,
            "link": {**asdict(self.stats), "packet_loss_ratio": self.stats.packet_loss_ratio},
            "columns": ["t_s", "force_n", "raw_counts", "status_flags"],
            "samples": [[round(s.t_s, 6), s.force_n, s.raw, s.flags] for s in self.samples],
        }, separators=(",", ":"))
