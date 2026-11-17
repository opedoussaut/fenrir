# Verification matrix

Last updated 2026-11-16. Evidence levels, in increasing strength:

- **NOT STARTED** — nothing exists.
- **SOFTWARE-TESTED** — automated test on a PC, passing on the date shown.
- **SIMULATED** — exercised against the software simulator; says nothing about hardware.
- **ELECTRICALLY MEASURED** — read from an instrument on the real device.
- **PHYSICALLY VALIDATED** — measured against an independent reference, with a record.

No row is above SOFTWARE-TESTED / SIMULATED, because **no hardware exists**. No physical test has been
performed and none is marked as passed.

## Software evidence (run on 2026-11-16)

| Suite | Command | Result |
|---|---|---|
| Firmware core, host build with `-Wall -Wextra -Wpedantic -Wconversion -Werror`, ASan + UBSan (gcc 13 in Docker) | `make -C firmware/tests test` | 113 checks, 0 failures (2026-11-17, includes the ADS1220 driver against a mock SPI device) |
| Protocol vectors: firmware encoder output vs. `protocol/vectors/v1.txt` | `make -C firmware/tests vectors-check` | identical |
| Python: protocol, data model, simulator, metrics, calibration | `pytest` | 64 passed (2026-11-17) |
| TypeScript client | `npm test` in `software/leblond-integration` | 6 passed |
| Firmware cross-compile, FENRIR PCB (ESP32-C6-MINI-1, ADS1220 over SPI) | `pio run -d firmware -e fenrir_pcb` | links (2026-11-17): 742 kB flash, 26 kB RAM; no warnings in project code (one `-Woverloaded-virtual` warning from the NimBLE-Arduino library header `NimBLEStream.h`) |

Defects found and fixed by these runs: CRC routine failing strict conversion warnings; RFD onset
detection never firing when the sample period does not divide the hold window (i.e. on any real ADC
clock); calibration CLI crashing on Windows consoles when printing "σ"; deprecated NimBLE service-start calls in the platform layer.

## Matrix

