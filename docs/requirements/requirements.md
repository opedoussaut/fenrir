# FENRIR requirements

Version 0.1 — 2026-11-16. Source: project brief v1.0. Each requirement has an ID used by the
[verification matrix](../verification/verification-matrix.md) and the [decision log](../decisions/decision-log.md).

Words used precisely in this project:

| Word | Meaning |
|---|---|
| **Target** | A limit we design for. Not evidence. |
| **Estimate** | A number computed from datasheets or models. |
| **Simulated / software-tested** | Shown by code running on a PC. |
| **Measured** | Read from an instrument on real hardware. |
| **Validated** | Measured against an independent reference, with a record. |

Nothing in this repository is *measured* or *validated* yet: no hardware exists.

## Functional

| ID | Requirement |
|---|---|
| F-01 | Measure tension with a strain-gauge load cell. |
| F-02 | Report force in N; applications also show kgf (÷ 9.80665) and lbf (÷ 4.4482216152605). |
| F-03 | Timestamp every sample with the device clock; report the real sample period. |
| F-04 | Deliver at least 80 real samples per second; 320 SPS available as an option. |
| F-05 | Stream over Bluetooth LE with a documented, versioned protocol. |
| F-06 | Tare on command; refuse to tare while the load is changing. |
| F-07 | Store calibration persistently with integrity check; expose its status and verified range. |
| F-08 | Keep raw ADC counts available and distinct from scaled and filtered force. |
| F-09 | Detect and report: ADC saturation, missing conversions, frozen ADC, overload, lost samples, corrupt configuration. |
| F-10 | Stop streaming on disconnect and recover by re-advertising. |
| F-11 | Report battery level only when measured; USB-C charging. |
| F-12 | Identify itself: model, serial, firmware and hardware revision, protocol version. |
| F-13 | Host software computes peak force, mean over an interval, time under tension, RFD and fatigue index with documented definitions. |
| F-14 | Export recordings as CSV and structured JSON including raw counts and link statistics. |
| F-15 | LeBlond integration through a device abstraction, usable over more than one transport. |
| F-16 | Status indicator (LED). *Not implemented in firmware yet.* |

## Measurement performance — proposed acceptance limits

Range: **0–2000 N displayed**. The selected load cell (Phidgets FRC4165_0) is rated 200 kg, i.e. **1961 N**; 2000 N is 102 % of
that rating. See [mechanical load path](../architecture/mechanical-load-path.md) for what may be claimed.

| ID | Quantity | Acceptance limit (target) | Why this number | Needs |
|---|---|---|---|---|
| M-01 | Noise at rest, 80 SPS, unfiltered | ≤ 0.15 N RMS | Estimate is 0.05 N RMS (below); 3× margin for board and cable pickup | device only |
| M-02 | Noise at rest, 320 SPS | ≤ 0.4 N RMS | No datasheet figure at 320 SPS; to be characterised, limit may move | device only |
| M-03 | Sample rate | 80 SPS ± 3 % real, and reported period within 0.5 % of true | ADC runs on an untrimmed RC oscillator | PC clock, 10 min run |
| M-04 | Accuracy inside the home-calibrated span | ± (0.5 % of reading + 1 N) | Dominated by how well the reference masses are known | weighed masses |
| M-05 | Accuracy over the full range | ± 0.5 % of 2000 N (± 10 N) | Achievable only with a calibrated reference; Tindeq claims 0.25 % FS | **external lab or calibrated reference cell** |
| M-06 | Repeatability (same load, 5 applications) | ≤ 0.1 % FS (2 N) | Cell datasheet: 0.03 % FS; margin for the hardware stack | masses |
| M-07 | Hysteresis (up vs. down at matched loads) | ≤ 0.1 % FS (2 N) | Cell datasheet: 0.03 % FS | masses |
| M-08 | Zero drift, 30 min after 5 min warm-up, constant temperature | ≤ 1 N | Cell: 0.023 % FS / 10 °C = 0.46 N / 10 °C | device only |
| M-09 | Creep at constant load, 30 min | ≤ 1 N at ≥ 300 N | Cell: 0.024 % FS / 30 min = 0.5 N at capacity | masses |
| M-10 | Step response / bandwidth | Report the 10–90 % rise time for a load release; no limit yet | NAU7802 −3 dB bandwidth is not stated for 80 SPS in the datasheet text we could read | drop-release rig |
| M-11 | Wireless latency (sample to application) | ≤ 100 ms at batch 4 | 50 ms batching + connection interval | LED/photodiode or audio sync |
| M-12 | Notification loss at 2 m, line of sight | ≤ 1 %, and 100 % of losses detected by the client | Loss is acceptable if visible | 10 min run |

