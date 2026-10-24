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


FTSH_NAME = "Samtec_FTSH-105-01-L-DV-K"
FTSH_ZIP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "datasheets",
                        "FTSH-105-01-L-DV-K.zip")
FTSH_STEP = "FTSH-105-01-L-DV-K.stp"


def ftsh_footprint():
    """Samtec FTSH-105-01-L-DV-K, 2x5 1.27 mm SMD header with keying shroud
    (ARM Cortex 10-pin debug).  Pad geometry from Samtec's recommended land
    pattern: 0.7366 x 2.794 mm pads, rows at +/-2.032 mm; odd pins on the +y
    row with pin 1 at x = -2.54."""
    fx = ["effects", ["font", ["size", 1.0, 1.0], ["thickness", 0.15]]]
    items = ["footprint", QStr(FTSH_NAME), ["version", "20241229"],
             ["generator", QStr("usbaudiobridge")], ["layer", QStr("F.Cu")],
             ["descr", QStr("Samtec FTSH-105-01-L-DV-K 2x5 1.27 mm SMD header, keying shroud")],
             ["tags", QStr("Cortex debug SWD 10-pin keyed")],
             ["property", QStr("Reference"), QStr("REF**"), ["at", 0, -4.6, 0],
              ["layer", QStr("F.SilkS")], fx],
             ["property", QStr("Value"), QStr(FTSH_NAME), ["at", 0, 4.6, 0],
              ["layer", QStr("F.Fab")], fx],
             ["attr", "smd"]]
    for i in range(5):
        x = round(-2.54 + i * 1.27, 3)
        for num, y in ((2 * i + 1, 2.032), (2 * i + 2, -2.032)):
            items.append(["pad", QStr(str(num)), "smd", "rect", ["at", x, y],
                          ["size", 0.7366, 2.794],
                          ["layers", QStr("F.Cu"), QStr("F.Mask"), QStr("F.Paste")]])
    fab = [(-3.175, -1.7145), (-2.54, -1.7145), (-2.54, -2.54), (2.54, -2.54), (2.54, -1.7145),
           (3.175, -1.7145), (3.175, 1.7145), (2.54, 1.7145), (2.54, 2.54), (-2.54, 2.54),
           (-2.54, 1.7145), (-3.175, 1.7145)]
    for a, b in zip(fab, fab[1:] + fab[:1]):
        items.append(["fp_line", ["start", *a], ["end", *b],
                      ["stroke", ["width", 0.1], ["type", "solid"]], ["layer", QStr("F.Fab")]])
    for a, b in (((-3.425, -3.679), (3.425, -3.679)), ((3.425, -3.679), (3.425, 3.679)),
                 ((3.425, 3.679), (-3.425, 3.679)), ((-3.425, 3.679), (-3.425, -3.679))):
        items.append(["fp_line", ["start", *a], ["end", *b],
                      ["stroke", ["width", 0.05], ["type", "solid"]], ["layer", QStr("F.CrtYd")]])
    for x in (-3.255, 3.255):     # shroud end walls
        items.append(["fp_line", ["start", x, -1.7145], ["end", x, 1.7145],
                      ["stroke", ["width", 0.12], ["type", "solid"]], ["layer", QStr("F.SilkS")]])
    items.append(["fp_circle", ["center", -2.54, 3.9], ["end", -2.39, 3.9],
                  ["stroke", ["width", 0.3], ["type", "solid"]], ["fill", "yes"],
                  ["layer", QStr("F.SilkS")]])
    items.append(["model", QStr("${KIPRJMOD}/3rdparty/" + FTSH_STEP),
                  ["offset", ["xyz", 0, 0, 0]], ["scale", ["xyz", 1, 1, 1]],
                  ["rotate", ["xyz", 0, 0, 0]]])
    return items


def extract_models(hw_dir):
    """Samtec's 3D model may not be redistributed: unpack it from the owner's
    download into the gitignored hardware/3rdparty folder."""
    import zipfile
    dest = os.path.join(hw_dir, "3rdparty")
    if os.path.exists(FTSH_ZIP):
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(FTSH_ZIP) as z:
            with open(os.path.join(dest, FTSH_STEP), "wb") as f:
                f.write(z.read(FTSH_STEP))


def write_library(pretty_dir):
    os.makedirs(pretty_dir, exist_ok=True)
    with open(os.path.join(pretty_dir, PMOD_NAME + ".kicad_mod"), "w") as f:
        f.write(dumps(pmod_footprint()) + "\n")
    with open(os.path.join(pretty_dir, FTSH_NAME + ".kicad_mod"), "w") as f:
        f.write(dumps(ftsh_footprint()) + "\n")
    extract_models(os.path.dirname(os.path.abspath(pretty_dir)))
