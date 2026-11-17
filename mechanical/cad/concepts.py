"""FENRIR enclosure - three industrial-design concepts (rev B study).

Status: CONCEPT geometry for a design review. Not released for manufacture.
Rev A (fenrir_enclosure.py) is kept unchanged for comparison.

All three concepts are built around the same real hardware:
  - Phidgets FRC4165_0 S-type load cell, 50.8 x 19 x 76.2 mm, M12 x 1.75 (datasheet)
  - M12 thin lock nuts (DIN 439)
  - the custom-PCB envelope and a flat LiPo cell (ASSUMED sizes, see below)
Concepts A and C use rated DIN 580 M12 lifting eye bolts. Concept B shows custom machined
attachments: these are NOT rated parts and would need engineering and a proof load.

Rule for every concept: the shell touches the cell's UPPER block only. Around the lower
block, the lower nut and the lower attachment there is a designed gap, so the plastic
cannot carry force around the strain gauges. check() measures this in the CAD.

Run:  python mechanical/cad/concepts.py
Axes: Z = load axis, X = width, Y = thickness (front = +Y). Millimetres.
"""

from __future__ import annotations

import pathlib
import sys

import cadquery as cq

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fenrir_enclosure import (CELL_H, CELL_T, CELL_W, EYE_COLLAR_D, NUT_H, eye_bolt, load_cell,  # noqa: E402
                              nut)

# --- Assumed electronics envelope (custom PCB not designed yet) ---------------
PCB = (46.0, 38.0, 1.6)        # X, Z, thickness - REQUIREMENT placed on the PCB design
PCB_COMP_H = 5.0               # tallest part on the PCB
BATT = (30.0, 35.0, 5.0)       # X, Z, thickness - ASSUMED flat 500 mAh class cell
BAY = 8.0                      # electronics bay depth for the custom PCB
BAY_PROTO = 10.5               # depth needed by the two Adafruit prototype boards

WALL = 2.0
GAP = 1.5                      # designed clearance to every moving steel part
FLOOR = 1.2                    # wall between the cell and the electronics
Y_BACK = -(CELL_T / 2 + GAP + WALL)
Y_FLOOR = CELL_T / 2 + GAP
Y_BAY = Y_FLOOR + FLOOR
Y_FRONT = Y_BAY + BAY + WALL
PAD_Z0, PAD_Z1 = 24.0, CELL_H / 2          # grip zone on the upper block

GRAPHITE = (0.115, 0.125, 0.14)
FASCIA = (0.075, 0.08, 0.09)
BLUE = (0.05, 0.42, 1.0)
STEEL = (0.62, 0.64, 0.66)
ZINC = (0.70, 0.70, 0.69)
MACHINED = (0.66, 0.67, 0.69)
PCB_GREEN = (0.05, 0.22, 0.14)
BATT_GREY = (0.45, 0.46, 0.48)
MARK = (0.78, 0.80, 0.83)
PA12_DENSITY = 1.01e-3         # g/mm3
STEEL_DENSITY = 7.85e-3


def prism(pts, y0: float, y1: float) -> cq.Workplane:
    """Extrude a profile given in (X, Z) between y0 and y1."""
    wp = cq.Workplane("XY").polyline(pts).close().extrude(y1 - y0)
    return wp.rotate((0, 0, 0), (1, 0, 0), 90).translate((0, y1, 0))


def rect(hw: float, z0: float, z1: float):
    return [(-hw, z0), (hw, z0), (hw, z1), (-hw, z1)]


def box(x0, x1, y0, y1, z0, z1) -> cq.Workplane:
    return cq.Workplane("XY").box(x1 - x0, y1 - y0, z1 - z0).translate(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))


def zcyl(r: float, z0: float, z1: float, x: float = 0, y: float = 0) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z0).center(x, y).circle(r).extrude(z1 - z0)


def ycyl(r: float, y0: float, y1: float, x: float, z: float) -> cq.Workplane:
    c = cq.Workplane("XY").circle(r).extrude(y1 - y0)
    return c.rotate((0, 0, 0), (1, 0, 0), 90).translate((x, y1, z))


