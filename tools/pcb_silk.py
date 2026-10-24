"""Silkscreen clean-up: keep reference designators where they help a human
(connectors, ICs, switches, LEDs, crystals, inductor, fuse, test points) and
move the rest to the fab layer; then nudge the kept ones to free spots."""

import pcbnew

import design
import pcb_layout as L
from pcb_route import rel

KEEP_PREFIX = ("J", "U", "SW", "D", "Y", "X", "L", "F", "TP", "Q", "JP")
TEXT_H = 0.8
TEXT_T = 0.12


def _box(item, grow=0.0):
    bb = item.GetBoundingBox()
    x1, y1 = rel(bb.GetOrigin())
    x2, y2 = rel(bb.GetEnd())
    return (x1 - grow, y1 - grow, x2 + grow, y2 + grow)


def _courtyard_box(fp, side):
    cy = fp.GetCourtyard(pcbnew.B_CrtYd if side == "B" else pcbnew.F_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
    x1, y1 = rel(bb.GetOrigin())
    x2, y2 = rel(bb.GetEnd())
    return (x1, y1, x2, y2)


def _overlap(a, b):
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def tidy(board):
    keep, obstacles = [], {}
    for fp in board.GetFootprints():
        side = "B" if fp.IsFlipped() else "F"
        silk = pcbnew.B_SilkS if side == "B" else pcbnew.F_SilkS
        fab = pcbnew.B_Fab if side == "B" else pcbnew.F_Fab
        ref = fp.Reference()
        ref.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(TEXT_H), pcbnew.FromMM(TEXT_H)))
        ref.SetTextThickness(pcbnew.FromMM(TEXT_T))
        name = fp.GetReference()
        wanted = name.startswith(KEEP_PREFIX) and not name.startswith("H")
        if not wanted or fp.IsExcludedFromBOM() and not name.startswith(("TP", "JP")):
            ref.SetLayer(fab)
        else:
            ref.SetLayer(silk)
            keep.append(fp)
        for p in fp.Pads():
            for s in ("F", "B"):
                lay = pcbnew.F_Cu if s == "F" else pcbnew.B_Cu
                if p.IsOnLayer(lay):
                    obstacles.setdefault(s, []).append(_box(p, 0.15))
        for g in fp.GraphicalItems():
            if g.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                s = "F" if g.GetLayer() == pcbnew.F_SilkS else "B"
                obstacles.setdefault(s, []).append(_box(g, 0.1))
    # tracks and vias are under solder mask (tented): silkscreen may cross them

    # place kept references at the first clear spot around their footprint
    for fp in sorted(keep, key=lambda f: f.GetReference()):
        s = "B" if fp.IsFlipped() else "F"
        ref = fp.Reference()
        ref.SetTextAngle(pcbnew.EDA_ANGLE(0, pcbnew.DEGREES_T))
        fb = _courtyard_box(fp, s)
        cx, cy = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
        w = len(fp.GetReference()) * TEXT_H * 0.75 + 0.3
        h = TEXT_H + 0.3
        cands = [(cx, fb[1] - h / 2 - 0.15), (cx, fb[3] + h / 2 + 0.15),
                 (fb[0] - w / 2 - 0.15, cy), (fb[2] + w / 2 + 0.15, cy),
                 (fb[0] - w / 2, fb[1] - h / 2), (fb[2] + w / 2, fb[1] - h / 2),
                 (fb[0] - w / 2, fb[3] + h / 2), (fb[2] + w / 2, fb[3] + h / 2), (cx, cy)]
        placed = False
        for x, y in cands:
            box = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
            if not (0.4 < box[0] and box[2] < L.W - 0.4 and 0.4 < box[1] and box[3] < L.H - 0.4):
                continue
            if any(_overlap(box, o) for o in obstacles.get(s, [])):
                continue
            ref.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(L.ORIGIN[0] + x),
                                            pcbnew.FromMM(L.ORIGIN[1] + y)))
            obstacles.setdefault(s, []).append(box)
            placed = True
            break
        if not placed:
            ref.SetLayer(pcbnew.B_Fab if s == "B" else pcbnew.F_Fab)
            print(f"  silk: no room for {fp.GetReference()}, moved to fab")


# (text, layer, size, candidate centres in board mm); first free spot wins
LABELS = [
    # (text, size, [(side, x, y[, angle]), ...]) in board mm; the first free spot wins.
    # Bottom text is read from below, where west and east swap: list it east-to-west.
    (f"{design.TITLE} {design.REV}", 0.9,
     [("B", 21.59, 47.0), ("F", 1.3, 34.0, 90), ("F", 41.9, 42.0, 90), ("B", 41.9, 30.0, 90),
      ("B", 1.3, 34.0, 90)]),
    ({"F": "JB: I2S (Pmod I2S2)   JC: SPI+GPIO", "B": "JC: SPI+GPIO   JB: I2S (Pmod I2S2)"}, 0.8,
     [("B", 21.59, 49.2), ("B", 21.59, 51.2), ("B", 21.59, 44.6)]),
    ("Hold BOOT + tap RESET = USB serial downloader", 0.8,
     [("B", 21.59, 51.2), ("B", 21.59, 53.2), ("B", 21.59, 37.0)]),
    ({"F": "TX RX GND", "B": "GND RX TX"}, 0.8, [("F", 31.3, 5.4), ("B", 31.3, 4.9),
                                                ("B", 31.3, 5.8)]),
    ("I2S", 0.8, [("F", 8.0, 49.6), ("F", 8.0, 47.4)]),
    ("SPI+GPIO", 0.8, [("F", 31.0, 49.6), ("F", 31.0, 47.4), ("F", 37.4, 47.4)]),
]


def title_block(board):
    tb = board.GetTitleBlock()
    tb.SetTitle(design.TITLE)
    tb.SetRevision(design.REV)
    tb.SetDate(design.DATE)


def labels(board):
    title_block(board)
    obstacles = {}
    for fp in board.GetFootprints():
        for item in list(fp.GraphicalItems()) + [fp.Reference()]:
            lay = item.GetLayer()
            if lay in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                obstacles.setdefault("F" if lay == pcbnew.F_SilkS else "B", []).append(_box(item, 0.15))
        for p in fp.Pads():
            for s_, lay in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu)):
                if p.IsOnLayer(lay):
                    obstacles.setdefault(s_, []).append(_box(p, 0.15))
    for texts, size, cands in LABELS:
        for side, x, y, *ang in cands:
            text = texts[side] if isinstance(texts, dict) else texts
            w = len(text) * size * 0.95 + 0.4   # KiCad stroke font runs ~0.9 em per glyph
            h = size + 0.4
            if ang and ang[0] in (90, 270):
                w, h = h, w
            box = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
            if not (0.4 < box[0] and box[2] < L.W - 0.4 and 0.4 < box[1] and box[3] < L.H - 0.4):
                continue
            if any(_overlap(box, o) for o in obstacles.get(side, [])):
                continue
            t = pcbnew.PCB_TEXT(board)
            t.SetText(text)
            t.SetLayer(pcbnew.F_SilkS if side == "F" else pcbnew.B_SilkS)
            t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
            t.SetTextThickness(pcbnew.FromMM(0.15))
            t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(L.ORIGIN[0] + x), pcbnew.FromMM(L.ORIGIN[1] + y)))
            if side == "B":
                t.SetMirrored(True)
            if ang:
                t.SetTextAngle(pcbnew.EDA_ANGLE(ang[0], pcbnew.DEGREES_T))
            board.Add(t)
            obstacles.setdefault(side, []).append(box)
            break
        else:
            print(f"  silk: no room for label {texts!r}")
