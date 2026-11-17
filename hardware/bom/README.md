# Bill of materials

FENRIR is **one product** (decision D-023, 2026-11-17): the custom PCB in the concept A enclosure.
[`product-bom.csv`](product-bom.csv) is its parts list. **Nothing has been ordered.** Every price carries
its source and date; `NOT VERIFIED` means no price was found or checked.

Only the load cell is priced today (Phidgets FRC4165_0, US$50 on 2026-11-16, decision D-016). The board
cannot be quoted before its schematic and layout exist and pass ERC/DRC; the enclosure cannot be quoted
before a printing service is chosen. **No total is given**, because a total built mostly from
assumptions would look more certain than it is.

Part numbers marked "(to confirm)" are the intended parts; each is checked against its datasheet and
the assembler's library in the schematic step.

## Superseded: modular prototype list

[`prototype-bom.csv`](prototype-bom.csv) is the Phase 2 Option A list (Adafruit Feather + NAU7802
breakout). It is **not to be ordered**: D-023 dropped the modular prototype. It is kept as a record of
the prices found on 2026-11-16. The sections below describe that list.

## Expected prototype cost (parts only)

Unverified rows use a stated assumption so the total is visible; assumptions are marked `~`.
The euro value of the US-dollar price is not converted here: no exchange rate was checked.

| Item | Price | Basis |
|---|---:|---|
| Phidgets FRC4165_0 load cell | US$50.00 | Manufacturer page, 2026-11-16 |
| ESP32-C6 Feather | €12.81 | DigiKey EU, excl. VAT |
| NAU7802 breakout | €7.00 | EU retailer listing |
| LiPo 400 mAh | ~€7 | assumption |
| STEMMA QT cable | ~€1 | assumption |
| 2 × eye bolt DIN 580 M12 | ~€10 | assumption |
| 2 × M12 thin nut | ~€1 | assumption |
| 3D-printed enclosure (service) | not priced | NOT VERIFIED; the earlier ~€8 box assumption no longer applies |
| **Total without enclosure** | **US$50 + ~€39** | the printed enclosure is not priced and will take the total past €100 |

On top: shipping from three sellers, French VAT (20 %) on excl.-VAT prices, and import VAT plus
carrier fees on the load cell if it ships from Canada or the UK. **Landed cost will exceed the €100
target** once the printed enclosure is added. Buying the cell from an EU-shipping reseller
would remove the import step; none was confirmed today.

## Quantity 1 / 5 / 10

| Item | 1 | 5 | 10 | Source |
|---|---:|---:|---:|---|
| Load cell FRC4165_0 | US$50 | US$48 | US$46 | Phidgets page |
| ESP32-C6 Feather | US$14.95 | US$14.95 | US$13.46 | Adafruit page |
| NAU7802 breakout | US$5.95 | US$5.95 | US$5.36 | Adafruit page |

Per-unit saving at 10 units is about US$6, plus shared shipping. A real reduction needs Option B
(custom PCB), which has not been quoted because no schematic exists yet.

## Tools the owner needs for Phase 2

Small flat screwdriver (terminal block), 19 mm spanner (M12 nuts), tape measure or calliper.
Strongly recommended: a basic multimeter (~€15) to check battery polarity and the excitation voltage,
and a USB power meter (~€10) for current measurement. None of these is included in the totals above.