def soften(wp: cq.Workplane, selector: str, radii, chamfer: bool = False) -> cq.Workplane:
    """Round or chamfer one face's edges; keep the first result that is a valid solid."""
    for r in radii:
        try:
            sel = wp.faces(selector).edges()
            res = sel.chamfer(r) if chamfer else sel.fillet(r)
        except Exception:
            continue
        if all(s.isValid() for s in res.vals() if isinstance(s, cq.Shape)):
            return res
    return wp


def cell_cavity() -> cq.Workplane:
    return box(-CELL_W / 2 - GAP, CELL_W / 2 + GAP, -CELL_T / 2 - GAP, CELL_T / 2 + GAP,
               -CELL_H / 2 - GAP, CELL_H / 2 + GAP)


def grip_pads(back: bool = True, front: bool = True, sides: bool = True) -> cq.Workplane:
    pads = cq.Workplane("XY")
    if sides:
        for s in (1, -1):
            x0, x1 = sorted((s * CELL_W / 2, s * (CELL_W / 2 + GAP)))
            pads = pads.union(box(x0, x1, -CELL_T / 2, CELL_T / 2, PAD_Z0, PAD_Z1))
    if back:
        pads = pads.union(box(-20, 20, -CELL_T / 2 - GAP, -CELL_T / 2, PAD_Z0, PAD_Z1))
    if front:
        pads = pads.union(box(-20, 20, CELL_T / 2, CELL_T / 2 + GAP, PAD_Z0, PAD_Z1))
    return pads


def fascia_parts(hw: float, z0: float, z1: float, r: float, led=(-12.0, 9.0), button=(8.0, 9.0)):
    """Recessed front plate carrying the mark, the light guide and the button."""
    plate = prism(rect(hw, z0, z1), Y_FRONT - 2.0, Y_FRONT - 0.6).edges("|Y").fillet(r)
    plate = plate.cut(ycyl(1.3, Y_FRONT - 3, Y_FRONT, led[0], led[1]))
    plate = plate.cut(ycyl(5.2, Y_FRONT - 3, Y_FRONT, button[0], button[1]))
    light = ycyl(1.25, Y_FRONT - 2.0, Y_FRONT - 0.55, led[0], led[1])
    btn = ycyl(4.9, Y_FRONT - 2.0, Y_FRONT - 0.7, button[0], button[1])
    logo = (cq.Workplane("XZ").workplane(offset=-(Y_FRONT - 0.6)).center(0, z0 + 21)
            .text("FENRIR", 6.5, -0.25, kind="bold").mirror("YZ"))
    sub = (cq.Workplane("XZ").workplane(offset=-(Y_FRONT - 0.6)).center(0, z0 + 13.5)
           .text("by LeBlond", 3.2, -0.25, kind="italic").mirror("YZ"))
    return {"fascia": (plate, FASCIA), "light": (light, BLUE), "button": (btn, GRAPHITE),
            "logo": (logo.union(sub), MARK)}


def electronics(z_top: float = CELL_H / 2 + 2.0, batt_gap: float = 2.0):
    y = Y_BAY + 0.8
    pcb = box(-PCB[0] / 2, PCB[0] / 2, y, y + PCB[2], z_top - PCB[1], z_top).edges("|Y").fillet(3.0)
    module = box(-8.3, 8.3, y + PCB[2], y + PCB[2] + 2.4, z_top - 13.5, z_top - 0.3)
    usb = box(PCB[0] / 2 - 7.0, PCB[0] / 2 + 0.6, y + PCB[2], y + PCB[2] + 3.2, z_top - 30, z_top - 21)
    term = box(-21, -3, y + PCB[2], y + PCB[2] + PCB_COMP_H, z_top - 37, z_top - 30)
    zb = z_top - PCB[1] - batt_gap
    batt = box(-BATT[0] / 2, BATT[0] / 2, Y_BAY + 0.5, Y_BAY + 0.5 + BATT[2], zb - BATT[1], zb)
    return {"pcb": (pcb, PCB_GREEN), "module": (module, MARK), "usb": (usb, ZINC),
            "terminal": (term, BATT_GREY), "battery": (batt, BATT_GREY)}, z_top - 25.5


