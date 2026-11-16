"""Sensor and device simulator.

Everything produced here is SIMULATED. It exists to exercise the protocol,
data model, metrics and calibration software before hardware exists; its noise
and error figures are datasheet-derived assumptions, not measurements.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterator

import numpy as np

from .. import protocol as P

Profile = Callable[[float], float]  # time (s) -> applied force (N)

# Datasheet-derived defaults (see docs/architecture/feasibility.md §4):
# TAS501: 2.0 mV/V at capacity; NAU7802: gain 128, ratiometric, 24-bit bipolar.
NOMINAL_COUNTS_PER_N = 2.0e-3 * 128 * 2**23 / 2000.0  # ~1073.7
# 150 nV RMS input-referred (80 SPS, gain 128, datasheet headline) on a 3.0 V
# reference -> counts RMS. Assumption until measured on the real board.
NOISE_COUNTS_RMS_80SPS = 150e-9 * 128 / 3.0 * 2**23  # ~53.7


# ---- Force profiles ------------------------------------------------------------
def rest(force_n: float = 0.0) -> Profile:
    return lambda t: force_n


def max_pull(peak_n: float, t_start: float = 1.0, rise_s: float = 0.25, hold_s: float = 3.0,
             release_s: float = 0.3) -> Profile:
    """Isometric maximal pull: smooth (raised-cosine) rise, plateau, release."""
    def f(t: float) -> float:
        u = t - t_start
        if u <= 0:
            return 0.0
        if u < rise_s:
            return peak_n * 0.5 * (1 - math.cos(math.pi * u / rise_s))
        if u < rise_s + hold_s:
            return peak_n
        u -= rise_s + hold_s
        if u < release_s:
            return peak_n * 0.5 * (1 + math.cos(math.pi * u / release_s))
        return 0.0
    return f


def repeaters(force_n: float, work_s: float = 7.0, rest_s: float = 3.0, reps: int = 6,
              t_start: float = 1.0, fatigue_per_rep: float = 0.03) -> Profile:
    one = max_pull(1.0, 0.0, 0.2, work_s - 0.4, 0.2)

    def f(t: float) -> float:
        u = t - t_start
        if u < 0:
            return 0.0
        k, phase = divmod(u, work_s + rest_s)
        if k >= reps:
            return 0.0
        return force_n * (1 - fatigue_per_rep * k) * one(phase)
    return f


def sustained(force_n: float, duration_s: float = 30.0, t_start: float = 1.0, decline: float = 0.25) -> Profile:
    """Sustained effort whose force decays linearly by ``decline`` (fatigue)."""
    env = max_pull(1.0, t_start, 0.3, duration_s - 0.6, 0.3)
    return lambda t: force_n * env(t) * (1 - decline * min(max((t - t_start) / duration_s, 0.0), 1.0))


def staircase(levels_n: list[float], dwell_s: float = 4.0) -> Profile:
    """Static steps, e.g. for a calibration run (up then down)."""
    return lambda t: levels_n[min(int(t // dwell_s), len(levels_n) - 1)] if t >= 0 else 0.0


# ---- Sensor model ----------------------------------------------------------------
@dataclass
class LoadCellModel:
    capacity_n: float = 2000.0
    counts_per_n: float = NOMINAL_COUNTS_PER_N * 1.004  # unit-to-unit sensitivity error
    zero_counts: float = 14_000.0  # zero balance (datasheet: within +-1 % FS)
    noise_counts_rms: float = NOISE_COUNTS_RMS_80SPS
    nonlinearity: float = 0.0003  # fraction of FS, bow shape (datasheet 0.03 % FS)
    hysteresis: float = 0.0003  # fraction of FS between loading and unloading
    zero_drift_counts_per_s: float = 0.0
    seed: int = 1
    _rng: np.random.Generator = field(init=False, repr=False)
    _prev: float = field(default=0.0, init=False, repr=False)
    _descending: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def counts(self, force_n: float, t: float) -> int:
        fs = self.capacity_n
        x = force_n / fs
        if force_n < self._prev - 1e-9:
            self._descending = True
        elif force_n > self._prev + 1e-9:
            self._descending = False
        self._prev = force_n
        err = self.nonlinearity * fs * 4 * x * (1 - x)  # zero at 0 and at capacity
        if self._descending:
            err += self.hysteresis * fs * 4 * x * (1 - x)
        ideal = self.zero_counts + (force_n + err) * self.counts_per_n + self.zero_drift_counts_per_s * t
        noisy = ideal + self._rng.normal(0.0, self.noise_counts_rms)
        return int(max(-8388608, min(8388607, round(noisy))))  # the ADC clips at its rails


# ---- Mock device --------------------------------------------------------------------
@dataclass
class Faults:
    packet_loss: float = 0.0  # probability a notification never arrives
    stuck_between: tuple[float, float] | None = None  # ADC returns a frozen code
    saturate_between: tuple[float, float] | None = None  # input pinned at +rail
    dropout_between: tuple[float, float] | None = None  # no conversions at all


class MockDevice:
    """Behavioural model of the FENRIR firmware behind the GATT protocol.

    It follows the same rules as firmware/src (command validation is shared
    logic in ``protocol.parse_command``), but it is a model: firmware host
    tests, not this class, are the evidence for firmware behaviour.
    """

    OVERLOAD_CN = 220_000
    STUCK_SAMPLES = 40

    def __init__(self, profile: Profile, cell: LoadCellModel | None = None, *, sample_rate: int = 80,
                 rate_error: float = 0.0, att_mtu: int = 247, faults: Faults | None = None,
                 cal: P.CalInfo | None = None, seed: int = 7) -> None:
        self.profile = profile
        self.cell = cell or LoadCellModel()
        self.sample_rate = sample_rate
        self.rate_error = rate_error  # ADC oscillator error (fraction); device reports true dt
        self.att_mtu = att_mtu
        self.faults = faults or Faults()
        self._rng = np.random.default_rng(seed)
        self.state = P.State.IDLE
        self.scale = 1.0 / NOMINAL_COUNTS_PER_N
        self.zero = 0
        self.tare = 0
        self.cal_valid = False
        self.cal_points = 0
        self.cal_max_ref = 0
        self.cal_time = 0
        if cal:
            self.scale, self.zero, self.cal_valid = cal.scale_n_per_count, cal.zero_counts, cal.valid
            self.cal_points, self.cal_max_ref, self.cal_time = cal.n_points, cal.max_ref_n, cal.unix_time
        self.format = P.Format.RAW_FORCE
        self.batch = 4
        self.seq = 0
        self.t = 0.0  # device time, seconds
        self._t0_offset_us = 4_294_000_000  # start near the 32-bit wrap on purpose
        self._last_raw: int | None = None
        self._same = 0
        self.responses: list[bytes] = []

    # -- characteristics --------------------------------------------------------
    @property
    def dt(self) -> float:
        return 1.0 / (self.sample_rate * (1.0 + self.rate_error))

    def flags(self) -> P.Status:
        f = P.Status(0)
        if self.state == P.State.STREAMING:
            f |= P.Status.STREAMING
        if self.cal_valid:
            f |= P.Status.CAL_VALID
        if self.tare:
            f |= P.Status.TARED
        return f

    def status(self) -> P.DeviceStatus:
        return P.DeviceStatus(self.state, 0, self.flags(), 87, 4012, self.sample_rate, P.Filter.NONE, 0, int(self.t))

    def calinfo(self) -> P.CalInfo:
        return P.CalInfo(self.cal_valid, self.cal_points, self.cal_max_ref, self.scale, self.zero, self.tare, self.cal_time)

    def _raw_now(self) -> int | None:
        fz = self.faults
        if fz.dropout_between and fz.dropout_between[0] <= self.t < fz.dropout_between[1]:
            return None
        if fz.saturate_between and fz.saturate_between[0] <= self.t < fz.saturate_between[1]:
            return 8388607
        if fz.stuck_between and fz.stuck_between[0] <= self.t < fz.stuck_between[1] and self._last_raw is not None:
            return self._last_raw
        return self.cell.counts(self.profile(self.t), self.t)

    # -- control point ------------------------------------------------------------
    def write_control(self, data: bytes) -> bytes:
        res, cmd = P.parse_command(data)
        op = data[0] if data else 0
        if res == P.Result.OK and cmd is not None:
            res = self._apply(cmd)
        resp = bytes([op, res])
        self.responses.append(resp)
        return resp

    def _apply(self, cmd: P.Command) -> P.Result:
        a = cmd.args
        if cmd.op == P.Op.START:
            cap = P.force_capacity(self.att_mtu, a["format"])
            if cap == 0:
                return P.Result.BAD_STATE
            self.format, self.batch = a["format"], min(a["batch"], cap)
            self.seq = 0
            self.state = P.State.STREAMING
        elif cmd.op == P.Op.STOP:
            self.state = P.State.IDLE
        elif cmd.op == P.Op.TARE:
            vals = []
            for _ in range(40):
                r = self._raw_now()
                self.t += self.dt
                if r is None:
                    return P.Result.HW_ERROR
                vals.append(r)
            if max(vals) - min(vals) > 2200:
                return P.Result.BAD_STATE  # not at rest
            self.tare = round(sum(vals) / len(vals)) - self.zero
        elif cmd.op == P.Op.CLEAR_TARE:
            self.tare = 0
        elif cmd.op == P.Op.SET_RATE:
            if self.state == P.State.STREAMING:
                return P.Result.BAD_STATE
            self.sample_rate = a["sps"]
        elif cmd.op == P.Op.CAL_WRITE:
            if self.state == P.State.STREAMING:
                return P.Result.BAD_STATE
            self.scale, self.zero, self.tare = a["scale"], a["zero"], 0
            self.cal_max_ref, self.cal_points, self.cal_time = a["max_ref_n"], a["n_points"], a["unix_time"]
            self.cal_valid = True
        elif cmd.op == P.Op.CAL_CLEAR:
            if self.state == P.State.STREAMING:
                return P.Result.BAD_STATE
            self.scale, self.zero, self.tare, self.cal_valid = 1.0 / NOMINAL_COUNTS_PER_N, 0, 0, False
        return P.Result.OK

    # -- streaming -------------------------------------------------------------------
    def notifications(self, duration_s: float) -> Iterator[bytes]:
        """Yields the force notifications a client would receive over
        ``duration_s`` of device time (lost ones are simply not yielded)."""
        end = self.t + duration_s
        raws: list[int] = []
        forces: list[int | None] = []
        t0 = 0.0
        sticky = P.Status(0)
        while self.t < end and self.state == P.State.STREAMING:
            raw = self._raw_now()
            now = self.t
            self.t += self.dt
            if raw is None:
                sticky |= P.Status.ADC_TIMEOUT | P.Status.SAMPLE_DROPPED
                continue
            self._same = self._same + 1 if raw == self._last_raw else 0
            self._last_raw = raw
            cn: int | None = round((raw - self.zero - self.tare) * float(np.float32(self.scale)) * 100)
            if raw >= 8388607 - 15 or raw <= -8388608 + 15:
                sticky |= P.Status.ADC_SATURATED
                cn = None
            elif abs(cn) > self.OVERLOAD_CN:
                sticky |= P.Status.OVERLOAD
            if self._same >= self.STUCK_SAMPLES:
                sticky |= P.Status.ADC_STUCK
            if not raws:
                t0 = now
            raws.append(raw)
            forces.append(cn)
            if len(raws) >= self.batch:
                pkt = P.ForcePacket(self.seq, (int(round(t0 * 1e6)) + self._t0_offset_us) & 0xFFFFFFFF,
                                    int(round(self.dt * 1e6)), self.flags() | sticky, self.format,
                                    tuple(raws) if self.format == P.Format.RAW_FORCE else (), tuple(forces))
                self.seq = (self.seq + 1) & 0xFFFF
                raws, forces, sticky = [], [], P.Status(0)
                if self._rng.random() >= self.faults.packet_loss:
                    yield pkt.encode()
