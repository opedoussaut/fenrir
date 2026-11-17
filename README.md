# FENRIR

Open-source Bluetooth force sensor for climbers: finger-strength tests, no-hang pick-ups, pulling
strength, peak force and rate of force development. Part of the LeBlond ecosystem, usable on its own.

> **FENRIR measures force. It is not climbing safety equipment.** Never use it where its failure
> could cause a fall, and never shock-load it. See [mechanical load path](docs/architecture/mechanical-load-path.md).

## Current state (2026-11-17)

**No hardware exists yet. Nothing has been bought, built, measured or physically tested.**

FENRIR is **one product** (decision D-023): a custom PCB in a 3D-printed enclosure (concept A, "Precision")
around a 200 kg S-type load cell. The earlier plan of an Adafruit-module prototype is dropped.

| Area | State |
|---|---|
| Requirements, feasibility, sourced BOM, decision log, verification matrix | Written |
| GATT protocol 1.1 | Specified; three codecs pinned to shared byte vectors |
| Firmware core (protocol, calibration, filters, fault detection, ADS1220 and NAU7802 drivers) | Host-tested: 113 checks, strict warnings, ASan/UBSan |
| Firmware ESP32 platform layer (BLE, SPI ADC, I²C gauge, flash) | Compiles and links for the FENRIR PCB target (ESP32-C6-MINI-1); **never run on hardware**; pin map provisional |
| Python tools (simulator, data model, metrics, calibration, diagnostics) | 64 tests passing; exercised on simulated data only |
| TypeScript client for LeBlond | 6 tests passing; Web Bluetooth path never run against a device |
| Enclosure | **Concept A, detail design rev C** ([mechanical/enclosure-a.md](mechanical/enclosure-a.md)); CAD clearance checks pass on nominal geometry; not released for printing |
| Custom PCB | **Definition only** ([hardware/pcb-design.md](hardware/pcb-design.md)); ADS1220 as ADC (D-024); no schematic, layout or Gerbers |
| LeBlond application changes | **None** — specification only |

Target build on 2026-11-17 (pioarduino platform 55.03.312 pinned, Arduino-ESP32 3.3.12, NimBLE-Arduino 2.x):
`fenrir_pcb` 742 kB flash / 26 kB RAM. A successful
build shows the code compiles; it says nothing about whether it works on a board.

## Repository map

| Path | Content |
|---|---|
| [docs/requirements](docs/requirements/requirements.md) | Requirements, acceptance limits, uncertainty budget |
| [docs/architecture/feasibility.md](docs/architecture/feasibility.md) | Reference products, component comparison, Option A vs B, risks |
| [docs/architecture/mechanical-load-path.md](docs/architecture/mechanical-load-path.md) | Load path, ratings, failure modes, safety limits |
| [docs/decisions](docs/decisions/decision-log.md) | Decision log |
| [docs/verification](docs/verification/verification-matrix.md) | Verification matrix, calibration procedure |
| [docs/manufacturing](docs/manufacturing/prototype-assembly.md) | Modular prototype wiring (superseded by D-023; kept for the flashing and first power-up steps) |
| [hardware/bom](hardware/bom/README.md) | Single-product parts list with price sources |
| [protocol](protocol/fenrir-gatt-v1.md) | BLE protocol and reference vectors |
| `firmware/` | PlatformIO project: `src/core` (portable C), `src/platform/esp32`, `tests` (host) |
| `software/fenrir/` | Python package: protocol, model, metrics, `simulator`, `calibration`, `diagnostics` |
| [software/leblond-integration](software/leblond-integration/README.md) | Integration spec and TypeScript client |
| `tests/` | Python tests |

## Try it without hardware

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -e ".[dev,plots]"
```

```bash
.venv/Scripts/python -m pytest
```

```bash
.venv/Scripts/python -m fenrir.diagnostics --sim --seconds 8 --loss 0.02
```

```bash
.venv/Scripts/python -m fenrir.calibration demo --lat 43.6 --alt 150 --out calibration-demo
```

(On Linux/macOS use `.venv/bin/python`.) Simulator output is labelled as simulated; it is not a measurement.

Firmware host tests need gcc and make. With Docker:

```bash
docker run --rm -v "$PWD:/w" -w /w/firmware/tests gcc:13 make test
```

## Licences

Confirmed by the owner on 2026-11-16 (decision D-014).

| Content | Licence | Text |
|---|---|---|
| Firmware, software, tests, build files (`firmware/`, `software/`, `tests/`) | MIT | [LICENSE](LICENSE) |
| Hardware and mechanical design (`hardware/`, `mechanical/`) | CERN-OHL-P v2 | [LICENSES/CERN-OHL-P-2.0.txt](LICENSES/CERN-OHL-P-2.0.txt) |
| Documentation and protocol specification (`docs/`, `protocol/`, README files) | CC BY 4.0 | [LICENSES/CC-BY-4.0.txt](LICENSES/CC-BY-4.0.txt) |

All three exclude any warranty. None of them makes FENRIR safety equipment: see the notice at the
top of this file.