def usb_port(x_side: float, z: float) -> cq.Workplane:
    y = Y_BAY + 0.8 + PCB[2] + 1.6
    return box(x_side - 6, x_side + 6, y - 2.6, y + 2.6, z - 6.2, z + 6.2).edges("|X").fillet(2.4)


def rated_hardware():
    return {"eye_top": (eye_bolt(True), ZINC), "eye_bottom": (eye_bolt(False), ZINC),
            "nut_top": (nut(True), ZINC), "nut_bottom": (nut(False), ZINC),
            "cell": (load_cell(), STEEL)}


def lug(top: bool, shoulder: float, opening_w: float, opening_h: float, bar: float) -> cq.Workplane:
    """Custom machined attachment with integral M12 stud. NOT a rated part."""
    seat = CELL_H / 2 + NUT_H
    z0 = seat + shoulder
    stud = zcyl(6.0, CELL_H / 2 - 16, seat)
    neck = zcyl(10.0, seat, z0 + 2)
    hw, ht = opening_w / 2 + bar, opening_h + 2 * bar
    outer = [(-10, z0), (10, z0), (hw, z0 + ht * 0.45), (hw * 0.82, z0 + ht), (-hw * 0.82, z0 + ht),
             (-hw, z0 + ht * 0.45)]
    plate = prism(outer, -6, 6).edges("|Y").fillet(min(bar * 0.9, 6))
    iw = opening_w / 2
    inner = [(-iw * 0.45, z0 + bar), (iw * 0.45, z0 + bar), (iw, z0 + bar + opening_h * 0.5),
             (iw * 0.8, z0 + bar + opening_h), (-iw * 0.8, z0 + bar + opening_h), (-iw, z0 + bar + opening_h * 0.5)]
    hole = prism(inner, -8, 8).edges("|Y").fillet(min(opening_w * 0.2, 5))
    part = plate.cut(hole)
    part = soften(part, ">Y", (2.0, 1.0)).union(stud).union(neck)
    part = soften(part, "<Y", (2.0, 1.0))
    return part if top else part.mirror("XY")


def screws(points, y_head: float) -> cq.Workplane:
    wp = cq.Workplane("XY")
    for x, z in points:
        wp = wp.union(ycyl(2.7, y_head - 0.2, y_head + 1.0, x, z))
    return wp


# ----------------------------------------------------------------------------
def concept_a():
    """Precision: smooth rounded body ending just short of the nuts, rated eye bolts."""
    hw = CELL_W / 2 + GAP + WALL
    hz = CELL_H / 2 + NUT_H - GAP          # nuts stand 1.5 mm proud: the lower one must never touch
    nut_r = 19.0 / 0.866 / 2 + GAP         # hex nut across corners + clearance
    y_back = Y_BACK - 1.5                  # 2 mm wall behind the nut bore
    body = prism(rect(hw, -hz, hz), y_back, Y_FRONT).edges("|Y").fillet(12.0)
    body = soften(body, ">Y", (5.0, 4.0, 2.5))
    body = soften(body, "<Y", (5.0, 4.0, 2.5))
    cavity = cell_cavity()
    for s in (1, -1):
        cavity = cavity.union(zcyl(nut_r, min(s * 36, s * 70), max(s * 36, s * 70)))
    bay = prism(rect(25.0, -40.0, 40.0), Y_BAY, Y_FRONT + 1).edges("|Y").fillet(6.0)
    parts, usb_z = electronics(z_top=37.5)
    shell = body.cut(cavity).cut(bay).cut(usb_port(hw, usb_z)).union(grip_pads())
    back = shell.cut(box(-99, 99, 0, 99, -99, 99))
    front = shell.cut(box(-99, 99, -99, 0, -99, 99))
    out = {"back_shell": (back, GRAPHITE), "front_shell": (front, GRAPHITE)}
    out.update(fascia_parts(25.0, -40.0, 40.0, 6.0, led=(-12, 26), button=(9, 26)))
    out["screws"] = (screws([(-18, 38), (18, 38), (-18, -38), (18, -38)], y_back), ZINC)
    out.update(parts)
    out.update(rated_hardware())
    return out, {"name": "A  Precision", "attach": "rated DIN 580 M12 eye bolts"}


