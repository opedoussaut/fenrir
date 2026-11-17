"""FENRIR enclosure - concept A "Precision", detailed engineering (rev C).

Status: DETAIL DESIGN IN PROGRESS. Not released for manufacture.
Owner chose concept A on 2026-11-17 (decision D-021). The concept model in concepts.py is
kept unchanged; this file adds what the concept lacked:

  - a closure that fits: four M2 thread-forming screws from the back, in "shoulders" beside the
    eye bolts at each end, because there is no room for screw bosses beside the cell;
  - counterbores, clearance holes and pilot holes sized for M2 thread-forming screws (>= 1 mm wall);
  - checks that the shoulders clear both eye bolts (the lower one moves with the load).

Still open (see mechanical/enclosure-a.md): cable exit (needs the real cell), PCB and front-plate
retention details, antenna range (test V-26), print tolerances from the chosen service.

Run:  python mechanical/cad/fenrir_a.py   (always under a timeout: OCC can hang on bad fillets)
"""

from __future__ import annotations

import pathlib
import sys

import cadquery as cq

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from concepts import (CELL_H, CELL_W, GAP, GRAPHITE, NUT_H, Y_BACK, Y_BAY, Y_FRONT, ZINC, VIEWS,  # noqa: E402
                      box, cell_cavity, check, electronics, fascia_parts, grip_pads, prism, rated_hardware,
                      rect, render, sheet, soften, usb_port, ycyl, zcyl)

HW = CELL_W / 2 + GAP + 2.0            # 28.9 half width
HZ = CELL_H / 2 + NUT_H - GAP          # 42.6: centre of each end stops 1.5 mm short of the nut top
SHOULDER = 48.6                        # shoulders beside the eye bolt reach this far
NOTCH_HW = 19.0                        # half width of the opening for the eye bolt (1.5 mm to its ring)
NUT_R = 19.0 / 0.866 / 2 + GAP         # hex nut across corners + clearance = 12.5
Y_REAR = Y_BACK - 1.5                  # 2 mm wall behind the nut bore

# M2 thread-forming screw for plastics (30 deg flank "PT"-style), pan head, Torx T6.
# M2.5 left only 0.3 mm of wall around the counterbore in the shoulders.
SCREW_XZ = [(-22.9, 43.6), (22.9, 43.6), (-22.9, -43.6), (22.9, -43.6)]   # centred in the shoulder corner
SCREW_L = 10.0
CLAMP = 3.0                            # back-shell material under the screw head
HEAD_D, HEAD_H = 3.8, 1.6              # typical M2 pan head: VERIFY against the chosen screw
CBORE_D = 4.4                          # counterbore, head diameter + 0.6
CLEAR_D = 2.4                          # clearance hole in the back shell
PILOT_D = 1.7                          # pilot hole in the front shell: CHECK the screw maker's table for PA12
MIN_WALL = 1.0                         # design rule for MJF PA12 walls (general guidance, not a supplier figure)
PILOT_DEPTH = SCREW_L - CLAMP + 1.0


def body() -> cq.Workplane:
    main = prism(rect(HW, -HZ, HZ), Y_REAR, Y_FRONT).edges("|Y").fillet(12.0)
    ends = prism(rect(HW, -SHOULDER, SHOULDER), Y_REAR, Y_FRONT).edges("|Y").fillet(6.0)
    ends = ends.intersect(box(-99, 99, -99, 99, -SHOULDER, -30).union(box(-99, 99, -99, 99, 30, SHOULDER)))
    b = main.union(ends)
    for s in (1, -1):
        notch = prism(rect(NOTCH_HW, HZ, 70.0), Y_REAR - 1, Y_FRONT + 1).edges("|Y").fillet(3.0)
        b = b.cut(notch if s > 0 else notch.mirror("XY"))
    b = soften(b, ">Y", (4.0, 3.0, 2.0))
    b = soften(b, "<Y", (0.6, 0.5))        # small edge break at the back: the counterbores open there
    return b


def counterbore_walls() -> dict:
    """Thinnest plastic between each counterbore and the outside of the body (back face excluded,
    since the counterbore opens through it). Measured on the CAD solids."""
    cavity = cell_cavity()
    for s in (1, -1):
        cavity = cavity.union(zcyl(NUT_R, min(s * 36, s * 70), max(s * 36, s * 70)))
    outer = body().cut(cavity).val()
    faces = [f for f in outer.Faces()
             if not (f.geomType() == "PLANE" and abs(f.Center().y - Y_REAR) < 0.05)]
    res = {}
    for x, z in SCREW_XZ:
        cb = ycyl(CBORE_D / 2, Y_REAR, -CLAMP, x, z).val()
        side = [f for f in cb.Faces() if f.geomType() == "CYLINDER"][0]
        res[(x, z)] = round(min(side.distance(f) for f in faces), 2)
    return res


