import json

import numpy as np
import pytest

from fenrir import metrics, protocol as P
from fenrir.model import N_PER_KGF, Recording, n_to_kgf, n_to_lbf
from fenrir.simulator import Faults, LoadCellModel, MockDevice, max_pull, rest


def calibrated_device(profile, **kw):
    cell = kw.pop("cell", None) or LoadCellModel()
    cal = P.CalInfo(True, 6, 392, 1 / cell.counts_per_n, int(cell.zero_counts), 0, 0)
    return MockDevice(profile, cell, cal=cal, **kw)


def record(dev, seconds, fmt=P.Format.RAW_FORCE, batch=4):
    assert dev.write_control(P.cmd_start(fmt, batch)) == bytes([P.Op.START, P.Result.OK])
    rec = Recording()
    for n in dev.notifications(seconds):
        rec.add_packet(P.ForcePacket.decode(n))
    return rec


def test_units():
    assert n_to_kgf(N_PER_KGF) == pytest.approx(1.0)
    assert n_to_lbf(2000.0) == pytest.approx(449.6179, abs=1e-4)


def test_clean_stream_has_no_loss_and_true_rate():
    rec = record(calibrated_device(rest(), rate_error=0.012), 10)
    assert rec.stats.lost_packets == 0 and rec.stats.lost_samples_est == 0
    # the ADC runs 1.2 % fast; the recording must show the real rate, not 80.0
    assert rec.measured_rate_hz() == pytest.approx(80 * 1.012, rel=2e-3)
    assert rec.calibrated and not rec.filtered


def test_timestamps_survive_the_32_bit_wrap():
    rec = record(calibrated_device(rest()), 5)  # the mock starts 0.97 s before the wrap
    t = np.array([s.t_s for s in rec.samples])
    assert np.all(np.diff(t) > 0) and t[-1] == pytest.approx(5.0, abs=0.1)


def test_packet_loss_is_counted_not_hidden():
    dev = calibrated_device(rest(), faults=Faults(packet_loss=0.1), seed=11)
    rec = record(dev, 30)
    sent = dev.seq
    assert rec.stats.packets + rec.stats.lost_packets == pytest.approx(sent, abs=1)  # a lost tail packet is invisible
    assert 0.05 < rec.stats.packet_loss_ratio < 0.15
    assert rec.stats.lost_samples_est == rec.stats.lost_packets * 4
    # time axis keeps its gaps: no samples are invented or shifted
    assert rec.samples[-1].t_s == pytest.approx(30.0, abs=0.2)


def test_duplicates_and_reordering_are_dropped():
    dev = calibrated_device(rest())
    dev.write_control(P.cmd_start())
    pkts = [P.ForcePacket.decode(n) for n in dev.notifications(1)]
    rec = Recording()
    for p in (pkts[0], pkts[1], pkts[1], pkts[0], pkts[2]):
        rec.add_packet(p)
    assert rec.stats.packets == 3 and rec.stats.duplicate_or_reordered == 2
    assert len(rec.samples) == 12


def test_peak_and_rfd_recovered_from_a_simulated_pull():
    peak, rise = 600.0, 0.25
    rec = record(calibrated_device(max_pull(peak, 1.0, rise, 3.0), sample_rate=80), 6)
    t, f = rec.valid_series()
    pk, _ = metrics.peak_force(t, f, smooth_s=0.1)
    assert pk == pytest.approx(peak, abs=1.5)  # calibration model error + noise
    r = metrics.rfd(t, f)
    assert r is not None and r.onset_s == pytest.approx(1.0 + 0.029, abs=0.02)
    # raised-cosine rise: 20->80 % takes (acos(-0.6)-acos(0.6))/pi * rise
    assert r.rfd_20_80 == pytest.approx(0.6 * peak / (0.4097 * rise), rel=0.08)
    assert r.peak_rfd == pytest.approx(np.pi * peak / (2 * rise), rel=0.10)


def test_uncalibrated_device_is_flagged_through_to_the_recording():
    rec = record(MockDevice(rest()), 1)
    assert not rec.calibrated


def test_saturation_yields_invalid_samples_not_numbers():
    dev = calibrated_device(rest(), faults=Faults(saturate_between=(1.0, 2.0)))
    rec = record(dev, 3)
    bad = [s for s in rec.samples if s.force_n is None]
    assert 70 <= len(bad) <= 90
    assert all(s.raw == 8388607 and s.flags & P.Status.ADC_SATURATED for s in bad)
    assert rec.stats.fault_packets >= 20
    t, f = rec.valid_series()
    assert max(f) < 5  # the rail value never leaks into the force series


def test_stuck_adc_and_dropout_are_reported():
    rec = record(calibrated_device(rest(), faults=Faults(stuck_between=(1.0, 2.5))), 3)
    assert any(s.flags & P.Status.ADC_STUCK for s in rec.samples)
    rec = record(calibrated_device(rest(), faults=Faults(dropout_between=(1.0, 1.5))), 3)
    assert any(s.flags & P.Status.ADC_TIMEOUT for s in rec.samples)
    assert rec.stats.lost_samples_est == pytest.approx(40, abs=2)  # 0.5 s of missing samples


def test_overload_is_flagged():
    rec = record(calibrated_device(rest(2300.0)), 1)
    assert all(s.flags & P.Status.OVERLOAD for s in rec.samples)


def test_small_mtu_falls_back_to_fewer_samples_per_packet():
    dev = calibrated_device(rest(), att_mtu=23)
    rec = record(dev, 1, batch=8)
    assert dev.batch == 1 and rec.stats.samples == pytest.approx(80, abs=1)


def test_tare_and_state_rules():
    dev = calibrated_device(rest(50.0))
    assert dev.write_control(P.cmd_simple(P.Op.TARE))[1] == P.Result.OK
    rec = record(dev, 1)
    assert abs(np.mean([s.force_n for s in rec.samples])) < 0.05
    assert all(s.flags & P.Status.TARED for s in rec.samples)
    assert dev.write_control(P.cmd_set_rate(320))[1] == P.Result.BAD_STATE  # not while streaming
    assert dev.write_control(P.cmd_cal_write(1e-3, 0, 400, 5, 0))[1] == P.Result.BAD_STATE
    moving = calibrated_device(max_pull(500, 0.0, 0.4, 2))
    assert moving.write_control(P.cmd_simple(P.Op.TARE))[1] == P.Result.BAD_STATE  # refuses to tare under load


def test_exports_keep_raw_and_invalid_samples():
    rec = record(calibrated_device(rest(), faults=Faults(saturate_between=(0.0, 0.1))), 0.5)
    doc = json.loads(rec.to_json())
    assert doc["schema"] == "fenrir.recording/1" and doc["columns"][2] == "raw_counts"
    assert doc["samples"][0][1] is None and doc["samples"][0][2] == 8388607
    rows = rec.to_csv().splitlines()
    assert rows[0] == "t_s,force_n,raw_counts,status_flags" and rows[1].split(",")[1] == ""
    assert len(rows) == len(rec.samples) + 1
