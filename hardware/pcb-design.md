# Custom PCB — design definition

Status: **definition only. No schematic, no layout, no ERC/DRC, no fabrication files exist.**
The owner asked on 2026-11-16 for the PCB to be designed now (decision D-019), and on 2026-11-17
decided that FENRIR is **one product only**: this board in the concept A enclosure, with no modular
Adafruit prototype (D-023). Ordering a board still needs the owner's approval.

Because there is no prototype, this board is also the first hardware FENRIR will ever measure
(risk R-13). It therefore carries more test access and options than a production board would.

Part choices are marked **read** where the datasheet was read; the others must be read before the
schematic is drawn.

## Board

| Item | Choice | Reason |
|---|---|---|
| Outline | **46 × 38 mm, 3 mm corner radii** (enclosure concept A rev C bay: 50 × 80 × 8 mm, shared with a 30 × 35 × 5 mm battery below the PCB). Mounting method open | Enclosure decisions D-021 / D-022 |
| Stack | 4 layers, 1.6 mm, inner ground plane | Quiet return path under the bridge inputs |
| Assembly | One side, by the manufacturer. No hand soldering | Owner has no soldering equipment |
| Component height | ≤ 5 mm on the top side | Bay depth 8 mm |

## Blocks and parts

| Block | Part | Notes |
|---|---|---|
| MCU + radio | Espressif ESP32-C6-MINI-1 (4 MB), pre-certified module, PCB antenna | Existing firmware targets the C6; flashing over USB, no programmer (D-025). Antenna at the board edge, keep-out respected. Fallback ESP32-C6-MINI-1U if the range test fails (R-14) |
| Bridge ADC | **TI ADS1220IPW, TSSOP-16, SPI** (read) — D-024, accepted 2026-11-17 | Gain 128, external reference REFP0/REFN0 = bridge excitation (ratiometric). Firmware runs turbo mode. Typical input-referred noise at gain 128, turbo: 0.15 µV at 90 SPS, 0.28 µV at 350 SPS, 0.41 µV at 660 SPS. DRDY to an interrupt pin. Symbol `ADS1220xPW` is in KiCad's `Analog_ADC` library |
| Analog supply | TI LP5907-3.0, fed from the 3.3 V rail | Powers ADS1220 AVDD and bridge excitation (350 Ω bridge ≈ 8.6 mA). Cascading from 3.3 V adds supply rejection and keeps the bridge regulated as the battery falls. Solder jumper to feed AVDD from 3.3 V instead (R-13 option) |
| Digital supply | 3.3 V LDO sized for the radio's transmit peaks; candidate TI TLV757P-3.3 | To size from the module datasheet |
| Charger | Microchip MCP73831, about 200 mA for a 400 mAh cell | — |
| Fuel gauge | Maxim MAX17048 | Firmware already reads it. **Datasheet still not read** |
| USB-C | 16-pin USB 2.0 receptacle, two 5.1 kΩ CC resistors, ESD array on D+/D− | USB is also the programming port |
| Battery input | JST-PH 2-pin, reverse-polarity protection, power-path switch between USB and battery | Battery plug polarity is not standardised (R-09) |
| Bridge connector | 5-way spring terminal: E+, E−, A+, A−, shield | Screwdriver only, no soldering |
| Bridge protection | Differential + common-mode RC filter and low-leakage ESD protection on A+ / A− | Values from the ADS1220 application section, to compute in the schematic step |
| User interface | One RGB LED, one button, BOOT button, reset pads | Requirement F-16 |
| Test points | 3V3, AVDD (3.0 V), E+, E−, GND, SCLK, DIN, DOUT, CS, DRDY, SDA, SCL, VBAT, VBUS | First hardware ever measured: every rail and bus must be reachable with a probe |

## Pin plan (to confirm against the module datasheet)

| Signal | Pin | Note |
|---|---|---|
| USB D− / D+ | GPIO12 / GPIO13 | Native USB serial and flashing |
| SPI SCLK / DIN (MOSI) / DOUT (MISO) / CS | GPIO21 / GPIO22 / GPIO23 / GPIO20 | ADS1220, SPI mode 1 |
| ADC DRDY | GPIO2 | Low-power domain pin, can wake the chip |
| I²C SDA / SCL | GPIO6 / GPIO7 | MAX17048 at 0x36 |
| Button | GPIO3 | Low-power domain pin, wake from sleep |
| Gauge alert | GPIO1 | Optional |
| LED R / G / B | GPIO0 / GPIO18 / GPIO19 | Avoid the strapping pins (4, 5, 8, 9, 15) and UART0 (16, 17) |
| BOOT | GPIO9 | Strapping pin |

## Firmware (done in software, 2026-11-17)

`firmware/src/core/ads1220.c` drives the ADC over an SPI HAL: reset, write and read back all four
configuration registers (SPI has no acknowledge, so the read-back is the presence and wiring check),
start continuous conversion, read 24-bit codes on DRDY low, power down. Host-tested against a mock SPI
device (configuration bytes, sign extension, full-scale codes passed through untouched, absent device,
bus failure, a register that ignores writes). The ESP32 platform layer uses it with the pin plan above.
Rates are 90 and 350 SPS (protocol 1.1, D-026). Higher rates (660–2000 SPS) stay out of protocol 1.x.
**Never run on hardware.**

## Layout rules

- Bridge traces short, routed as pairs, over unbroken ground, away from the antenna, the USB
  connector and the charger.
- Reference lines (REFP0/REFN0) routed as a pair from the bridge terminal, not from the regulator.
- Analog and digital grounds joined at one point near the ADC.
- Nothing but the antenna in the module keep-out; no copper under it on any layer.
- Run ERC and DRC, then the assembler's DFM check; treat every flag as a finding to judge.

## Work sequence

1. Read the datasheets not yet read (module, regulators, charger, gauge, USB connector).
2. Schematic in KiCad; ERC clean.
3. Check each part against the assembler's library and stock.
4. Layout; DRC clean; 3D check against the enclosure bay.
5. Fabrication outputs and a BOM with sourced prices.
6. Owner review, then order approval.
7. Bare-board bring-up on the bench (rails, ADC, radio range) before the enclosure is ordered.

## Tooling

KiCad 10.0.8 was installed on the design machine on 2026-11-17 (`E:\KiCad`); `kicad-cli` and the
`pcbnew` Python API run. The standard libraries contain ESP32-C6-MINI-1, ADS1220 (`ADS1220xPW`),
MCP73831 and LP5907. **MAX17048 is not in the standard symbol libraries**: it needs a project symbol
drawn from the datasheet pinout and checked against it.

A schematic or layout that has never been through ERC/DRC is not something this project will publish.
