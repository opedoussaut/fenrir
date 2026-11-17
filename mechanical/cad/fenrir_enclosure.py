"""FENRIR enclosure - parametric CONCEPT model (rev A).

Status: concept geometry built from datasheet and product-page dimensions.
NOT released for printing: the dimensions marked VERIFY must be measured on
the received parts first (see mechanical/enclosure.md).

The shell never carries load. Steel path: eye bolt -> load cell -> eye bolt.
The shell grips the cell's upper block only and clears everything else, so it
cannot shunt force around the strain gauges.

Run:  python mechanical/cad/fenrir_enclosure.py
Writes renders to mechanical/drawings/ and STEP/STL to mechanical/cad/out/
(the out/ folder is git-ignored: generated files, not manufacturing data).

Axes: Z = load axis, X = cell width, Y = thickness (front of the device = +Y).
All dimensions in millimetres.
"""

from __future__ import annotations

import pathlib

import cadquery as cq

# --- Load cell, Phidgets FRC4165_0 (datasheet) ------------------------------
CELL_W = 50.8          # X
CELL_T = 19.0          # Y
CELL_H = 76.2          # Z
THREAD_D = 12.0        # M12 x 1.75
# VERIFY on the received cell: slot positions, cable exit position, thread depth.
CELL_SLOT_H = 4.0      # assumption, appearance only
CELL_SLOT_Z = 17.0     # assumption, appearance only
CELL_BORE_D = 22.0     # assumption, appearance only

# --- Eye bolt DIN 580 M12 and thin nut DIN 439 M12 (standard dimensions) ----
EYE_COLLAR_D = 28.0
EYE_COLLAR_H = 10.0    # VERIFY against the purchased bolt
EYE_RING_OD = 54.0
EYE_RING_ID = 30.0
EYE_HEIGHT = 53.0      # seat to top of ring
NUT_AF = 19.0
NUT_H = 6.0

# --- Electronics (product pages; VERIFY with a calliper) ---------------------
FEATHER = (50.8, 22.9, 1.6)      # Adafruit Feather outline
ADC_BRD = (25.4, 17.8, 1.6)      # Adafruit NAU7802 breakout, VERIFY
BATTERY = (36.0, 17.0, 7.8)      # 400 mAh LiPo, VERIFY

# --- Shell -------------------------------------------------------------------
WALL = 2.4
CLEAR = 1.5            # gap between shell and every moving part of the cell
MID_WALL = 1.6         # separates the cell chamber from the electronics bay
BAY_DEPTH = 10.5       # electronics bay, Y
CORNER_R = 12.0        # silhouette corner radius
EDGE_R = 3.5           # soft edge radius
BOLT_HOLE_D = 26.0     # clears the M12 nut (21.9 mm across corners)

SHELL_X = CELL_W + 2 * (CLEAR + WALL)
SHELL_Z = CELL_H + 2 * (CLEAR + WALL)
Y_BACK = -(CELL_T / 2 + CLEAR + WALL)
Y_MID = CELL_T / 2 + CLEAR
Y_FRONT = Y_MID + MID_WALL + BAY_DEPTH + WALL
SHELL_Y = Y_FRONT - Y_BACK
Y_C = (Y_FRONT + Y_BACK) / 2

BLACK = (0.10, 0.10, 0.11)
ORANGE = (0.95, 0.42, 0.10)
STEEL = (0.72, 0.74, 0.76)
ZINC = (0.80, 0.80, 0.78)
PCB = (0.07, 0.25, 0.20)
GREY = (0.55, 0.56, 0.58)


def rounded_block(x: float, y: float, z: float, r_sil: float, r_edge: float) -> cq.Workplane:
    wp = cq.Workplane("XY").box(x, y, z).edges("|Y").fillet(r_sil)
    return wp.edges().fillet(r_edge) if r_edge > 0 else wp


