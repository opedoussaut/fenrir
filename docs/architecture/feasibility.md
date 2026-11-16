# FENRIR feasibility assessment (Phase 1)

2026-11-16. Prices and stock were read from supplier pages or search-result snippets on this date;
each is marked with how it was obtained. Nothing was purchased.

## 1. Verdict

A credible 80 SPS Bluetooth dynamometer can be built from purchasable parts with **no soldering**.
Three things are not settled and decide whether the result is good:

1. **The load cell drives both cost and credibility.** A 200 kg S-type cell with a datasheet from a
   named distributor costs €55–91, which pushes the prototype over €100. Marketplace cells at €20–35
   meet the budget but come without traceable specifications.
2. **Accuracy above ~400 N cannot be shown at home.** It needs a calibrated reference (a lab, or a
   borrowed calibrated dynamometer). Until then FENRIR is "calibrated to X N, extrapolated above".
3. **The NAU7802's internal regulator is close to its limit** driving the bridge (7.9 mA into the selected cell's 380 Ω, of a
   guaranteed 10 mA). Fine for a prototype if it holds; the custom PCB should not depend on it.

## 2. References examined

**Tindeq Progressor 200** (product page, read 2026-11-16): design load 2000 N; safe overload 120 % FS,
limit overload 150 % FS; 80 Hz; precision 0.25 % FS; non-linearity, repeatability and hysteresis each
0.1 % FS; USB-C rechargeable; 150 g; US$160 excl. VAT. Its API page describes a custom service with a
control point and a data point using TLV framing, Bluetooth 5, power-off after 10 min idle. The opcode
tables are images and were not read. FENRIR reuses none of it.

**Anthropic electronics-design write-up** (read 2026-11-16). What we take from it:
- decisions come from datasheets, not memory (done here for the NAU7802 and TAS501 — both PDFs were
  downloaded and read);
- automated checks produce false positives that need judgement, and real findings that need fixing;
- in that work, electrical validation, antenna tuning, thermal testing and certification were **not**
  done by the model — humans assembled and ran the boards. Same boundary here: this repository can be
  software-verified by Claude; everything physical needs the owner or a supplier.

**LeBlond** (local clone, read-only): Next.js 16 / React 19 PWA, Supabase Postgres with row-level
security, zod, Vitest and Playwright, fr/en strings in `lib/i18n`, pure-function analytics in
`lib/analytics`, provider adapters in `lib/integrations/wearables` with a rule never to show a fake
"Connected". `training_exercise_sets` already has `edge_mm`, `side`, `load_kg`, `seconds`, `details`.
The assessment protocol labels every value with an evidence level (measured / observed / self /
estimated). Details in [the integration spec](../../software/leblond-integration/README.md).

## 3. Component comparison

### ADC

| | Nuvoton NAU7802 | Avia HX711 |
|---|---|---|
| Datasheet read | Yes — rev 1.7, register map and electrical table | No — from general knowledge, **not re-verified today** |
| Rates | 10 / 20 / 40 / 80 / 320 SPS (CRS bits, reg 0x02) | 10 or 80 SPS, pin-selected |
| Interface | I²C, address 0x2A, status and error bits | Bit-banged clock/data, no registers |
| Noise | 50 nV RMS @ 10 SPS, 150 nV RMS @ 80 SPS, gain 128 | — |
| Excitation | Internal LDO 2.4–4.5 V in 8 steps, ≥ 10 mA at 3.0 V | Internal regulator with external transistor |
| Extras | Internal offset calibration, temperature sensor, < 1 µA standby | — |
| Solder-free breakout | Adafruit 4538, screw terminals pre-soldered, STEMMA QT | Common breakouts need header soldering |

**Choice: NAU7802.** 320 SPS headroom for RFD, a real bus with fault reporting, and a breakout that
needs no soldering. Limits: 320 SPS noise is not specified; −3 dB bandwidth at 80 SPS could not be
read reliably from the PDF text (table garbled by extraction) — open item.

### Microcontroller

| | ESP32-C3 / C6 | nRF52840 |
|---|---|---|
| First flash | Over USB-C with built-in USB serial/JTAG — **no programmer** | Needs SWD programmer unless the module ships with a USB bootloader |
| Streaming current | Tens of mA (estimate) | A few mA (estimate) |
| Module cost | Low | Higher |
| Solder-free dev board with battery charger and Qwiic | Adafruit ESP32-C6 Feather 5933 (USB-C, charger, MAX17048 gauge, STEMMA QT) | Not found: XIAO nRF52840 needs wires soldered for I²C and battery |
| BLE stack | NimBLE | SoftDevice / Zephyr |