def concept_b():
    """Technical: faceted tapered body, blue seam line, custom machined attachments."""
    hw = CELL_W / 2 + GAP + WALL
    zt, zb, z_up, z_dn = 41.5, -41.5, 52.0, -56.0
    outline = [(-15, z_dn), (15, z_dn), (hw, zb), (hw, zt), (19, z_up), (-19, z_up), (-hw, zt), (-hw, zb)]
    body = prism(outline, Y_BACK, Y_FRONT).edges("|Y").fillet(3.0)
    body = soften(body, ">Y", (3.0, 2.0, 1.5))
    body = soften(body, "<Y", (2.0, 1.5, 1.0))
    cavity = cell_cavity()
    bore_r = 11.0 + GAP
    cavity = cavity.union(zcyl(bore_r, 36, 70)).union(zcyl(bore_r, -70, -36))
    bay_pts = rect(25.0, -40.0, 40.0)
    bay = prism(bay_pts, Y_BAY, Y_FRONT + 1).edges("|Y").chamfer(4.0)
    parts, usb_z = electronics(z_top=37.0)
    shell = body.cut(cavity).cut(bay).cut(usb_port(hw, usb_z)).union(grip_pads())
    # One restrained accent: a thin blue strip in a groove along the right-hand seam.
    grow = prism([(x * 1.012, z * 1.008) for x, z in outline], -0.5, 0.5).edges("|Y").fillet(3.0)
    inner = (cq.Workplane("XY").polyline(outline).close().offset2D(-1.0).extrude(3.0)
             .rotate((0, 0, 0), (1, 0, 0), 90).translate((0, 1.5, 0)))
    line = grow.cut(inner).intersect(box(0, 99, -0.5, 0.5, -8, 99)).cut(usb_port(hw, usb_z))
    back = shell.cut(box(-99, 99, 0, 99, -99, 99)).cut(line)
    front = shell.cut(box(-99, 99, -99, 0, -99, 99)).cut(line)
    fas = prism(bay_pts, Y_FRONT - 2.0, Y_FRONT - 0.6).edges("|Y").chamfer(4.0)
    f = fascia_parts(25.0, -40.0, 40.0, 4.0, led=(-12, 26), button=(9, 26))
    hole = ycyl(1.3, Y_FRONT - 3, Y_FRONT, -12, 26).union(ycyl(5.2, Y_FRONT - 3, Y_FRONT, 9, 26))
    f["fascia"] = (fas.cut(hole), FASCIA)
    out = {"back_shell": (back, GRAPHITE), "front_shell": (front, GRAPHITE), "accent": (line, BLUE)}
    out.update(f)
    out["screws"] = (screws([(-20, 44), (20, 44), (-17, -46), (17, -46)], Y_BACK), ZINC)
    out.update(parts)
    out["eye_top"] = (lug(True, 9.0, 26.0, 34.0, 9.0), MACHINED)
    out["eye_bottom"] = (lug(False, 13.0, 18.0, 16.0, 7.0), MACHINED)
    out["nut_top"] = (nut(True), ZINC)
    out["nut_bottom"] = (nut(False), ZINC)
    out["cell"] = (load_cell(), STEEL)
    return out, {"name": "B  Technical", "attach": "CUSTOM machined lugs - not rated"}