def load_cell() -> cq.Workplane:
    body = cq.Workplane("XY").box(CELL_W, CELL_T, CELL_H).edges("|Y").fillet(2.0)
    slot_len = CELL_W * 0.72
    for sign in (1, -1):
        slot = (cq.Workplane("XY").box(slot_len, CELL_T + 2, CELL_SLOT_H)
                .translate((sign * (CELL_W - slot_len) / 2, 0, sign * CELL_SLOT_Z)))
        body = body.cut(slot)
    bore = cq.Workplane("XZ").circle(CELL_BORE_D / 2).extrude(CELL_T + 2, both=True)
    return body.cut(bore)


def eye_bolt(top: bool) -> cq.Workplane:
    """Simplified DIN 580 eye bolt with its seat at the nut's outer face."""
    seat = CELL_H / 2 + NUT_H
    ring_r = (EYE_RING_OD + EYE_RING_ID) / 4
    tube_r = (EYE_RING_OD - EYE_RING_ID) / 4
    ring_z = seat + EYE_HEIGHT - EYE_RING_OD / 2
    collar = cq.Workplane("XY").workplane(offset=seat).circle(EYE_COLLAR_D / 2).extrude(EYE_COLLAR_H)
    neck = (cq.Workplane("XY").workplane(offset=seat + EYE_COLLAR_H)
            .circle(9).extrude(ring_z - ring_r - seat - EYE_COLLAR_H + tube_r))
    ring = cq.Workplane("XY").add(
        cq.Solid.makeTorus(ring_r, tube_r, cq.Vector(0, 0, ring_z), cq.Vector(0, 1, 0)))
    stud = cq.Workplane("XY").workplane(offset=CELL_H / 2 - 18).circle(THREAD_D / 2).extrude(18 + NUT_H)
    part = collar.union(neck).union(ring).union(stud)
    return part if top else part.mirror("XY")


def nut(top: bool) -> cq.Workplane:
    n = (cq.Workplane("XY").workplane(offset=CELL_H / 2).polygon(6, NUT_AF / 0.866)
         .circle(THREAD_D / 2).extrude(NUT_H))
    return n if top else n.mirror("XY")