| ID | Requirement | Objective | Equipment | Procedure | Acceptance | Evidence to collect | Status |
|---|---|---|---|---|---|---|---|
| V-01 | Electrical correctness | Wiring and supplies as designed | Multimeter | Measure 3.3 V, AVDD and E+ (expect 3.0 V) unloaded and with the bridge connected; ADS1220 register read-back passes at boot; MAX17048 answers at 0x36 | E+ within 3.0 V ± 3 %, no sag > 1 % with bridge; no ADC_FAULT; gauge ACKs | Readings, serial log | NOT STARTED |
| V-02 | F-04, M-03 Sampling rate | Real sample rate and timestamp truth | PC | 10 min stream; compare sample count and device time span with PC clock | 90 SPS ± 3 %; device period within 0.5 % of PC-measured | Diagnostic output, CSV | SIMULATED (model with a 1.2 % fast ADC is reported as 91.08 Hz, not 90) |
| V-03 | M-01, M-02 Noise | RMS noise at rest | Device | 60 s at rest, unloaded and at a static load, 90 and 350 SPS | ≤ 0.15 N RMS (90), ≤ 0.3 N RMS (350) | CSV, spectrum | NOT STARTED (estimate 0.05 / 0.09 N RMS from the ADS1220 datasheet) |
| V-04 | M-04 Accuracy in calibrated span | Error at check loads not used in the fit | Weighed masses | Calibrate; then apply 3 independent loads | ± (0.5 % of reading + 1 N) | Calibration report, check table | SIMULATED (tool recovers the simulator's scale to 0.2 %) |
| V-05 | M-05 Full-range accuracy | Error up to 2000 N | **Calibrated reference / external lab** | 5 points up and down to 2000 N | ± 10 N | Lab certificate or comparison record | NOT STARTED — cannot be done at home |
| V-06 | M-06 Repeatability | Spread at one load | Masses | Same load 5 times, full unload between | ≤ 2 N | Table | NOT STARTED |
| V-07 | M-07 Hysteresis | Up vs. down | Masses | Staircase up and down | ≤ 2 N | Calibration report | SIMULATED (tool reports the model's hysteresis) |
| V-08 | M-08 Zero drift | Drift at rest and with temperature | Thermometer | 30 min at rest after warm-up; repeat in a second room | ≤ 1 N / 30 min; report N/°C | CSV, temperatures | NOT STARTED |
| V-09 | M-10 Rapid force change | Step response | Dead weight with quick release | Cut or release a hanging load; 350 SPS | Report 10–90 % time; no ringing artefacts from filtering | CSV | NOT STARTED |
| V-10 | F-05 BLE throughput | Sustained rate at each mode | Phone and PC | 5 min at 90 SPS/batch 4 and 350 SPS/batch 16; note negotiated MTU | No sample loss; throughput ≥ computed 0.81 / 2.4 kB/s | Link statistics | NOT STARTED (computed only) |
| V-11 | M-11, M-12 Loss and timing | Loss rate, loss detection, latency | PC; LED + phone camera for latency | 10 min at 2 m and at 8 m; deliberate interference | ≤ 1 % loss at 2 m; every loss counted; latency ≤ 100 ms | Link statistics, video | SIMULATED (injected 10 % loss is fully counted; time axis keeps gaps) |
| V-12 | F-10 Reconnection | Recovery after link loss | Phone | Walk out of range and back; kill the app | Device re-advertises; no streaming until START; client resumes | Log | SOFTWARE-TESTED (client side with a fake transport); device side NOT STARTED |
| V-13 | F-11, S-06 Battery and charging | Run time, charge behaviour, gauge truth | USB power meter, multimeter, thermometer | Full charge, stream to cut-off; charge from empty; cell temperature while charging | Run time ≥ 6 h; charge current per board spec; cell < 45 °C; gauge within 10 % | Current log, temperatures | NOT STARTED (estimate 6–13 h) |
| V-14 | Thermal | Self-heating and its effect on zero | Thermometer | 1 h streaming in the enclosure | Enclosure rise < 15 °C; zero drift within V-08 limit | Temperatures, CSV | NOT STARTED |
| V-15 | S-01…S-05 Mechanical integrity | Load path holds; zero returns; nothing moves | Dead weights, rated anchor, padded floor; full range needs a lab | Procedure in mechanical-load-path.md | No thread movement, zero return within 1 N, no damage; stated proof load = largest load applied | Photos, readings | NOT STARTED |
| V-16 | F-09 Firmware error handling | Faults are detected and reported, never turned into numbers | Device | Disconnect a bridge wire; short A+ to E+; unplug the ADC cable while streaming; corrupt stored config | Matching status flag within 1 s; invalid samples carry the invalid code; recovery after reconnection | Diagnostic log | SOFTWARE-TESTED for the core logic (saturation, stuck, slew, overload, CRC, ADC init failures against a register-level mock); on hardware NOT STARTED |
| V-17 | F-07, F-08 Calibration storage and raw data | Coefficients survive power cycles; raw is untouched by tare/filter | Device | CAL_WRITE, power cycle, read back; stream with filter on and compare raw | Bit-exact read-back; raw identical with filter on/off | Log | SOFTWARE-TESTED (serialise/deserialise, every single-bit corruption rejected); on hardware NOT STARTED |
| V-18 | F-05 Protocol consistency | Firmware, Python and TypeScript agree byte for byte | PC | Shared vectors | Identical | Test output | SOFTWARE-TESTED |
| V-19 | F-13 Metrics | Peak, mean, TUT, RFD, fatigue index correct on known signals | PC | Analytic ramps and simulated pulls | Within stated tolerances | Test output | SOFTWARE-TESTED |
| V-20 | F-14, F-15 Data consistency with LeBlond | The same recording gives the same numbers in LeBlond and in the Python reference | PC | Replay a recorded session through both | Peak and RFD equal within 0.1 % | Comparison | NOT STARTED (LeBlond not modified; TypeScript metrics not ported yet) |
| V-21 | Extended operation | No drift of rate, memory or link over hours | Device | 4 h continuous stream | No loss growth, no reset, uptime continuous | Log | NOT STARTED |
| V-22 | Firmware builds for the target | Platform layer compiles and links | PC | `pio run -d firmware -e fenrir_pcb` | Build succeeds without warnings in project code | Build log | SOFTWARE-TESTED on 2026-11-17 for the ADS1220/SPI platform layer (builds only; never executed on a board; pin map provisional) |
| V-23 | S-01 Enclosure fit | Shell fits the real cell, eye bolts and boards with the designed clearances | Parts + printed shell | Assemble; feeler gauge at the lower block and lower eye bolt | Gap >= 1 mm everywhere except the upper grip pads | Photos, measurements | NOT STARTED (concept model only; parts not received) |
| V-24 | S-01 Shell carries no load | The shell does not change the reading | Device | Same dead weights with and without the shell | Difference within repeatability | Calibration reports | NOT STARTED |
| V-25 | PCB electrical rules | Schematic and layout pass ERC and DRC | PC | KiCad ERC/DRC, assembler DFM | No unexplained violation | Reports | NOT STARTED (no schematic exists) |
| V-26 | F-05 Radio range in the enclosure | BLE link holds with the module 4-5 mm in front of the steel cell, inside the shell | Device | Stream at 1, 3 and 5 m through the chosen enclosure | No packet loss at 3 m | Diagnostics log | NOT STARTED (risk identified in the rev B concept study) |
| V-27 | S-01 Enclosure CAD clearances | Concept shells do not touch the cell's lower block, lower nut or lower attachment, and do not intersect internal parts | PC | `check()` in `mechanical/cad/concepts.py` on nominal dimensions | Interference 0; gap >= 1.5 mm at the floating end | Script output | SOFTWARE-TESTED on 2026-11-17 for concepts A, B, C and for concept A detail rev C (`fenrir_a.py`, which also checks >= 1.0 mm wall around the screw counterbores). Nominal CAD only; says nothing about real parts or tolerances |
