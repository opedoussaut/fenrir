# Prototype A — wiring, flashing and first power-up

Status: **written from datasheets and product pages; never performed.** Correct this document during
the first build.

## Wiring (no soldering)

| From | To | Note |
|---|---|---|
| Load cell **red** (excitation +) | NAU7802 breakout terminal **E+** | Colours per the Phidgets FRC4165_0 page; check the label on the cell you actually receive |
| Load cell **black** (excitation −) | **E−** | |
| Load cell **green** (signal +) | **A+** | Swapping green/white only flips the sign |
| Load cell **white** (signal −) | **A−** | |
| Load cell **yellow** (shield / ground, per the Phidgets page) | **E−** terminal, together with black | This end only |
| NAU7802 STEMMA QT | Feather STEMMA QT | 100 mm cable; carries 3.3 V, GND, SDA, SCL |
| LiPo JST plug | Feather battery socket | **Check polarity first** (below) |

Coil the spare 3 m of load-cell cable neatly; do not cut it for the prototype (shortening changes
nothing useful and cannot be undone).

**Battery polarity.** JST-PH batteries are not standardised: red may be on either side. Before
plugging in, compare the plug with the `+` marking next to the Feather's socket. If they disagree, do
not connect. A reversed battery can destroy the board and overheat.

## Flash the firmware

Requires [PlatformIO Core](https://docs.platformio.org/) (`pip install platformio`) and the USB-C cable.
The toolchain download is about 7 GB.

```bash
cd firmware
```

```bash
pio run -e feather_esp32c6 -t upload
```

```bash
pio device monitor
```

Expected on the serial monitor: `FENRIR fw 0.1.0 hw proto-A, cal NOMINAL (uncalibrated)`.
`NAU7802 init failed: 1` means the breakout is not answering on I²C (cable); `2` power-up failed;
`3` its internal calibration failed (check the four bridge wires).

If upload fails, hold the Feather's **Boot** button, tap **Reset**, release Boot, and retry.

## First checks (no load cell hardware needed beyond the bench)

```bash
python -m fenrir.diagnostics --ble --seconds 10
```

1. Device is found and reports protocol 1.0.
2. Sample rate close to 80 Hz, zero lost packets at 1 m.
3. With nothing attached, noise is of the order of 0.05–0.15 N RMS (target M-01).
4. Pull the cell gently by hand through the eye bolts: force goes **positive** in tension. If negative,
   swap the green and white wires.
5. Unplug one bridge wire: within a second the tool reports `ADC_STUCK` or saturation — the fault
   detection works on real hardware. Reconnect.

Record the outputs under `docs/verification/evidence/` (create the folder with the first record).

## Then

Mechanical assembly and first loading: [mechanical load path](../architecture/mechanical-load-path.md).
Calibration: [calibration procedure](../verification/calibration-procedure.md).
