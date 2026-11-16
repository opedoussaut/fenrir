# Calibration procedure (home workflow)

Status: **procedure and software exist; never run on hardware.** The software has been exercised on
simulated data only.

## What a home calibration can and cannot establish

| Can | Cannot |
|---|---|
| Scale factor and zero within the loads you actually hang | Accuracy above your largest load |
| Noise, zero drift, short-term repeatability | Traceable accuracy (your masses are not calibrated standards) |
| Hysteresis between loading and unloading, within that span | Behaviour near 2000 N |

The tool states both limits in every report and stores the largest reference force in the device
(`max_ref_n`), so applications can mark readings above it as unverified.

**Needs an external calibrated reference or laboratory:** full-range accuracy (M-05), traceability,
and a proof load at 2000 N (V-15). Options: a university or industrial metrology lab, a calibration
service for force transducers, or a comparison in series with a recently calibrated dynamometer.

## Reference loads

| Reference | Realistic uncertainty | Comment |
|---|---|---|
| Water in containers, weighed on a kitchen scale (5 kg × 1 g) | 0.1–0.3 % | Cheap and good. Weigh container + water + hook. Give density 1000 for the buoyancy correction |
| Steel plates weighed on a verified scale | 0.2–0.5 % | Weigh each one; do not trust the cast-in number |
| Gym plates, nominal value | ~2 % (can be worse) | Only for a rough check |
| Class M1 calibration weights | ≤ 0.005 % | Traceable if certified; expensive |
| Calibrated reference load cell in series | per its certificate | The only practical route to full range |

Hang masses, never stand on or pull the device for calibration.

## Steps

1. Warm up: device powered and streaming for 5 minutes.
2. Hang the empty rigging (hook, sling) — this is the zero condition. Record a dwell:

   ```bash
   python -m fenrir.diagnostics --ble --dwell 3
   ```

   Note `mean_counts`, `std_counts`, `n_samples`.
3. Add masses in at least 4 steps up to the largest load available, waiting 10 s after each change
   before the 3 s dwell. Mark these rows `up`.
4. Remove masses in the same steps, marking rows `down` (hysteresis).
5. Repeat one mid-range load three times (repeatability).
6. Write the rows to a CSV:

   ```csv
   mass_kg,mean_counts,std_counts,n_samples,direction,u_mass_kg,density_kg_m3
   0,14021.3,52.1,240,up,0,
   5.012,19402.8,51.7,240,up,0.002,1000
   ```

7. Fit and produce the report. Latitude and altitude are required: the tool refuses to assume
   standard gravity (Toulouse is ≈ 43.6° N, 150 m → 9.8045 m/s²; using 9.80665 would be a 0.02 % error
   there and up to 0.26 % elsewhere on Earth).

   ```bash
   python -m fenrir.calibration fit points.csv --lat 43.6 --alt 150 --out calibration/2026-xx-xx
   ```

8. Review `report.md` and `calibration.png`: residuals should be small and without a bow shape;
   read the "Limits of this calibration" section.
9. Write the coefficients to the device (CAL_WRITE with the printed arguments). *A one-command writer
   is not implemented yet in the diagnostic tool.*
10. Keep the CSV, report and JSON in the repository as the calibration record.

## Zero drift and temperature

Leave the device streaming at rest for 30 minutes (test V-08), then repeat after moving it between a
cool and a warm room, noting both temperatures. These are observations, not corrections: the firmware
applies no temperature compensation.

## Validity

A calibration is no longer trusted if the device reports `CONFIG_CRC`, after any overload flag above
2200 N, after the eye bolts were re-seated, or after 12 months (proposed; no drift data yet).