### Why a 24-bit ADC does not mean 24-bit measurement

Estimate, datasheet values only:

- Cell output: 2.0 mV/V × 3.0 V excitation = **6.0 mV at capacity**.
- NAU7802 input-referred noise at 80 SPS, gain 128: **150 nV RMS** (datasheet headline).
- 150 nV / 6.0 mV = 25 ppm of capacity = **0.05 N RMS**, about 0.3 N peak-to-peak.
- Noise-free resolution ≈ 6.0 mV / (6.6 × 150 nV) ≈ 6 000 steps ≈ **12.6 bits**, not 24.

And resolution is not accuracy: the cell's own combined error (0.03 % FS = 0.6 N, specified at 9–12 V
excitation, not our 3 V), temperature, creep, off-axis loading and above all the calibration reference
decide accuracy.

### Uncertainty budget (estimate, standard uncertainties, home calibration to ~400 N)

| Source | Size | At 400 N | Note |
|---|---|---|---|
| Reference masses | 0.2–0.5 % if weighed on a kitchen scale; ~2 % for unverified gym plates | 0.8–2 N (8 N for plates) | **Dominant.** |
| Local gravity (formula vs. standard g) | formula: ~0.005 %; using 9.80665 blindly: up to 0.26 % | 0.02 N | Tool forces a local value |
| Air buoyancy | steel 0.015 %, water 0.12 % | 0.06–0.5 N | Corrected when density is given |
| Cell non-linearity + hysteresis | 0.03 % FS each | 0.6 N each | Datasheet, unverified for our unit and excitation |
| Cell temperature effect on span | 0.023 % FS / 10 °C | 0.5 N / 10 °C | |
| ADC noise (single sample) | 0.05 N RMS | 0.05 N | Averages down |
| ADC gain drift, reference ratio | not quantified | ? | Ratiometric design cancels excitation changes to first order |
| Off-axis load, bending | not quantified | ? | Controlled by the pin-jointed load path; to be tested (V-15) |
| **Extrapolation above the calibrated span** | unbounded by this budget | — | Only a full-range reference closes it |

Root-sum-square with weighed masses: roughly **1.5–2.5 N at 400 N (≈ 0.4–0.6 %)**, hence limit M-04.

## Safety and mechanical

| ID | Requirement |
|---|---|
| S-01 | The load path is metal only: connector → load cell → connector. Enclosure, PCB and battery carry no load. |
| S-02 | Every load-path part has a documented rating; the device rating is the lowest of them with a stated margin. |
| S-03 | FENRIR is a measuring instrument. It must never be the only thing between a person and a fall; no dynamic loading. This is stated on the device and in the documentation. |
| S-04 | First loading tests use dead weights in a guarded arrangement, no person in the load path. |
| S-05 | No claim of safe use at any force without a physical proof-load record. |
| S-06 | Battery: protected Li-polymer cell, charging only by a dedicated charger IC, connector polarity checked before first connection. |

## Constraints

| ID | Constraint |
|---|---|
| C-01 | Parts obtainable in Europe by an individual. |
| C-02 | No soldering, 3D printer or lab required for the Phase 2 prototype. |
| C-03 | Parts cost target ≤ €100 per device; report the real figure at 1, 5 and 10 units. |
| C-04 | Open source hardware, firmware, software and documentation. |
| C-05 | No automatic purchases or manufacturing orders; no change to LeBlond production or protected branches without approval. |
