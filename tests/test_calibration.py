import json

import pytest

from fenrir.calibration import (CalPoint, G_STANDARD, fit, load_points_csv, local_gravity, mass_to_force,
                                write_report)
from fenrir.calibration.__main__ import main as cal_main, simulated_points
from fenrir.simulator import LoadCellModel


def test_local_gravity_reference_values():
    assert local_gravity(0.0) == pytest.approx(9.78033, abs=1e-5)  # equator
    assert local_gravity(90.0) == pytest.approx(9.83219, abs=1e-5)  # pole
    assert local_gravity(45.0) == pytest.approx(9.80620, abs=1e-5)
    assert local_gravity(45.0, 1000.0) == pytest.approx(9.80620 - 0.003086, abs=1e-5)
    # using standard gravity instead of local gravity is a real error (0.05 % at the equator vs pole)
    assert abs(local_gravity(43.6, 150.0) - G_STANDARD) / G_STANDARD > 1e-4


def test_mass_to_force_and_buoyancy():
    assert mass_to_force(10.0, 9.805) == pytest.approx(98.05)
    assert mass_to_force(10.0, 9.805, 7850.0) == pytest.approx(98.05 * (1 - 1.2 / 7850))
    assert mass_to_force(10.0, 9.805, 1000.0) / 98.05 == pytest.approx(0.9988)


def test_exact_line_is_recovered():
    scale, zero = 9.31e-4, 14000
    pts = [CalPoint(f, zero + f / scale) for f in (0, 100, 200, 300, 400)]
    r = fit(pts)
    assert r.scale_n_per_count == pytest.approx(scale, rel=1e-9)
    assert r.zero_counts == zero and r.max_abs_residual_n < 1e-6


def test_partial_range_and_untraceable_are_stated():
    r = fit([CalPoint(f, 1000 * f) for f in (0, 100, 200, 400)])
    assert r.status == "VALID_PARTIAL_RANGE_UNTRACEABLE" and r.coverage == pytest.approx(0.2)
    text = " ".join(r.warnings)
    assert "NOT verified" in text and "not traceable" in text
    assert "hysteresis not assessed" in text and "repeatability not assessed" in text
    full = fit([CalPoint(f, 1000 * f) for f in (0, 500, 1000, 1500, 2000)], traceable_reference=True)
    assert full.status == "VALID_FULL_RANGE"
    assert fit([CalPoint(f, 1000 * f) for f in (0, 200, 400)], traceable_reference=True).status == "VALID_PARTIAL_RANGE_TRACEABLE"


def test_rejects_degenerate_input():
    with pytest.raises(ValueError):
        fit([CalPoint(0, 100)])
    with pytest.raises(ValueError):
        fit([CalPoint(100, 5), CalPoint(100, 9)])


def test_simulated_workflow_recovers_the_model_and_sees_its_hysteresis():
    g = local_gravity(43.6, 150.0)
    cell = LoadCellModel(seed=3)
    pts = simulated_points([0, 5, 10, 20, 30, 40], g)
    r = fit(pts)
    assert r.scale_n_per_count == pytest.approx(1 / cell.counts_per_n, rel=2e-3)
    assert abs(r.zero_counts - cell.zero_counts) < 300
    assert r.hysteresis_n is not None and 0.02 < r.hysteresis_n < 0.6  # model: 0.03 % FS
    assert r.noise_n_rms == pytest.approx(cell.noise_counts_rms / cell.counts_per_n, rel=0.2)
    assert r.max_ref_n == pytest.approx(40 * g * (1 - 1.2 / 7850), rel=1e-9)


def test_reference_uncertainty_enters_the_slope_uncertainty():
    pts = [CalPoint(f, 1000 * f, u_reference_n=0.01 * f) for f in (0, 100, 200, 400)]
    assert fit(pts).u_scale_rel == pytest.approx(0.01, rel=0.05)


def test_csv_loading_and_reproducible_report(tmp_path):
    csv = tmp_path / "pts.csv"
    csv.write_text("mass_kg,mean_counts,std_counts,n_samples,direction,u_mass_kg,density_kg_m3\n"
                   "0,14000,50,240,up,0,\n10,119300,52,240,up,0.01,7850\n20,224650,51,240,up,0.02,7850\n"
                   "10,119380,50,240,down,0.01,7850\n")
    g = 9.8043
    pts = load_points_csv(csv, g)
    assert pts[1].reference_n == pytest.approx(10 * g * (1 - 1.2 / 7850))
    assert pts[1].u_reference_n == pytest.approx(0.01 * g) and pts[3].direction == "down"
    r = fit(pts)
    a = write_report(r, pts, tmp_path / "a", g=g).read_text(encoding="utf-8")
    b = write_report(fit(load_points_csv(csv, g)), pts, tmp_path / "b", g=g).read_text(encoding="utf-8")
    assert a == b and r.input_sha256 in a and "Limits of this calibration" in a
    doc = json.loads((tmp_path / "a" / "calibration.json").read_text())
    assert doc["result"]["status"] == r.status and len(doc["points"]) == 4


def test_cli_requires_gravity_and_labels_simulated_output(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cal_main(["demo", "--out", str(tmp_path)])  # no --lat / --g
    assert cal_main(["demo", "--lat", "43.6", "--alt", "150", "--out", str(tmp_path)]) == 0
    assert "SIMULATED DATA" in capsys.readouterr().out