def shell_parts() -> dict[str, cq.Workplane]:
    outer = rounded_block(SHELL_X, SHELL_Y, SHELL_Z, CORNER_R, EDGE_R).translate((0, Y_C, 0))
    inner = rounded_block(SHELL_X - 2 * WALL, SHELL_Y - 2 * WALL, SHELL_Z - 2 * WALL,
                          CORNER_R - WALL, 1.0).translate((0, Y_C, 0))
    mid = (cq.Workplane("XY").box(SHELL_X - WALL, MID_WALL, SHELL_Z - WALL)
           .translate((0, Y_MID + MID_WALL / 2, 0)))
    # Upper grip pads: the only place the shell touches the cell (upper block).
    pad_z = CELL_H / 2 - 7
    pads = cq.Workplane("XY")
    for sx in (1, -1):
        pads = pads.union(cq.Workplane("XY").box(CLEAR, CELL_T, 12)
                          .translate((sx * (CELL_W / 2 + CLEAR / 2), 0, pad_z)))
    body = outer.cut(inner).union(mid.intersect(outer)).union(pads)

    holes = cq.Workplane("XY").circle(BOLT_HOLE_D / 2).extrude(SHELL_Z, both=True)
    body = body.cut(holes)

    # USB-C opening on the +X side, at the Feather's connector.
    bay_y = Y_MID + MID_WALL + 4.2
    feather_z = CELL_H / 2 - 16
    usb = cq.Workplane("XY").box(WALL * 4, 7.0, 12.5).edges("|X").fillet(3.0)
    body = body.cut(usb.translate((SHELL_X / 2, bay_y, feather_z)))

    # Recessed front panel.
    panel = (cq.Workplane("XY").box(SHELL_X - 14, 1.0, SHELL_Z - 14).edges("|Y").fillet(7.0)
             .translate((0, Y_FRONT - 0.5 + 0.01, 0)))
    body = body.cut(panel)
    led = cq.Workplane("XZ").workplane(offset=-(Y_FRONT + 1)).center(15, feather_z).circle(1.6).extrude(WALL + 2)
    body = body.cut(led)

    # Orange accents: seam band and bolt collars. Cosmetic, same non-structural plastic.
    band_y0 = Y_MID + MID_WALL / 2 - 1.5
    big = rounded_block(SHELL_X + 1.2, SHELL_Y, SHELL_Z + 1.2, CORNER_R + 0.6, 0).translate((0, Y_C, 0))
    slab = cq.Workplane("XY").box(SHELL_X + 4, 3.0, SHELL_Z + 4).translate((0, band_y0 + 1.5, 0))
    band = big.intersect(slab).cut(inner).cut(holes)
    usb_band = cq.Workplane("XY").box(WALL * 6, 7.0, 12.5).translate((SHELL_X / 2, bay_y, feather_z))
    band = band.cut(usb_band)
    body = body.cut(slab.intersect(big).cut(inner))

    collars = cq.Workplane("XY")
    for sz in (1, -1):
        c = (cq.Workplane("XY").workplane(offset=sz * (SHELL_Z / 2 - 0.4))
             .circle(BOLT_HOLE_D / 2 + 4).circle(BOLT_HOLE_D / 2).extrude(sz * 1.6))
        collars = collars.union(c)

    logo = (cq.Workplane("XZ").workplane(offset=-(Y_FRONT - 1.0))
            .center(0, -CELL_H / 2 + 20).text("FENRIR", 8.5, -0.6, kind="bold").mirror("YZ"))
    light = cq.Workplane("XZ").workplane(offset=-(Y_FRONT - 1.0)).center(15, feather_z).circle(1.5).extrude(-0.5)

    return {"shell": body, "band": band, "collars": collars, "logo": logo, "light": light}


def electronics() -> dict[str, cq.Workplane]:
    y0 = Y_MID + MID_WALL + 2.5
    feather_z = CELL_H / 2 - 16
    feather = cq.Workplane("XY").box(FEATHER[0], FEATHER[2], FEATHER[1]).translate((0, y0, feather_z))
    usb = cq.Workplane("XY").box(7.5, 3.2, 9.0).translate((FEATHER[0] / 2 - 3.0, y0 + 2.4, feather_z))
    adc = cq.Workplane("XY").box(ADC_BRD[1], ADC_BRD[2], ADC_BRD[0]).translate((-13, y0, -10))
    batt = cq.Workplane("XY").box(BATTERY[1], BATTERY[2], BATTERY[0]).translate((11, y0 + 3.2, -12))
    return {"feather": feather, "usb": usb, "adc": adc, "battery": batt}


def build() -> dict[str, tuple[cq.Workplane, tuple[float, float, float]]]:
    parts: dict[str, tuple[cq.Workplane, tuple[float, float, float]]] = {}
    s = shell_parts()
    parts["shell"] = (s["shell"], BLACK)
    parts["band"] = (s["band"], ORANGE)
    parts["collars"] = (s["collars"], ORANGE)
    parts["logo"] = (s["logo"], ORANGE)
    parts["light"] = (s["light"], (0.9, 0.95, 1.0))
    parts["cell"] = (load_cell(), STEEL)
    for name, top in (("eye_top", True), ("eye_bottom", False)):
        parts[name] = (eye_bolt(top), ZINC)
    for name, top in (("nut_top", True), ("nut_bottom", False)):
        parts[name] = (nut(top), ZINC)
    e = electronics()
    parts["feather"] = (e["feather"], PCB)
    parts["usb"] = (e["usb"], GREY)
    parts["adc"] = (e["adc"], PCB)
    parts["battery"] = (e["battery"], GREY)
    return parts