**Choice: ESP32 family.** The owner has no programmer and no soldering iron; flashing over the same
USB-C cable that charges the device outweighs battery life for a tool used an hour at a time. The
nRF52840 remains the better radio for a later battery-optimised revision (decision D-002).
Prototype on the **ESP32-C6 Feather**; custom PCB candidate **ESP32-C3-MINI-1** or C6-MINI-1, decided
after Phase 2 current measurements.

### Load cell

| Candidate | Evidence | Price found | Notes |
|---|---|---|---|
| HT Sensor **TAS501-200kg** (SparkFun SEN-14282) | Datasheet downloaded and read | US$96.95 (SparkFun page); €90.87 excl. VAT (DigiKey FR, search snippet) | 2.0 ± 0.005 mV/V; safe overload 150 % FS; ultimate 200 % FS; combined error 0.03 % FS; 350 Ω; IP66; 51 × 19 × 76 mm; 3 m cable. Datasheet thread table is ambiguous; a SparkFun reviewer reports **M12**. |
| Phidgets **FRC4165_0** Steel S-Type 200 kg (C3) — **selected** | Manufacturer page and datasheet read | US$50.00 (Phidgets page, 124 in stock; 5+ $48, 10+ $46); £52.31 (RobotShop UK) | 2 mV/V ± 4 µV/V; in 380 Ω / out 350 Ω; max overload 300 kg; M12 × 1.75; IP68; 50.8 × 19 × 76.2 mm; 3 m cable. Ships from Canada or UK → import VAT. |
| Unbranded S-type 200 kg (marketplaces) | None | €54 (Fruugo snippet); €20–35 typical — **not verified** | No traceable specification. |
| Zemic H3-C3-200kg-3B | Not confirmed | US$235 (US dealer, possibly outdated) | OIML C3, IP67. Over budget. |
| Tedea-Huntleigh 615, 200 kg | RS listing snippet | €189 | ½" UNF threads. Over budget. |

**Selected by the owner on 2026-11-16: Phidgets FRC4165_0** (decision D-016). After the choice its
manufacturer page and datasheet were read: the cell is a Ningbo ANE ST01, 2.0 mV/V ± 4 µV/V, input
380 Ω, output 350 Ω, M12 × 1.75, IP68, 50.8 × 19 × 76.2 mm, maximum overload 300 kg (datasheet: safe
150 % FS, ultimate 200 % FS), non-linearity, hysteresis and repeatability each ≤ 100 g on the Phidgets
page (0.05 % FS ≈ 1 N), creep 200 g/h, US$50 direct with 124 in stock. The TAS501 stays as fallback.
Datasheet excitation is 10–12 V (15 V max); we use 3.0 V, which is safe
for the cell but gives a third of the signal and is outside the conditions its error figures are
stated for.

An S-type cell is the right geometry: threaded holes at both ends, in-line tension, widely available.
Single-point (platform) cells are designed for off-centre compression and are wrong here.

## 4. Electrical architecture

```
            E+ (3.0 V from NAU7802 LDO) ──────────────┐
 Load cell  E−  ──────────────────────────────────────┤  Adafruit NAU7802 breakout
 350 Ω      A+ / A−  (6.0 mV at capacity) ────────────┤  gain 128, 80 or 320 SPS
 bridge     shield → E− at the breakout only          │  REFP/REFN = AVDD/GND (ratiometric)
                                                      │
                               I²C 400 kHz (STEMMA QT cable, 3.3 V)
                                                      │
 LiPo 3.7 V ── JST ──► ESP32-C6 Feather: charger, MAX17048 gauge, USB-C, BLE 5 ──► phone / PC
```

Signal budget (estimates from datasheets):

| Quantity | Value | Basis |
|---|---|---|
| Bridge output at capacity | 6.0 mV | 2.0 mV/V × 3.0 V |
| ADC full-scale input at gain 128 | ± 11.7 mV | ± 0.5 × VREF / gain |
| Headroom | capacity uses 51 % of the positive range; clipping near 195 % of capacity | above the cell's 150 % safe overload, so the cell limit comes first |
| Sensitivity | ≈ 1074 counts/N (per 2000 N nominal) | 2e-3 × 128 × 2²³ / 2000 |
| Noise | 0.05 N RMS at 80 SPS | 150 nV / 6.0 mV × capacity |
| Bridge current | 7.9 mA | 3.0 V / 380 Ω input resistance (FRC4165_0) — **79 % of the LDO's guaranteed 10 mA** |

