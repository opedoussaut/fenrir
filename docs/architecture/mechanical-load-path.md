# Mechanical load path and safety

Status: **design intent. No part has been bought, measured or loaded.** An enclosure concept model
exists ([mechanical/enclosure.md](../../mechanical/enclosure.md)); it is not released for printing.

> **FENRIR is a force-measuring instrument, not climbing safety equipment.** It must never be the only
> link between a person and a fall, must not be used for belaying, anchoring, lowering or fall arrest,
> and must not be shock-loaded. Use it for pulls where letting go simply ends the effort: feet on the
> ground, or a lifted weight a few centimetres off the floor.

## Load path

```
carabiner / sling  (user's own, rated)
      │
 DIN 580 M12 lifting eye bolt ── M12 thin lock nut (DIN 439)
      │  threaded into
 S-type load cell Phidgets FRC4165_0, 200 kg, M12 × 1.75
      │  threaded into
 DIN 580 M12 lifting eye bolt ── M12 thin lock nut
      │
carabiner / edge / pick-up handle
```

Metal only. A 3D-printed shell wraps the cell and holds the electronics on its front face (decision
D-017). The shell grips the cell's **upper block only** and keeps a 1.5 mm gap everywhere else,
including around the lower eye bolt, so no force can pass through it. Both eye bolts pass through
clearance openings in the shell.

The two eyes work as pin joints: a carabiner in each eye lets the assembly align with the pull, which
keeps bending and side load out of the cell. This is the reason for eye bolts instead of rigid
studs or plates.

## Ratings (from documents, not tests)

| Part | Rating | Source | Margin at 2000 N |
|---|---|---|---|
| Load cell Phidgets FRC4165_0 (Ningbo ANE ST01), 200 kg | Capacity 200 kg = **1961 N**; safe overload 150 % = 2942 N; ultimate overload 200 % = 3923 N | Manufacturer datasheet | 2000 N is 102 % of capacity; 1.47× to safe overload; 1.96× to ultimate |
| Eye bolt DIN 580 M12, C15E steel | Working load limit **340 kg = 3334 N** axial; 240 kg at 45°; supplier sheets state a safety coefficient of 6 | French supplier data sheets (search, 2026-11-16) | 1.67× on WLL |
| Carabiners / slings | User-supplied; EN 12275 climbing carabiners are rated ≥ 20 kN on the major axis | Standard knowledge, not re-verified | ≥ 10× |
| Enclosure, PCB, battery | **0 N** — not in the load path | Design rule S-01 | — |

**The load cell is the weakest element**, and its margin is small by lifting or climbing standards
(1.5× to "safe overload", 2× to "ultimate" — the datasheet does not define ultimate as breaking).
That is normal for a measuring cell and is exactly why the device is not safety equipment.

What may be said today:

- Display range: 0–2000 N.
- **Rated working range: not established.** Proposed after proof-loading: 0–1960 N, with the overload
  warning at 2200 N as implemented in firmware.
- "Safe at 2000 N": **may not be claimed** until test V-15 has been done and recorded.

## Things that will go wrong if ignored

| Failure mode | Cause | Prevention |
|---|---|---|
| Eye bolt bottoms out and bridges the cell's flexure | S-type cells are threaded through to the central cut; a bolt screwed in too far touches the other half | Set the depth with the lock nut; keep the bolt tip short of the cut; check that the reading returns to zero and responds to hand pull |
| Too little thread engagement | Lock nut uses up thread; unknown hole depth | Aim for ≥ 12 mm (1 × diameter) engaged; measure the hole on receipt (risk R-04) |
| Eye bolt unscrews under rotation | Twisting during use | Lock nut tightened against the cell; witness mark with paint pen; check before each session |
| Side load / bending on the cell | Rigid attachment, pulling at an angle | Carabiners in both eyes; pull in line |
| Shock load | Dropping a weight onto the device, falling onto it | Forbidden use; overload flag is a warning, not a protection |
| Cable torn out | Cable snagged while under load | Strain relief at the box; cable tied along the fixed half of the cell |
| Cell overloaded without notice | Two-handed or lower-body pulls can exceed 2 kN | Overload flag at 2200 N in every packet; 200 kg capacity confirmed by the owner (decision D-006), so such pulls are out of scope and must not be attempted |
| Corrosion or damaged thread | Outdoor use, chalk, sweat | Inspect; cell is IP66 alloy steel, not stainless |

## First loading (test V-15 outline)

No person in the load path. Hang the assembly from a rated overhead anchor (e.g. a pull-up bar rated
well above the test load), with the weights no more than a few centimetres above a padded floor, and
keep hands and feet out from under them.

1. Assemble with lock nuts; mark the threads.
2. Step up in dead weight to the largest load available, holding each step 60 s; record reading, zero
   return and any thread movement.
3. Unload in the same steps.
4. Inspect threads, eyes and cable.

A proof load to the full 2000 N needs about 204 kg of dead weight or a test machine — in practice an
external lab or a gym with calibrated plates and a rack. Until that is done the device is proven only
to the largest load actually applied.

## Enclosure target (Phase 3, not started)

Constraints for the design, including the concept render reviewed on 2026-11-16:

- The cell body (76.2 × 50.8 × 19 mm) plus two eye bolts gives roughly 180 mm eye-to-eye. A 95 mm device
  would need a custom-machined sensing body, which conflicts with using a purchasable, datasheet-backed
  cell.
- Attachment points are the steel eyes passing through openings in the shell with clearance all round;
  the shell must be free to move a little relative to the cell so it can never pick up load.
- One side of the shell houses the electronics and battery; USB-C, LED and button on that side.
- Either an off-the-shelf ABS box fixed to the cell, or a two-part printed shell from an online
  printing service (PETG or PA12). No owner-operated printer needed.
- No CE mark or origin marking on the product until the corresponding conformity work is done.
