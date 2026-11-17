# Enclosure — concept A "Precision", detail design (rev C)

Status: **detail design in progress, 2026-11-17. Not released for printing. Nothing printed,
fitted or loaded.** The owner chose concept A on 2026-11-17 (decision D-021).

Model: [`cad/fenrir_a.py`](cad/fenrir_a.py), built on the shared helpers in
[`cad/concepts.py`](cad/concepts.py) (the concept versions are kept unchanged).
Review sheet: [drawings/concepts/concept-a-detail-sheet.png](drawings/concepts/concept-a-detail-sheet.png).
Rebuild with `timeout 600 python mechanical/cad/fenrir_a.py`; it writes STEP files for the assembly
and for each printed part to `cad/out/` (git-ignored until release).

## What changed from the concept

| Topic | Concept A | Rev C | Why |
|---|---|---|---|
| Closure | Screw marks only; no room for bosses | **4 × M2 thread-forming screws from the back**, in shoulders beside each eye bolt | Beside the cell there is only 3.5 mm of material |
| Ends | Body stops 1.5 mm short of the nuts | Same in the centre, plus two shoulders per end reaching 48.6 mm, with a 38 mm wide opening for the eye bolt | Room for the screws; frames the eye bolts |
| Shell height | 85 mm | **97 mm** | Cost of the shoulders |
| Back edge | 2.5–4 mm round | 0.6 mm edge break | A larger round left 0.15–0.5 mm of plastic at the counterbore mouths |

Width (58 mm), depth (37 mm) and length over the eye bolts (194 mm) are unchanged.

## Force path (unchanged, steel only)

Upper DIN 580 M12 eye bolt → lock nut → load cell → lock nut → lower eye bolt. The shell grips the
cell's upper block only (pads at z = 24…38 mm). The lower block, lower nut and lower eye bolt float
inside a designed gap of at least 1.5 mm. The screws join the two shell halves to each other; none
of them touches steel.

## CAD checks (run 2026-11-17 on nominal geometry)

| Check | Result | Rule |
|---|---|---|
| Interference, shells vs cell, nuts, eye bolts, PCB, battery | 0 mm³ | 0 |
| Gap from shell to cell lower block, lower nut, lower eye bolt | 1.50 mm (smallest) | ≥ 1.5 mm |
| Plastic around each counterbore (to outside and to the cell cavity) | 1.38 mm | ≥ 1.0 mm for MJF PA12 (general guidance, not a supplier figure) |
| Counterbore / pilot hole to the steel cell | 3.3 mm / 4.65 mm | no contact |
| Screw thread engagement in the front shell | 7.0 mm | ≥ 2.5 × d is the usual aim for thread-forming screws in plastic |
| All solids valid | yes | — |

Found and fixed during this step: the first shoulder layout came within **1.04 mm** of the lower
eye bolt's ring (now 1.50 mm, by widening the opening to 38 mm); M2.5 screws left **0.32 mm** of
wall (now M2 at 1.38 mm). None of this says anything about the real parts or print tolerances.

## Tolerances (proposal for MJF PA12)

| Feature | Value in the model | Note |
|---|---|---|
| General outline | nominal | MJF services usually quote around ±0.3 mm (+0.3 % on long dimensions): **check the chosen service** |
| Clearance to any steel part | 1.5 mm | Leaves margin for ±0.3 mm per side plus real-part variation |
| Grip pads on the upper block | 0 mm (line-to-line) | Pads must be adjusted after measuring the real cell: they should press lightly, not crush |
| Shell-to-shell joint | 0 mm | Add 0.1–0.2 mm relief before release |
| Screw clearance hole | Ø 2.4 mm | M2 + 0.4 |
| Counterbore | Ø 4.4 mm × 11.5 mm deep | Pan head Ø 3.8 assumed |
| Pilot hole | Ø 1.7 mm × 8 mm deep | **Check the screw maker's table for PA12 before release** |

## Enclosure parts list

Prices: **NOT VERIFIED**. No supplier was contacted.

| Ref | Part | Qty | Material / spec | Source |
|---|---|---:|---|---|
| EN1 | Back shell | 1 | MJF PA12, dyed, bead-blasted | Printing service |
| EN2 | Front shell (with electronics bay) | 1 | MJF PA12, dyed, bead-blasted | Printing service |
| EN3 | Front plate | 1 | MJF PA12, darker dye, logo pad-printed or laser-marked (method open) | Printing service |
| EN4 | Button cap | 1 | PA12 or TPU | Printing service |
| EN5 | Light guide | 1 | Clear PC or PMMA rod, Ø 2.5 mm | Catalogue part (not chosen) |
| EN6 | Screw, M2 × 10, thread-forming for plastics, pan head, Torx | 4 | Steel, zinc or black finish | Catalogue part (not chosen) |
| EN7 | Front-plate adhesive | 1 | Die-cut acrylic foam tape (VHB type) | Proposal, not tested |

## Assembly sequence (proposed, not tried)

1. Fit eye bolts and lock nuts to the cell as in the [mechanical load path](../docs/architecture/mechanical-load-path.md);
   check the reading returns to zero.
2. Place the FENRIR PCB and battery in the front shell bay; connect the cell wires to the spring terminal.
3. Close the back shell around the cell; the pads seat on the upper block.
4. Fit the four screws from the back by hand (Torx driver); no power tool.
5. Fit the button cap and light guide; bond the front plate.
6. Check again that the reading returns to zero with the shell on (V-24).

## Open items (block release)

1. **Cable exit and strain relief.** Where the cable leaves the real cell is unknown; the route to
   the PCB terminal cannot be drawn until the cell is measured.
2. **PCB and battery retention** in the bay (ribs or two screws into the bay floor) are not modelled.
3. **Antenna.** The module sits 4–5 mm in front of the steel cell; no position in this envelope
   puts it clear of steel. Plan: range-test the prototype early (V-26); fallback is the
   ESP32-C6-MINI-1U (u.FL connector) with a small external antenna in a shoulder.
4. **Real-part dimensions** (cell, eye bolts, battery, PCB): see [enclosure.md](enclosure.md).
5. **Print service and tolerances**: not chosen, not quoted.
6. **Dimensioned 2D drawings**: not produced yet; the STEP files carry the geometry.
7. Physical checks V-23 (fit), V-24 (shell carries no load), V-26 (radio range): not started.
8. ~~Prototype boards do not fit this bay.~~ **Closed 2026-11-17 by D-023:** FENRIR is one product,
   the custom PCB (46 × 38 mm) in this shell; no Adafruit prototype and no second shell variant.
   The bare board is brought up on the bench before the shell is ordered.