def render(parts, path: pathlib.Path, position, mode: str = "full", size=(1500, 1800)) -> None:
    """mode: full | cover_off (front cover removed) | section (plastic cut at X = 0)."""
    import vtk

    ren = vtk.vtkRenderer()
    ren.SetBackground(0.96, 0.96, 0.95)
    plastic = {"shell", "band", "collars", "logo", "light"}
    for name, (wp, colour) in parts.items():
        shape = wp
        if mode == "cover_off" and name in plastic:
            if name in {"logo", "light"}:
                continue
            cutter = cq.Workplane("XY").box(200, 60, 200).translate((0, Y_MID + MID_WALL + 30 + 0.01, 0))
            shape = wp.cut(cutter)
        if mode == "section" and name in plastic:
            shape = wp.cut(cq.Workplane("XY").box(100, 200, 200).translate((50, 0, 0)))
        solids = shape.vals()
        if not solids:
            continue
        comp = cq.Compound.makeCompound([v for v in solids if isinstance(v, cq.Shape)])
        mapper = vtk.vtkPolyDataMapper()
        normals = vtk.vtkPolyDataNormals()
        normals.SetInputData(comp.toVtkPolyData(0.05, 0.2))
        normals.SetFeatureAngle(40)
        mapper.SetInputConnection(normals.GetOutputPort())
        mapper.ScalarVisibilityOff()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(*colour)
        metal = name in {"cell", "eye_top", "eye_bottom", "nut_top", "nut_bottom", "usb"}
        prop.SetInterpolationToPBR()
        prop.SetMetallic(0.45 if metal else 0.0)
        prop.SetRoughness(0.4 if metal else 0.75)
        ren.AddActor(actor)

    ren.UseImageBasedLightingOff()
    ren.RemoveAllLights()
    for pos, intensity in (((300, 400, 350), 1.5), ((-350, 250, 100), 0.7), ((0, 300, -400), 0.5),
                           ((300, -200, 100), 0.5)):
        light = vtk.vtkLight()
        light.SetPosition(*pos)
        light.SetFocalPoint(0, 0, 0)
        light.SetIntensity(intensity)
        ren.AddLight(light)
    ren.SetUseFXAA(True)

    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.SetMultiSamples(8)
    win.AddRenderer(ren)
    win.SetSize(*size)
    cam = ren.GetActiveCamera()
    cam.SetViewUp(0, 0, 1)
    cam.SetFocalPoint(0, Y_C, 0)
    cam.SetPosition(*position)
    cam.SetViewAngle(22)
    ren.ResetCamera()
    cam.Zoom(1.05)
    win.Render()
    grab = vtk.vtkWindowToImageFilter()
    grab.SetInput(win)
    grab.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(path))
    writer.SetInputConnection(grab.GetOutputPort())
    writer.Write()


def main() -> None:
    root = pathlib.Path(__file__).resolve().parents[1]
    drawings = root / "drawings"
    out = root / "cad" / "out"
    drawings.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    parts = build()

    render(parts, drawings / "enclosure-concept-front.png", (260, 520, 150))
    render(parts, drawings / "enclosure-concept-cover-off.png", (200, 560, 120), mode="cover_off")
    render(parts, drawings / "enclosure-concept-section.png", (560, 200, 110), mode="section")

    asm = cq.Assembly(name="fenrir_concept_revA")
    for name, (wp, colour) in parts.items():
        asm.add(wp, name=name, color=cq.Color(*colour))
    asm.save(str(out / "fenrir-enclosure-concept-revA.step"))
    cq.exporters.export(parts["shell"][0], str(out / "shell-concept-revA.stl"))

    eye_tip = CELL_H / 2 + NUT_H + EYE_HEIGHT
    print(f"shell envelope  X {SHELL_X:.1f}  Y {SHELL_Y:.1f}  Z {SHELL_Z:.1f} mm")
    print(f"overall length over eye bolts {2 * eye_tip:.1f} mm")
    print(f"shell volume {parts['shell'][0].val().Volume() / 1000:.1f} cm3")


if __name__ == "__main__":
    main()
