"""FENRIR GATT protocol v1 codec (see protocol/fenrir-gatt-v1.md).

Mirrors firmware/src/core/protocol.c byte for byte; both are pinned to
protocol/vectors/v1.txt by tests.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field
from enum import IntEnum, IntFlag

PROTOCOL_MAJOR = 1
PROTOCOL_MINOR = 1

# Protocol 1.1 rates (ADS1220 turbo mode). SET_RATE still accepts the 1.0 values 80 and 320 and
# the device maps them; Status always reports the real rate.
RATE_LOW = 90
RATE_HIGH = 350
LEGACY_RATES = {80: RATE_LOW, 320: RATE_HIGH}

_BASE = "f3e7{:04x}-6b1d-4c8a-9e2f-5a1c0d7e4b90"
UUID_SERVICE = _BASE.format(1)
UUID_FORCE = _BASE.format(2)
UUID_CONTROL = _BASE.format(3)
UUID_STATUS = _BASE.format(4)
UUID_CALIBRATION = _BASE.format(5)
UUID_PROTOCOL = _BASE.format(6)

FORCE_HEADER_LEN = 12
FORCE_INVALID = -8388608
I24_MAX = 8388607
I24_MIN = -8388607
MAX_SAMPLES_PER_PACKET = 40
STATUS_LEN = 16
CALINFO_LEN = 20
BATTERY_UNKNOWN = 0xFF


class Format(IntEnum):
    RAW_FORCE = 0
    FORCE = 1


class Status(IntFlag):
    STREAMING = 1 << 0
    CAL_VALID = 1 << 1
    TARED = 1 << 2
    OVERLOAD = 1 << 3
    ADC_SATURATED = 1 << 4
    ADC_TIMEOUT = 1 << 5
    ADC_STUCK = 1 << 6
    SAMPLE_DROPPED = 1 << 7
    LOW_BATTERY = 1 << 8
    FILTERED = 1 << 9
    SLEW = 1 << 10
    CONFIG_CRC = 1 << 11
    ADC_FAULT = 1 << 12


#: Flags that mean "do not trust the samples in this packet".
FAULT_FLAGS = (Status.ADC_SATURATED | Status.ADC_TIMEOUT | Status.ADC_STUCK
               | Status.SAMPLE_DROPPED | Status.ADC_FAULT)


class Op(IntEnum):
    START = 0x01
    STOP = 0x02
    TARE = 0x03
    CLEAR_TARE = 0x04
    SET_RATE = 0x05
    SET_FILTER = 0x06
    CAL_WRITE = 0x10
    CAL_CLEAR = 0x11
    GET_STATUS = 0x20
    SLEEP = 0x30


class Result(IntEnum):
    OK = 0
    UNKNOWN_OP = 1
    BAD_LENGTH = 2
    BAD_PARAM = 3
    BAD_STATE = 4
    HW_ERROR = 5


class State(IntEnum):
    BOOT = 0
    IDLE = 1
    STREAMING = 2
    ERROR = 3


class Filter(IntEnum):
    NONE = 0
    MOVING_AVG = 1
    IIR = 2


class ProtocolError(ValueError):
    pass


def sample_size(fmt: int) -> int:
    if fmt == Format.RAW_FORCE:
        return 6
    if fmt == Format.FORCE:
        return 3
    raise ProtocolError(f"unknown sample format {fmt}")


def force_capacity(att_mtu: int, fmt: int) -> int:
    """Samples that fit in one notification (payload = ATT MTU - 3)."""
    n = (att_mtu - 3 - FORCE_HEADER_LEN) // sample_size(fmt)
    return max(0, min(n, MAX_SAMPLES_PER_PACKET))


def _i24(v: int) -> bytes:
    return (v & 0xFFFFFF).to_bytes(3, "little")


def _get_i24(b: bytes, o: int) -> int:
    return int.from_bytes(b[o:o + 3], "little", signed=True)


@dataclass(frozen=True)
class ForcePacket:
    seq: int
    t0_us: int
    dt_us: int
    status: Status
    format: Format
    raw: tuple[int, ...]  # empty for Format.FORCE
    force_cn: tuple[int | None, ...]  # None = device reported no valid force

    @property
    def count(self) -> int:
        return len(self.force_cn)

    def encode(self) -> bytes:
        n = self.count
        if not 1 <= n <= MAX_SAMPLES_PER_PACKET:
            raise ProtocolError("bad sample count")
        if self.format == Format.RAW_FORCE and len(self.raw) != n:
            raise ProtocolError("raw/force length mismatch")
        out = bytearray(struct.pack("<HIHHBB", self.seq & 0xFFFF, self.t0_us & 0xFFFFFFFF,
                                    self.dt_us, int(self.status), int(self.format), n))
        for i in range(n):
            if self.format == Format.RAW_FORCE:
                out += _i24(max(-8388608, min(I24_MAX, self.raw[i])))
            f = self.force_cn[i]
            out += _i24(FORCE_INVALID if f is None else max(I24_MIN, min(I24_MAX, f)))
        return bytes(out)

    @classmethod
    def decode(cls, data: bytes) -> "ForcePacket":
        if len(data) < FORCE_HEADER_LEN:
            raise ProtocolError("force packet shorter than header")
        seq, t0, dt, status, fmt, n = struct.unpack_from("<HIHHBB", data)
        ss = sample_size(fmt)
        if not 1 <= n <= MAX_SAMPLES_PER_PACKET or len(data) != FORCE_HEADER_LEN + ss * n:
            raise ProtocolError("force packet length does not match its header")
        raw, force = [], []
        o = FORCE_HEADER_LEN
        for _ in range(n):
            if fmt == Format.RAW_FORCE:
                raw.append(_get_i24(data, o))
                o += 3
            f = _get_i24(data, o)
            o += 3
            force.append(None if f == FORCE_INVALID else f)
        return cls(seq, t0, dt, Status(status), Format(fmt), tuple(raw), tuple(force))


@dataclass(frozen=True)
class DeviceStatus:
    state: State
    last_error: int
    flags: Status
    battery_pct: int | None
    battery_mv: int | None
    sample_rate: int
    filter_type: Filter
    filter_param: int
    uptime_s: int

    def encode(self) -> bytes:
        return struct.pack("<BBHBBHHBBI", self.state, self.last_error, int(self.flags),
                           BATTERY_UNKNOWN if self.battery_pct is None else self.battery_pct, 0,
                           self.battery_mv or 0, self.sample_rate, self.filter_type,
                           self.filter_param, self.uptime_s)

    @classmethod
    def decode(cls, data: bytes) -> "DeviceStatus":
        if len(data) != STATUS_LEN:
            raise ProtocolError("bad status length")
        st, err, fl, pct, _, mv, rate, ft, fp, up = struct.unpack("<BBHBBHHBBI", data)
        return cls(State(st), err, Status(fl), None if pct == BATTERY_UNKNOWN else pct,
                   mv or None, rate, Filter(ft), fp, up)


@dataclass(frozen=True)
class CalInfo:
    valid: bool
    n_points: int
    max_ref_n: int
    scale_n_per_count: float
    zero_counts: int
    tare_counts: int
    unix_time: int

    def encode(self) -> bytes:
        return struct.pack("<BBHfiiI", int(self.valid), self.n_points, self.max_ref_n,
                           self.scale_n_per_count, self.zero_counts, self.tare_counts, self.unix_time)

    @classmethod
    def decode(cls, data: bytes) -> "CalInfo":
        if len(data) != CALINFO_LEN:
            raise ProtocolError("bad calibration info length")
        v, n, mx, s, z, t, u = struct.unpack("<BBHfiiI", data)
        return cls(bool(v), n, mx, s, z, t, u)


# ---- Control point -----------------------------------------------------------
def cmd_start(fmt: Format = Format.RAW_FORCE, batch: int = 4) -> bytes:
    return bytes([Op.START, fmt, batch])


def cmd_simple(op: Op) -> bytes:
    return bytes([op])


def cmd_set_rate(sps: int) -> bytes:
    return struct.pack("<BH", Op.SET_RATE, sps)


def cmd_set_filter(kind: Filter, param: int = 0) -> bytes:
    return bytes([Op.SET_FILTER, kind, param])


def cmd_cal_write(scale_n_per_count: float, zero_counts: int, max_ref_n: int, n_points: int,
                  unix_time: int) -> bytes:
    return struct.pack("<BfiHBI", Op.CAL_WRITE, scale_n_per_count, zero_counts, max_ref_n,
                       n_points, unix_time)


@dataclass(frozen=True)
class Command:
    op: Op
    args: dict = field(default_factory=dict)


def parse_command(data: bytes) -> tuple[Result, Command | None]:
    """Same validation rules as fenrir_command_parse() in the firmware."""
    if len(data) < 1:
        return Result.BAD_LENGTH, None
    try:
        op = Op(data[0])
    except ValueError:
        return Result.UNKNOWN_OP, None
    p = data[1:]
    if op == Op.START:
        if len(p) != 2:
            return Result.BAD_LENGTH, None
        if p[0] not in (0, 1) or not 1 <= p[1] <= MAX_SAMPLES_PER_PACKET:
            return Result.BAD_PARAM, None
        return Result.OK, Command(op, {"format": Format(p[0]), "batch": p[1]})
    if op == Op.SET_RATE:
        if len(p) != 2:
            return Result.BAD_LENGTH, None
        sps = struct.unpack("<H", p)[0]
        sps = LEGACY_RATES.get(sps, sps)
        if sps not in (RATE_LOW, RATE_HIGH):
            return Result.BAD_PARAM, None
        return Result.OK, Command(op, {"sps": sps})
    if op == Op.SET_FILTER:
        if len(p) != 2:
            return Result.BAD_LENGTH, None
        t, param = p
        if t > 2 or (t == 1 and not 2 <= param <= 32) or (t == 2 and not 1 <= param <= 8):
            return Result.BAD_PARAM, None
        return Result.OK, Command(op, {"type": Filter(t), "param": param})
    if op == Op.CAL_WRITE:
        if len(p) != 15:
            return Result.BAD_LENGTH, None
        s, z, mx, n, u = struct.unpack("<fiHBI", p)
        if math.isnan(s) or not 1e-6 <= abs(s) <= 10.0 or n < 2:
            return Result.BAD_PARAM, None
        return Result.OK, Command(op, {"scale": s, "zero": z, "max_ref_n": mx, "n_points": n, "unix_time": u})
    return (Result.OK, Command(op)) if not p else (Result.BAD_LENGTH, None)


def decode_response(data: bytes) -> tuple[int, Result]:
    if len(data) != 2:
        raise ProtocolError("bad response length")
    return data[0], Result(data[1])