def concept_c():
    """Ultralight: electronics pod on the cell's front face only; the steel cell stays visible."""
    hw = CELL_W / 2
    z0, z1 = -CELL_H / 2, CELL_H / 2 + 2.5
    pod = prism(rect(hw, z0, z1), Y_FLOOR, Y_FRONT).edges("|Y").fillet(6.0)
    pod = soften(pod, ">Y", (5.0, 3.5, 2.0))
    bay = prism(rect(hw - 2.0, z0 + 2.0, z1 - 2.0), Y_BAY, Y_FRONT + 1).edges("|Y").fillet(4.0)
    parts, usb_z = electronics(z_top=z1 - 2.2, batt_gap=1.0)
    pod = pod.cut(bay).cut(usb_port(hw, usb_z))
    cheeks = cq.Workplane("XY")
    for s in (1, -1):
        x0, x1 = sorted((s * hw, s * (hw + 2.6)))
        cheeks = cheeks.union(box(x0, x1, -CELL_T / 2 - 2.6, Y_FLOOR + 0.5, PAD_Z0, PAD_Z1))
    pod = pod.union(cheeks).union(grip_pads(back=False, sides=False))
    strap = box(-hw - 2.6, hw + 2.6, -CELL_T / 2 - 2.6, -CELL_T / 2, PAD_Z0, PAD_Z1)
    strap = strap.cut(box(-hw - 3, -hw, -CELL_T / 2 - 3, -CELL_T / 2 + 0.01, PAD_Z0 - 1, PAD_Z1 + 1))
    strap = strap.cut(box(hw, hw + 3, -CELL_T / 2 - 3, -CELL_T / 2 + 0.01, PAD_Z0 - 1, PAD_Z1 + 1))
    strap = box(-hw - 2.6, hw + 2.6, -CELL_T / 2 - 2.6, -CELL_T / 2, PAD_Z0, PAD_Z1)
    pod = pod.cut(strap)
    out = {"front_shell": (pod, GRAPHITE), "back_shell": (strap.edges("|Y").fillet(1.0), GRAPHITE)}
    out.update(fascia_parts(hw - 2.0, z0 + 2.0, z1 - 2.0, 4.0, led=(-12, 26), button=(9, 26)))
    out["screws"] = (screws([(-hw - 1.3, 27.5), (hw + 1.3, 27.5), (-hw - 1.3, 34.5), (hw + 1.3, 34.5)],
                            -CELL_T / 2 - 2.6), ZINC)
    out.update(parts)
    out.update(rated_hardware())
    return out, {"name": "C  Ultralight", "attach": "rated DIN 580 M12 eye bolts"}


# ----------------------------------------------------------------------------
PLASTIC = ("back_shell", "front_shell", "fascia", "accent", "button", "light")
MOVING = ("cell", "nut_bottom", "eye_bottom")
EXPLODE = {"front_shell": (0, 38, 0), "fascia": (0, 62, 0), "light": (0, 62, 0), "button": (0, 62, 0),
           "logo": (0, 62, 0), "accent": (0, 0, 0), "pcb": (0, 20, 0), "module": (0, 20, 0), "usb": (0, 20, 0),
           "terminal": (0, 20, 0), "battery": (0, 20, 0), "back_shell": (0, -34, 0), "screws": (0, -58, 0),
           "eye_top": (0, 0, 16), "nut_top": (0, 0, 6), "eye_bottom": (0, 0, -16), "nut_bottom": (0, 0, -6)}


def solid_of(wp: cq.Workplane) -> cq.Shape:
    return cq.Compound.makeCompound([v for v in wp.vals() if isinstance(v, cq.Shape)])


