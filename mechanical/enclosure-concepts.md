# Enclosure concepts — rev B design study

Status: **concept geometry for design review, 2026-11-17. Nothing printed, fitted or loaded.**
Rev A ([enclosure.md](enclosure.md), `cad/fenrir_enclosure.py`) is kept unchanged for comparison.
The owner rejected rev A's look (boxy, orange) and asked for a graphite / electric-blue product with
"FENRIR by LeBlond" branding.

Model: [`cad/concepts.py`](cad/concepts.py) (CadQuery, fully parametric). Run
`python mechanical/cad/concepts.py` to rebuild, re-check and re-render all three. STEP assemblies
go to `cad/out/fenrir-concept-{a,b,c}.step` (git-ignored, regenerated on demand).

| Concept | Review sheet (front, rear, side, three-quarter, exploded; same scale) |
|---|---|
| A — Precision | [drawings/concepts/concept-a-sheet.png](drawings/concepts/concept-a-sheet.png) |
| B — Technical | [drawings/concepts/concept-b-sheet.png](drawings/concepts/concept-b-sheet.png) |
| C — Ultralight | [drawings/concepts/concept-c-sheet.png](drawings/concepts/concept-c-sheet.png) |

## What every concept shares

- The same real hardware: Phidgets FRC4165_0 cell (datasheet dimensions), M12 lock nuts, the custom
  PCB envelope (46 × 38 mm, 3 mm corner radii; a requirement on the PCB design) and a flat LiPo
  (30 × 35 × 5 mm, **assumed**; a cell of that size has not been selected).
- **Force path:** upper attachment → M12 thread → load cell → M12 thread → lower attachment. Steel
  only.
- **The shell holds the cell's upper block only** (pads at z = 24…38 mm). Everywhere else, including
  the lower block, the lower nut and the lower attachment, there is a designed gap, so plastic cannot
  carry force around the strain gauges (decision D-017, requirement S-01).
- Graphite PA12 shell, darker recessed front plate with one blue light guide and one flush button,
  USB-C recessed in the right-hand side, "FENRIR / by LeBlond" in light grey. No CE mark or other
  certification symbol.

## CAD checks (run 2026-11-17, `check()` in the model)

These are geometric checks on nominal dimensions. They say nothing about print tolerances, the real
parts or loading.

| Check | A | B | C |
|---|---|---|---|
| Interference, shell vs cell, nuts, attachments, PCB, battery | 0 mm³ | 0 mm³ | 0 mm³ |
| Smallest gap from any shell part to the cell's lower block, lower nut, lower attachment | 1.50 mm | 1.50 mm | 1.50 mm |
| All solids valid | yes | yes | yes |

Defects found and fixed during the study: concept A's collars and screw heads stood proud of the
body and its nut bores broke through the back wall; concept B's chamfered faces and lug edges gave
invalid solids (which also hung the CAD kernel); concept C's battery and PCB corners clashed with the
bay. The figures above are after the fixes.

## Comparison

| | A — Precision | B — Technical | C — Ultralight |
|---|---|---|---|
| Idea | Smooth rounded body over the whole cell; nuts stand 1.5 mm proud at each end | Faceted body tapering to the attachments, one blue seam inlay, machined attachments | Electronics pod on the cell's front face only; steel cell visible at the back |
| Shell envelope (W × D × H) | 58 × 37 × 85 mm | 58 × 35 × 108 mm | 56 × 34 × 79 mm |
| Length over attachments | 194 mm | 192 mm | 194 mm |
| Printed parts (CAD volume × PA12 1.01 g/cm³) | 45 g | 69 g | 18 g |
| Steel: cell / attachments + nuts (CAD volume, simplified geometry) | 477 g / 353 g | 477 g / 278 g | 477 g / 353 g |
| Device mass, estimate (plus ≈ 15 g electronics, assumed) | ≈ 0.89 kg | ≈ 0.84 kg | ≈ 0.86 kg |
| Attachments | **Rated** DIN 580 M12 eye bolts (WLL 340 kg) | **Custom machined lugs: not rated.** Need design calculation, a qualified maker and a proof load before any use | **Rated** DIN 580 M12 eye bolts |
| Protection of cell and cable | Full | Full | Back and sides of the cell exposed; cable exit not protected |
| Printed parts | 2 shells + front plate + button + light guide | 2 shells + front plate + button + light guide + blue inlay | pod + strap + front plate + button + light guide |
| Print cost driver | Medium volume | Highest volume, extra inlay part | Lowest volume |
| Visual match with the owner's reference | Partial (clean, calm) | Closest (tapered, blue line, sculpted attachments) | Lowest (looks like a sensor with a pod) |

No printing or machining price has been obtained; every cost here is **NOT VERIFIED**. Print cost
is roughly proportional to part volume, so the ranking C < A < B holds whatever the service charges.

## Open problems common to all three (none solved)

1. **Closure.** The two shells meet around the cell with only 3.5 mm between cell and outer
   surface: there is no room for screw bosses beside the cell. The screws in the renders mark
   positions, not a working joint. Detail design must choose between snap-fits, bosses in the end
   regions (adds length), or a bonded/clipped front plate.
2. **Antenna next to steel.** The radio module sits 4–5 mm in front of the steel cell. Steel that
   close detunes a PCB antenna and shortens range. The shell is plastic (radio-transparent), but the
   module position or antenna type needs checking with a range test (V-26).
3. **Cable route and strain relief** from the cell to the PCB terminal are not modelled.
4. **Real dimensions.** Cell slot positions, cable exit, thread depth, eye-bolt collar and battery
   size must be measured before any print (list in [enclosure.md](enclosure.md)).
5. **Tolerances.** The model uses nominal sizes. MJF PA12 typically needs about ±0.3 mm allowance
   (general guidance, not a supplier figure); the 1.5 mm gaps are chosen to leave margin for that.

## Manufacturing routes

| | Option A: printed (prototype and small series) | Option B: premium |
|---|---|---|
| Shell | MJF PA12, dyed black/graphite, bead-blasted matte, from a European service | CNC aluminium front frame, anodised, **with a polymer window over the antenna**; PA12 or PC back |
| Fasteners | Commercial M2/M2.5 screws or snap-fits | Same |
| Feasibility | Fits the owner's situation (no printer) | Machining cost and part count rise; the radio window adds a joint |
| Budget | Plausible within €100 for the device: **not verified** | Very likely above the €100 target: **not verified** |

A metal shell would not be rated or structural just because it is machined: it stays out of the
load path in every option.

## Recommendation

**Concept A (Precision) for detailed engineering.** It is the only fully enclosing design that keeps
**rated** attachments, so it changes nothing in the load-path analysis; it is also shorter than B
and has fewer parts. B's look is closest to the reference, but only because of custom lugs that
would need their own engineering and a proof load. It could become a later premium variant once the
rest of the device is proven. C protects the least and gives up the "product" look the brief asks
for.

Before A is released for printing: solve the closure, place the antenna, route the cable, measure
the real parts, then run V-23, V-24 and V-26.
