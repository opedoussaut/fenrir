from pathlib import Path

import pytest

from fenrir import protocol as P

VECTORS = dict(line.split() for line in
               (Path(__file__).parents[1] / "protocol" / "vectors" / "v1.txt").read_text().splitlines())
S = P.Status


def test_force_raw_matches_firmware_vector():
    pkt = P.ForcePacket(7, 1234567890, 12500, S.STREAMING | S.CAL_VALID | S.TARED, P.Format.RAW_FORCE,
                        (1000, 108374, -5, 8388607), (0, 10000, -1, None))
    assert pkt.encode().hex() == VECTORS["force_raw"]
    assert P.ForcePacket.decode(bytes.fromhex(VECTORS["force_raw"])) == pkt


def test_force_only_matches_firmware_vector():
    pkt = P.ForcePacket(65535, 1234567890, 3125, S.STREAMING | S.OVERLOAD | S.FILTERED, P.Format.FORCE,
                        (), (0, 10000, -1, None))
    assert pkt.encode().hex() == VECTORS["force_only"]
    assert P.ForcePacket.decode(bytes.fromhex(VECTORS["force_only"])) == pkt


def test_status_and_calinfo_match_firmware_vectors():
    st = P.DeviceStatus(P.State.STREAMING, 0, S.STREAMING | S.CAL_VALID, 87, 4012, 80, P.Filter.IIR, 2, 3600)
    assert st.encode().hex() == VECTORS["status"]
    assert P.DeviceStatus.decode(bytes.fromhex(VECTORS["status"])) == st
    ci = P.CalInfo(True, 5, 490, 15625 / 2**24, -20000, 150, 1794000000)
    assert ci.encode().hex() == VECTORS["calinfo"]
    assert P.CalInfo.decode(bytes.fromhex(VECTORS["calinfo"])) == ci
    assert P.decode_response(bytes.fromhex(VECTORS["response"])) == (P.Op.TARE, P.Result.BAD_STATE)


def test_unknown_battery_is_none_not_a_number():
    st = P.DeviceStatus(P.State.IDLE, 0, S(0), None, None, 80, P.Filter.NONE, 0, 1)
    assert P.DeviceStatus.decode(st.encode()).battery_pct is None


@pytest.mark.parametrize("mtu,fmt,expected", [(23, 0, 1), (23, 1, 2), (247, 0, 38), (517, 1, 40), (17, 1, 0)])
def test_capacity(mtu, fmt, expected):
    assert P.force_capacity(mtu, fmt) == expected


def test_force_never_aliases_the_invalid_sentinel():
    pkt = P.ForcePacket(0, 0, 12500, S(0), P.Format.FORCE, (), (-9_000_000,))
    assert P.ForcePacket.decode(pkt.encode()).force_cn == (P.I24_MIN,)


@pytest.mark.parametrize("data", [b"", b"\x00" * 11, bytes.fromhex("0700d2029649d43007000904e8"),
                                  bytes.fromhex(VECTORS["force_raw"])[:-1], bytes.fromhex(VECTORS["force_raw"]) + b"\x00"])
def test_malformed_force_packets_are_rejected(data):
    with pytest.raises(P.ProtocolError):
        P.ForcePacket.decode(data)


@pytest.mark.parametrize("data,result", [
    (b"", P.Result.BAD_LENGTH),
    (b"\x77", P.Result.UNKNOWN_OP),
    (P.cmd_start(P.Format.RAW_FORCE, 4), P.Result.OK),
    (bytes([P.Op.START, 0, 0]), P.Result.BAD_PARAM),
    (bytes([P.Op.START, 5, 4]), P.Result.BAD_PARAM),
    (bytes([P.Op.START, 0]), P.Result.BAD_LENGTH),
    (P.cmd_set_rate(320), P.Result.OK),
    (P.cmd_set_rate(100), P.Result.BAD_PARAM),
    (P.cmd_set_filter(P.Filter.MOVING_AVG, 1), P.Result.BAD_PARAM),
    (P.cmd_set_filter(P.Filter.IIR, 3), P.Result.OK),
    (P.cmd_cal_write(9.3e-4, 10000, 500, 5, 1794000000), P.Result.OK),
    (P.cmd_cal_write(0.0, 0, 500, 5, 0), P.Result.BAD_PARAM),
    (P.cmd_cal_write(float("nan"), 0, 500, 5, 0), P.Result.BAD_PARAM),
    (P.cmd_cal_write(9.3e-4, 0, 500, 1, 0), P.Result.BAD_PARAM),
    (bytes([P.Op.TARE, 1]), P.Result.BAD_LENGTH),
])
def test_command_validation_mirrors_firmware(data, result):
    assert P.parse_command(data)[0] == result