Ratiometric measurement (reference = excitation) cancels excitation drift to first order, which is
why the weak internal LDO is tolerable for a prototype.

Power (estimate, to be measured in V-13): ADC 2.1 mA + bridge 7.9 mA + MCU with BLE streaming, in total
roughly 30–60 mA → **about 6–13 h on a 400 mAh cell**. Adafruit states 17 µA deep sleep for the
Feather. Not measured.

## 5. Option A vs Option B

| | A — modular prototype | B — custom PCB |
|---|---|---|
| Electronics | Feather + NAU7802 breakout + cable | One board: ESP32-C3/C6 module, NAU7802, charger, gauge, USB-C, ESD, LED, button |
| Parts cost (1 unit) | €105–145 with a documented cell, ~€75–85 with a marketplace cell (see BOM) | **Not quoted.** No schematic yet, so no honest number |
| Size | Two boards ≈ 51 × 23 mm and 25 × 18 mm plus battery | Target one board ≈ 45 × 25 mm |
| Sample rate | 80 / 320 SPS, ready bit polled over I²C (≤ 0.5 ms timestamp jitter) | Same ADC, DRDY on an interrupt pin |
| Manual assembly | 4 screw terminals, 2 plugs. No soldering | Assembled by the PCB supplier; battery plug only |
| Firmware | Same portable core; `feather_esp32c6` environment | Same core; pin map and LED/button added |
| Analog quality | Breakout layout, I²C cable next to the bridge wires | Own ground partition, filtering, short bridge traces, external low-noise excitation |
| Availability risk | Adafruit direct was out of stock for the Feather on 2026-11-16; DigiKey EU listed it | Depends on assembler's parts library — to check in Phase 3 |
| Maintainability | Anyone can replace a module | Needs the manufacturing files; repair by replacement |

Recommendation: **build A first** to learn noise, drift, current and mechanics on real parts, then
design B with those measurements. Designing the PCB before A has run would mean guessing at exactly the
numbers the PCB exists to improve.

## 6. Risks and open assumptions

| ID | Risk / assumption | Consequence | Next step |
|---|---|---|---|
| R-01 | Calibration reference limited to ~400 N at home | Upper 80 % of range unverified | Find a lab or calibrated reference (V-05) |
| R-02 | NAU7802 LDO near its current limit with a 350 Ω bridge | Excitation sag, extra noise or drift | Measure E+ under load; fall back to 2.7 V; external regulator on the PCB |
| R-03 | Cell error figures quoted at 9–12 V, we use 3 V | Real non-linearity/hysteresis may differ | Characterise (V-06, V-07) |
| R-04 | Load cell thread is M12 × 1.75 per its datasheet; usable thread depth is not published | Eye bolts may bottom out or engage too little | Measure the hole depth on receipt before loading |
| R-05 | Device rating equals the cell's rating (200 kg ≈ 1961 N); two-handed pulls can exceed that | Overload of the cell | Overload flag at 2200 N; owner confirmed 200 kg (D-006), so loads above the cell's rating are out of scope and must be stated as such in the user documentation |
| R-06 | Firmware platform layer never run on hardware | Unknown bugs in BLE/I²C glue | Phase 2 bring-up |
| R-07 | ESP32 current draw only estimated | Battery life claim unsupported | USB power meter measurement (V-13) |
| R-08 | BLE link unencrypted; anyone nearby can write calibration | Tampering | Add bonding or a physical-presence check before distribution (D-011) |
| R-09 | LiPo connector polarity differs between battery vendors | Reverse polarity can destroy the board or start a fire | Buy the battery from the board's vendor; check polarity before plugging |
| R-10 | Web Bluetooth absent on iOS | iPhone users cannot connect from the web app | Native bridge or WebBLE browser (integration spec) |
| R-11 | No radio/EMC conformity work planned yet | Cannot be CE-marked or sold | Use a pre-certified module; assess before any distribution |
| R-12 | Prices and stock move | BOM total drifts | Re-check at order time |