def check(parts) -> dict:
    """CAD-only checks: interference volumes and the gap at the floating (lower) end."""
    res = {"interference_mm3": 0.0, "min_gap_lower_mm": 1e9}
    hard = [k for k in parts if k in ("cell", "nut_top", "nut_bottom", "eye_top", "eye_bottom", "pcb", "module",
                                      "usb", "terminal", "battery")]
    lower = box(-99, 99, -99, 99, -150, 14)
    for name in ("back_shell", "front_shell", "fascia"):
        if name not in parts:
            continue
        shell = parts[name][0]
        for h in hard:
            common = shell.intersect(parts[h][0])
            vol = sum(s.Volume() for s in common.vals() if isinstance(s, cq.Shape))
            if h == "usb":
                continue  # the connector sits in its own opening by design
            res["interference_mm3"] += vol
        for m in MOVING:
            moving = parts[m][0].intersect(lower)
            vals = [v for v in moving.vals() if isinstance(v, cq.Shape)]
            for mv in vals:
                for ss in solid_of(shell).Solids():
                    try:
                        d = ss.distance(mv)
                    except Exception:
                        res["gap_failures"] = res.get("gap_failures", 0) + 1
                        continue
                    res["min_gap_lower_mm"] = min(res["min_gap_lower_mm"], d)
    vol = lambda keys: sum(solid_of(parts[k][0]).Volume() for k in keys if k in parts)  # noqa: E731
    res["plastic_g"] = vol(PLASTIC) * PA12_DENSITY
    res["attach_g"] = vol(("eye_top", "eye_bottom", "nut_top", "nut_bottom")) * STEEL_DENSITY
    res["cell_g"] = vol(("cell",)) * STEEL_DENSITY
    bb = solid_of(cq.Workplane("XY").add([solid_of(parts[k][0]) for k in PLASTIC if k in parts])).BoundingBox()
    res["shell_xyz"] = (bb.xlen, bb.ylen, bb.zlen)
    allbb = solid_of(cq.Workplane("XY").add([solid_of(v[0]) for v in parts.values()])).BoundingBox()
    res["overall_len"] = allbb.zlen
    return res


def studio_environment():
    import numpy as np
    import vtk
    from vtk.util import numpy_support

    w, h = 512, 256
    img = np.full((h, w, 3), 0.22, dtype=np.float32)
    img[: h // 2] += np.linspace(0.55, 0.0, h // 2)[:, None, None]
    img[20:70, 60:200] = 3.2          # key softbox
    img[30:80, 300:380] = 1.6         # fill
    img[90:120, 430:500] = 2.2        # rim
    data = vtk.vtkImageData()
    data.SetDimensions(w, h, 1)
    arr = numpy_support.numpy_to_vtk(img[::-1].reshape(-1, 3), deep=True)
    arr.SetNumberOfComponents(3)
    data.GetPointData().SetScalars(arr)
    tex = vtk.vtkTexture()
    tex.SetInputData(data)
    tex.SetColorModeToDirectScalars()
    tex.MipmapOn()
    tex.InterpolateOn()
    return tex


def render(parts, path, view: str, explode: bool = False, scale: float = 112.0, size=(760, 1240)) -> None:
    import vtk

    ren = vtk.vtkRenderer()
    ren.SetBackground(0.93, 0.935, 0.94)
    for name, (wp, colour) in parts.items():
        shape = solid_of(wp)
        if explode and name in EXPLODE:
            shape = shape.translate(cq.Vector(*EXPLODE[name]))
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(shape.toVtkPolyData(0.03, 0.15))
        normals.SetFeatureAngle(35)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(normals.GetOutputPort())
        mapper.ScalarVisibilityOff()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetInterpolationToPBR()
        prop.SetColor(*colour)
        metal = name in ("cell", "eye_top", "eye_bottom", "nut_top", "nut_bottom", "usb", "screws", "module")
        prop.SetMetallic(0.95 if metal else 0.0)
        prop.SetRoughness(0.32 if metal else (0.35 if name in ("light", "accent") else 0.62))
        if name in ("light", "accent"):
            prop.SetEmissiveFactor(1.0, 1.0, 1.0)
            prop.SetAmbient(0.6)
        ren.AddActor(actor)

    ren.SetEnvironmentTexture(studio_environment(), False)
    ren.UseImageBasedLightingOn()
    ren.RemoveAllLights()
    key = vtk.vtkLight()
    key.SetPosition(250, 420, 380)
    key.SetIntensity(1.6)
    ren.AddLight(key)
    back = vtk.vtkLight()
    back.SetPosition(-250, -420, 200)
    back.SetIntensity(1.1)
    ren.AddLight(back)
    if hasattr(ren, "SetUseSSAO"):
        ren.SetUseSSAO(True)
        ren.SetSSAORadius(6.0)
        ren.SetSSAOBias(0.5)
        ren.SetSSAOKernelSize(128)
    ren.SetUseFXAA(True)

    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetMultiSamples(0)
    win.AddRenderer(ren)
    win.SetSize(*size)
    cam = ren.GetActiveCamera()
    pos = {"front": (0, 800, 0), "rear": (0, -800, 0), "side": (800, 0, 0),
           "three_quarter": (420, 620, 210), "exploded": (560, 470, 200)}[view]
    cam.SetFocalPoint(0, 4.5 if view != "exploded" else 2, 0)
    cam.SetPosition(*pos)
    cam.SetViewUp(0, 0, 1)
    cam.ParallelProjectionOn()
    cam.SetParallelScale(scale if view != "exploded" else scale * 1.12)
    ren.ResetCameraClippingRange()
    win.Render()
    grab = vtk.vtkWindowToImageFilter()
    grab.SetInput(win)
    grab.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(path))
    writer.SetInputConnection(grab.GetOutputPort())
    writer.Write()


