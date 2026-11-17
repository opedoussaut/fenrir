# Hardware

| Folder | State |
|---|---|
| [`bom/`](bom/README.md) | Single-product parts list (`product-bom.csv`, D-023); the old prototype list is kept but superseded |
| `components/` | Datasheet index below; no custom KiCad symbols or footprints yet |
| [`pcb-design.md`](pcb-design.md) | Custom PCB definition: blocks, parts, pin plan, layout rules (decisions D-019, D-023 to D-025) |
| `kicad/` | **Empty.** Schematic not started. KiCad 10.0.8 is installed on the design machine |
| `fabrication/` | **Empty.** No Gerbers, drill files, pick-and-place or assembly drawings exist |

## Datasheets used

| Part | Document | How it was used |
|---|---|---|
| TI ADS1220 (PCB ADC, D-024) | Data sheet SBAS501D from ti.com | Downloaded and read: noise tables (normal and turbo mode), supply 2.3–5.5 V, external reference range up to AVDD, PGA common-mode limits (AVSS + 0.2 V to AVDD − 0.2 V at the PGA outputs), SPI, TSSOP-16 |
| TI ADS1261 (not selected) | Data sheet SBAS760C from ti.com | Downloaded and read: noise table at gain 128, AVDD 4.75–5.25 V |
| Nuvoton NAU7802 | Data sheet rev 1.7 — <https://cdn.sparkfun.com/assets/e/c/8/7/6/NAU7802_Data_Sheet_V1.7.pdf> | Downloaded and read: supply, LDO options and drive, rates, register map, power-up sequence. The noise table and parts of the electrical table did not survive text extraction |
| Phidgets FRC4165_0 (Ningbo ANE ST01) — selected cell | Product page <https://www.phidgets.com/?prodid=1321> and datasheet <https://www.phidgets.com/productfiles/FRC4165/FRC4165_0/Documentation/FRC4165_0_Datasheet.pdf> | Both read: output, impedances, overloads, errors, thread M12 × 1.75, dimensions, IP68, wire colours. Thread depth is not given; the dimension table is partly garbled in text extraction |
| HT Sensor TAS501 (fallback) | <https://cdn.sparkfun.com/assets/parts/1/2/2/3/8/TAS501.pdf> | Downloaded and read: output, overloads, errors, resistance, wiring colours, dimensions. Thread column ambiguous |
| Adafruit ESP32-C6 Feather (5933) | Product page | Features and price only; schematic and pinout not read |
| Adafruit NAU7802 breakout (4538) | Product page | Terminal block, excitation range, price; schematic not read |
| Maxim MAX17048 | — | **Not read.** Register addresses and scaling in the firmware (VCELL 0x02 at 78.125 µV/LSB, SOC 0x04 at 1/256 %) are from memory and must be checked against the datasheet |
| DIN 580 eye bolt M12 | Supplier data sheets (search results) | Working load limit 340 kg axial |

## Requirements for the custom PCB (input to Phase 3)

- Pre-certified ESP32-C3/C6 module with the antenna at the board edge and the keep-out respected.
- Bridge ADC (ADS1220, D-024) with DRDY on an interrupt pin; bridge traces short, paired, away from the antenna and the
  switching/charging section; analog ground joined to digital ground at one point.
- Dedicated low-noise 3.0–3.3 V regulator for AVDD/excitation (risk R-02); REFP/REFN sensed at the
  bridge connector (ratiometric).
- RC input filter and ESD protection on the bridge inputs; screw or spring terminal for the 4 wires + shield.
- USB-C with CC resistors and ESD; Li-ion charger sized for the cell; fuel gauge; battery protection
  if the cell has none; reverse-polarity protection on the battery connector.
- LED and one button; test points for 3V3, AVDD, GND, SDA, SCL, DRDY, VBAT; USB is the programming interface.
- Check the assembler's parts library and minimum rules before layout; run ERC/DRC and the
  assembler's DFM check; treat DFM flags as findings to judge, not to silence.
