"""Project footprint library (hardware/USBAudioBridge.pretty).

PMOD_Peripheral_2x06_P2.54mm_Horizontal
    Right-angle 2x6 male header with Digilent *peripheral* pin numbering
    (PMOD Interface Spec 1.2.0, Fig. 2).  Derived from KiCad's
    PinHeader_2x06_P2.54mm_Horizontal (pins exit towards +x):
      * column x=0 (farther from the board edge, upper mating row) = pins 1-6
      * column x=2.54 (nearer the edge, lower mating row)         = pins 7-12
      * pin 1 / pin 7 at y=12.7, pin 6 / pin 12 at y=0, so that after a
        270 degree rotation (pins pointing south, towards the host) pin 1 is
        on the west end, matching the Arty A7's host ports.
    The board edge belongs 3.81 mm beyond the column nearest the edge
    (x=6.35); a Dwgs.User line marks it.
"""

import copy
import os

from sexpr import QStr, dumps, find, find_all, parse

SRC = ("/usr/share/kicad/footprints/Connector_PinHeader_2.54mm.pretty/"
       "PinHeader_2x06_P2.54mm_Horizontal.kicad_mod")
PMOD_NAME = "PMOD_Peripheral_2x06_P2.54mm_Horizontal"
PMOD_EDGE_X = 6.35


def _num_for(x, y):
    col = 0 if abs(x) < 0.01 else 1
    row = round(y / 2.54)  # 0..5 from the top
    return (6 - row) + 6 * col


def pmod_footprint():
    fp = parse(open(SRC).read())
    fp[1] = QStr(PMOD_NAME)
    out = [fp[0], fp[1]]
    for item in fp[2:]:
        if isinstance(item, list) and item[0] == "pad":
            at = find(item, "at")
            n = _num_for(float(at[1]), float(at[2]))
            item = copy.deepcopy(item)
            item[1] = QStr(str(n))
            item[3] = "rect" if n == 1 else "circle"
            if n != 1:
                # KiCad's pad 1 carries a custom shape/roundrect params; others are plain
                item[:] = [x for x in item if not (isinstance(x, list) and x[0] in
                                                     ("roundrect_rratio",))]
        elif isinstance(item, list) and item[0] == "fp_line" and find(item, "layer")[1] == "F.SilkS":
            s, e = find(item, "start"), find(item, "end")
            # drop KiCad's pin-1 corner marker at the top-left
            if max(float(s[2]), float(e[2])) <= 0 and min(float(s[1]), float(e[1])) <= -1.0:
                continue
            # keep silkscreen on the board: clip at the edge, minus edge clearance
            lim = PMOD_EDGE_X - 0.35
            x1, x2 = float(s[1]), float(e[1])
            if min(x1, x2) >= lim:
                continue
            if max(x1, x2) > lim:
                item = copy.deepcopy(item)
                s, e = find(item, "start"), find(item, "end")
                y1, y2 = float(s[2]), float(e[2])
                k = (lim - x1) / (x2 - x1)
                yc = round(y1 + k * (y2 - y1), 4)
                if x1 > lim:
                    s[1], s[2] = lim, yc
                else:
                    e[1], e[2] = lim, yc
        elif isinstance(item, list) and item[0] == "fp_rect" and find(item, "layer")[1] == "F.SilkS":
            s, e = find(item, "start"), find(item, "end")
            lim = PMOD_EDGE_X - 0.35
            if min(float(s[1]), float(e[1])) >= lim:
                continue
            item = copy.deepcopy(item)
            for corner in (find(item, "start"), find(item, "end")):
                corner[1] = min(float(corner[1]), lim)
        elif isinstance(item, list) and item[0] == "property" and item[1] == "Description":
            item = copy.deepcopy(item)
            item[2] = QStr("PMOD peripheral (module side) 2x6 right-angle male header, "
                           "Digilent pin numbering: pins 1-6 upper row, 7-12 lower row")
        elif isinstance(item, list) and item[0] == "descr":
            item = ["descr", QStr("PMOD peripheral 2x6 right-angle male header, Digilent numbering")]
        out.append(item)
    stroke = ["stroke", ["width", 0.12], ["type", "solid"]]
    # pin-1 marker beside pin 1 (bottom of the x=0 column)
    out.append(["fp_line", ["start", -1.33, 12.7], ["end", -1.33, 14.03], stroke,
                ["layer", QStr("F.SilkS")]])
    out.append(["fp_line", ["start", -1.33, 14.03], ["end", 0, 14.03], stroke,
                ["layer", QStr("F.SilkS")]])
    out.append(["fp_line", ["start", PMOD_EDGE_X, -2.0], ["end", PMOD_EDGE_X, 14.7],
                ["stroke", ["width", 0.1], ["type", "dash"]], ["layer", QStr("Dwgs.User")]])
    out.append(["fp_text", "user", QStr("PCB Edge"), ["at", PMOD_EDGE_X + 0.8, 6.35, 90],
                ["layer", QStr("Dwgs.User")],
                ["effects", ["font", ["size", 0.8, 0.8], ["thickness", 0.1]]]])
    return out


def write_library(pretty_dir):
    os.makedirs(pretty_dir, exist_ok=True)
    with open(os.path.join(pretty_dir, PMOD_NAME + ".kicad_mod"), "w") as f:
        f.write(dumps(pmod_footprint()) + "\n")
