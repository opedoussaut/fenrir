import numpy as np
import pytest

from fenrir import metrics


def ramp_hold(rate_hz=80.0, slope=2000.0, peak=500.0, t0=1.0, total=5.0):
    t = np.arange(0, total, 1 / rate_hz)
    f = np.clip((t - t0) * slope, 0, peak)
    return t, f


def test_peak_and_mean():
    t, f = ramp_hold()
    assert metrics.peak_force(t, f) == (500.0, pytest.approx(1.25))
    assert metrics.mean_force(t, f, 2.0, 4.0) == pytest.approx(500.0)
    assert metrics.mean_force(t, f, 1.0, 1.25) == pytest.approx(250.0, rel=1e-3)
    assert metrics.impulse(t, f, 2.0, 4.0) == pytest.approx(1000.0)
    with pytest.raises(ValueError):
        metrics.mean_force(t, f, 4.0, 9.0)  # outside the recording: refuse, do not extrapolate


def test_time_under_tension_interpolates_crossings():
    t = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    f = np.array([0.0, 100.0, 100.0, 0.0, 0.0])
    assert metrics.time_under_tension(t, f, 50.0) == pytest.approx(2.0)
    assert metrics.time_under_tension(t, f, 200.0) == 0.0


@pytest.mark.parametrize("rate", [80.0, 320.0])
def test_rfd_on_a_linear_ramp_is_the_slope(rate):
    t, f = ramp_hold(rate_hz=rate, slope=2000.0, peak=800.0)
    r = metrics.rfd(t, f, onset_n=20.0)
    assert r.onset_s == pytest.approx(1.01, abs=1e-6)
    assert r.rfd_0_100 == pytest.approx(2000.0, rel=1e-6)
    assert r.rfd_0_200 == pytest.approx(2000.0, rel=1e-6)
    assert r.rfd_20_80 == pytest.approx(2000.0, rel=1e-6)
    assert r.peak_rfd == pytest.approx(2000.0, rel=1e-3)


def test_rfd_needs_a_sustained_onset():
    t = np.arange(0, 3, 1 / 80)
    f = np.zeros_like(t)
    f[40] = 300.0  # a single spike is not an onset
    assert metrics.rfd(t, f) is None
    assert metrics.find_onset(t, f) is None


def test_peak_rfd_refuses_windows_with_too_few_samples():
    t, f = ramp_hold(rate_hz=80.0)
    assert metrics.rfd(t, f, window_s=0.02).peak_rfd is None  # 20 ms at 80 Hz = 2-3 samples
    assert metrics.rfd(t, f, window_s=0.05).peak_rfd is not None


def test_rfd_intervals_beyond_the_recording_are_none():
    t, f = ramp_hold(total=1.12)
    r = metrics.rfd(t, f)
    assert r.rfd_0_100 is not None and r.rfd_0_200 is None


def test_fatigue_index_and_segmentation():
    t = np.arange(0, 32, 1 / 80)
    f = np.where((t >= 1) & (t <= 31), 400 * (1 - 0.3 * (t - 1) / 30), 0.0)
    assert metrics.fatigue_index(t, f, 1.0, 31.0) == pytest.approx(1 - (1 - 0.25) / (1 - 0.05), rel=1e-3)
    reps = np.where((t % 10) < 7, 300.0, 0.0)
    segs = metrics.segment_contractions(t, reps, 150.0)
    assert len(segs) == 4 and segs[0][1] - segs[0][0] == pytest.approx(7.0, abs=0.02)


def test_rejects_non_monotonic_time():
    with pytest.raises(ValueError):
        metrics.peak_force([0, 1, 1], [1, 2, 3])


def test_onset_found_when_sample_period_does_not_divide_the_hold_window():
    # regression: a real ADC runs off-nominal (e.g. 80.96 Hz), so 4 periods < 50 ms
    t = np.arange(0, 4, 1 / 80.96)
    f = np.clip((t - 1.0) * 2000.0, 0, 500.0)
    r = metrics.rfd(t, f)
    assert r is not None and r.onset_s == pytest.approx(1.01, abs=1e-6)
    assert r.rfd_0_100 == pytest.approx(2000.0, rel=1e-6)
