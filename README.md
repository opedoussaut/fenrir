# FENRIR

Open-source Bluetooth force sensor for climbers: finger-strength tests, no-hang pick-ups, pulling
strength, peak force and rate of force development. Part of the LeBlond ecosystem, usable on its own.

> **FENRIR measures force. It is not climbing safety equipment.** Never use it where its failure
> could cause a fall, and never shock-load it. See [mechanical load path](docs/architecture/mechanical-load-path.md).

## Current state (2026-11-16)

**No hardware exists yet. Nothing has been bought, built, measured or physically tested.**

| Area | State |
|---|---|
| Requirements, feasibility, sourced BOM, decision log, verification matrix | Written |
| GATT protocol v1 | Specified; three codecs pinned to shared byte vectors |
| Firmware core (protocol, calibration, filters, fault detection, NAU7802 driver) | Host-tested: 87 checks, strict warnings, ASan/UBSan |
| Firmware ESP32 platform layer (BLE, I²C, flash) | Compiles and links for ESP32-C6 and ESP32-C3 with no warnings; **never run on hardware** |
| Python tools (simulator, data model, metrics, calibration, diagnostics) | 62 tests passing; exercised on simulated data only |
| TypeScript client for LeBlond | 6 tests passing; Web Bluetooth path never run against a device |
| KiCad schematic and PCB, Gerbers, enclosure CAD, STEP | **Not started** (Phase 3, after the prototype is measured) |
| LeBlond application changes | **None** — specification only |

Target builds on 2026-11-16 (pioarduino platform, Arduino-ESP32 3.3.12, NimBLE-Arduino 2.x):
`feather_esp32c6` 737 kB flash / 26 kB RAM, `pcb_esp32c3` 624 kB flash / 25 kB RAM. A successful
build shows the code compiles; it says nothing about whether it works on a board.

## Repository map

| Path | Content |
|---|---|
| [docs/requirements](docs/requirements/requirements.md) | Requirements, acceptance limits, uncertainty budget |
| [docs/architecture/feasibility.md](docs/architecture/feasibility.md) | Reference products, component comparison, Option A vs B, risks |
| [docs/architecture/mechanical-load-path.md](docs/architecture/mechanical-load-path.md) | Load path, ratings, failure modes, safety limits |
| [docs/decisions](docs/decisions/decision-log.md) | Decision log |
| [docs/verification](docs/verification/verification-matrix.md) | Verification matrix, calibration procedure |
| [docs/manufacturing](docs/manufacturing/prototype-assembly.md) | Prototype wiring, flashing, first power-up |
| [hardware/bom](hardware/bom/README.md) | Purchasing list with price sources |
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

## Licences (proposed, see decision D-014)

Hardware: CERN-OHL-P v2 · Firmware and software: MIT · Documentation: CC BY 4.0.
Licence files will be added once the owner confirms the choice.