VIEWS = ("front", "rear", "side", "three_quarter", "exploded")


def sheet(folder: pathlib.Path, key: str, title: str, lines: list[str]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    imgs = [Image.open(folder / f"concept-{key}-{v}.png") for v in VIEWS]
    w, h = imgs[0].size
    head, foot = 150, 60
    out = Image.new("RGB", (w * len(imgs), h + head + foot), (237, 238, 240))
    try:
        big = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 54)
        small = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 27)
    except OSError:
        big = small = ImageFont.load_default()
    d = ImageDraw.Draw(out)
    d.text((40, 22), f"FENRIR  concept {title}", fill=(25, 28, 34), font=big)
    d.text((40, 96), "   |   ".join(lines), fill=(70, 75, 85), font=small)
    for i, (im, v) in enumerate(zip(imgs, VIEWS)):
        out.paste(im, (i * w, head))
        d.text((i * w + 40, head + h + 12), v.replace("_", " ") + ("  (parts moved apart)" if v == "exploded" else ""),
               fill=(70, 75, 85), font=small)
    d.text((out.size[0] - 760, 30), "CAD concept render, same scale in every view.\nNot a photograph. Not released for manufacture.",
           fill=(120, 60, 40), font=small)
    out.save(folder / f"concept-{key}-sheet.png")


def main() -> None:
    root = pathlib.Path(__file__).resolve().parents[1]
    folder = root / "drawings" / "concepts"
    out = root / "cad" / "out"
    folder.mkdir(parents=True, exist_ok=True)
    out.mkdir(exist_ok=True)
    report = []
    for key, fn in (("a", concept_a), ("b", concept_b), ("c", concept_c)):
        parts, info = fn()
        print(f"{info['name']}: geometry built", flush=True)
        res = check(parts)
        print(f"{info['name']}: checks done", flush=True)
        for v in VIEWS:
            render(parts, folder / f"concept-{key}-{v}.png", v, explode=(v == "exploded"))
        x, y, z = res["shell_xyz"]
        sheet(folder, key, info["name"],
              [f"shell {x:.0f} x {y:.0f} x {z:.0f} mm", f"length over attachments {res['overall_len']:.0f} mm",
               f"printed parts {res['plastic_g']:.0f} g (estimate)", info["attach"]])
        asm = cq.Assembly(name=f"fenrir_concept_{key}")
        for name, (wp, colour) in parts.items():
            asm.add(wp, name=name, color=cq.Color(*colour))
        asm.export(str(out / f"fenrir-concept-{key}.step"))
        report.append((info["name"], info["attach"], res))
    for name, attach, r in report:
        x, y, z = r["shell_xyz"]
        print(f"{name}: shell {x:.1f} x {y:.1f} x {z:.1f} | overall {r['overall_len']:.1f} | plastic {r['plastic_g']:.1f} g"
              f" | attachments {r['attach_g']:.0f} g | cell {r['cell_g']:.0f} g"
              f" | interference {r['interference_mm3']:.2f} mm3 | min gap lower end {r['min_gap_lower_mm']:.2f} mm"
              f" | gap checks failed {r.get('gap_failures', 0)}"
              f" | {attach}")


if __name__ == "__main__":
    main()