def build():
    cavity = cell_cavity()
    for s in (1, -1):
        cavity = cavity.union(zcyl(NUT_R, min(s * 36, s * 70), max(s * 36, s * 70)))
    bay = prism(rect(25.0, -40.0, 40.0), Y_BAY, Y_FRONT + 1).edges("|Y").fillet(6.0)
    parts, usb_z = electronics(z_top=37.5)
    shell = body().cut(cavity).cut(bay).cut(usb_port(HW, usb_z)).union(grip_pads())

    back = shell.cut(box(-99, 99, 0, 99, -99, 99))
    front = shell.cut(box(-99, 99, -99, 0, -99, 99))
    heads = cq.Workplane("XY")
    shanks = cq.Workplane("XY")
    for x, z in SCREW_XZ:
        back = back.cut(ycyl(CBORE_D / 2, Y_REAR - 1, -CLAMP, x, z)).cut(ycyl(CLEAR_D / 2, -CLAMP - 0.1, 0.1, x, z))
        front = front.cut(ycyl(PILOT_D / 2, -0.1, PILOT_DEPTH, x, z))
        heads = heads.union(ycyl(HEAD_D / 2, -CLAMP - HEAD_H, -CLAMP, x, z))
        shanks = shanks.union(ycyl(1.25, -CLAMP, SCREW_L - CLAMP, x, z))

    out = {"back_shell": (back, GRAPHITE), "front_shell": (front, GRAPHITE)}
    out.update(fascia_parts(25.0, -40.0, 40.0, 6.0, led=(-12, 26), button=(9, 26)))
    out["screws"] = (heads.union(shanks), ZINC)
    out.update(parts)
    out.update(rated_hardware())
    return out


def screw_checks(parts) -> dict:
    """Wall left around each screw feature, measured on the CAD solids."""
    from concepts import solid_of
    back = solid_of(parts["back_shell"][0])
    front = solid_of(parts["front_shell"][0])
    cell = solid_of(parts["cell"][0])
    res = {}
    for x, z in SCREW_XZ:
        cb = ycyl(CBORE_D / 2, Y_REAR + 0.01, -CLAMP, x, z).val()
        pil = ycyl(PILOT_D / 2, 0.01, PILOT_DEPTH, x, z).val()
        res[(x, z)] = {
            "counterbore_to_cell_mm": round(cb.distance(cell), 2),
            "pilot_to_cell_mm": round(pil.distance(cell), 2),
            "pilot_engagement_mm": round(SCREW_L - CLAMP, 1),
            "back_material_ok": back.isValid(),
            "front_material_ok": front.isValid(),
        }
    return res


def main() -> None:
    root = pathlib.Path(__file__).resolve().parents[1]
    folder = root / "drawings" / "concepts"
    out = root / "cad" / "out"
    folder.mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=True)
    parts = build()
    print("geometry built", flush=True)
    res = check(parts)
    print("checks done", flush=True)
    for k, v in screw_checks(parts).items():
        print("screw", k, v, flush=True)
    walls = counterbore_walls()
    print("counterbore wall mm", walls, "rule", MIN_WALL, "OK" if min(walls.values()) >= MIN_WALL else "FAIL", flush=True)
    for v in VIEWS:
        render(parts, folder / f"concept-a-detail-{v}.png", v, explode=(v == "exploded"))
    x, y, z = res["shell_xyz"]
    sheet(folder, "a-detail", "A  Precision, detail rev C",
          [f"shell {x:.0f} x {y:.0f} x {z:.0f} mm", f"length over eye bolts {res['overall_len']:.0f} mm",
           f"printed parts {res['plastic_g']:.0f} g (estimate)", "4 x M2 thread-forming screws from the back"])
    asm = cq.Assembly(name="fenrir_a_revC")
    for name, (wp, colour) in parts.items():
        asm.add(wp, name=name, color=cq.Color(*colour))
    asm.export(str(out / "fenrir-a-revC.step"))
    for name in ("back_shell", "front_shell", "fascia", "button", "light"):
        cq.exporters.export(parts[name][0], str(out / f"fenrir-a-revC-{name}.step"))
    print(f"shell {x:.1f} x {y:.1f} x {z:.1f} | overall {res['overall_len']:.1f} | plastic {res['plastic_g']:.1f} g"
          f" | interference {res['interference_mm3']:.2f} mm3 | min gap lower end {res['min_gap_lower_mm']:.2f} mm"
          f" | gap checks failed {res.get('gap_failures', 0)}")


if __name__ == "__main__":
    main()
