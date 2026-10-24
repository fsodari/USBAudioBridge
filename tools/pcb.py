"""Build hardware/USBAudioBridge.kicad_pcb from the schematic netlist.

Usage: python3 tools/pcb.py   (run tools/build.py first so the netlist exists)
       python3 tools/pcb.py --sync-fields   (copy values and schematic fields such as
                                            MPN/LCSC onto the existing, routed board)

The board is regenerated from scratch each time: outline, footprints (with
schematic links for DRC parity), nets, net classes, zones and the hand-routed
critical nets.  Placement lives in pcb_layout.py.
"""

import os
import sys

import pcbnew

import design
import pcb_layout as L
import pcb_copper
import pcb_rules
from sexpr import find, find_all, parse

HW = os.path.abspath(design.OUT)
PCB = os.path.join(HW, "USBAudioBridge.kicad_pcb")
NETLIST = os.path.join(HW, "build", "netlist.net")
SYS_FP = "/usr/share/kicad/footprints"


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    """Board-relative mm -> absolute KiCad VECTOR2I."""
    return pcbnew.VECTOR2I(mm(L.ORIGIN[0] + x), mm(L.ORIGIN[1] + y))


def read_netlist():
    root = parse(open(NETLIST).read())
    comps = {}
    for c in find_all(find(root, "components"), "comp"):
        ref = find(c, "ref")[1]
        fields = {}
        fl = find(c, "fields")
        for f in find_all(fl, "field") if fl else []:
            if len(f) > 2:
                fields[find(f, "name")[1]] = f[2]
        comps[ref] = {
            "fields": fields,
            "value": find(c, "value")[1],
            "footprint": find(c, "footprint")[1],
            "path": find(find(c, "sheetpath"), "tstamps")[1] + find(c, "tstamps")[1],
            "sheetname": next((find(p, "value")[1] for p in find_all(c, "property")
                               if find(p, "name")[1] == "Sheetname"), ""),
            "sheetfile": next((find(p, "value")[1] for p in find_all(c, "property")
                               if find(p, "name")[1] == "Sheetfile"), ""),
            "dnp": any(find(p, "name")[1] == "dnp" for p in find_all(c, "property")),
        }
    pads = {}
    for n in find_all(find(root, "nets"), "net"):
        name = find(n, "name")[1]
        for node in find_all(n, "node"):
            pads[(find(node, "ref")[1], find(node, "pin")[1])] = name
    return comps, pads


def load_footprint(fpid):
    lib, name = fpid.split(":")
    path = os.path.join(HW, lib + ".pretty") if lib == "USBAudioBridge" else \
        os.path.join(SYS_FP, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        sys.exit(f"cannot load footprint {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def copy_fields(fp, comp):
    """Mirror every schematic field (Datasheet, Description, MPN, LCSC, ...) for parity."""
    fp.SetValue(comp["value"])
    fp.SetDNP(comp["dnp"])
    for k, v in comp["fields"].items():
        if k == "Footprint":
            continue
        fp.SetField(k, v)
        f = fp.GetField(k)
        if f:
            f.SetVisible(False)


def sync_fields():
    """Update values and fields on the existing board without touching copper."""
    comps, _ = read_netlist()
    board = pcbnew.LoadBoard(PCB)
    seen = set()
    for fp in board.GetFootprints():
        c = comps.get(fp.GetReference())
        if c is None:
            sys.exit(f"{fp.GetReference()} is not in the netlist: rebuild with pcb.py")
        if c["footprint"] != fp.GetFPIDAsString():
            sys.exit(f"{fp.GetReference()}: footprint changed, rebuild with pcb.py")
        copy_fields(fp, c)
        seen.add(fp.GetReference())
    if set(comps) - seen:
        sys.exit("new parts in the netlist: rebuild with pcb.py")
    set_origins(board)
    pcbnew.SaveBoard(PCB, board)
    print("synced fields for", len(seen), "footprints")


def set_origins(board):
    """Drill/place origin at the lower-left board corner: fab outputs then use
    positive millimetre coordinates (Gerber, drill and placement agree)."""
    board.GetDesignSettings().SetAuxOrigin(pt(0, L.H))


def outline(board):
    corners = [(0, 0), (L.W, 0), (L.W, L.H), (0, L.H)]
    for (x1, y1), (x2, y2) in zip(corners, corners[1:] + corners[:1]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pt(x1, y1))
        s.SetEnd(pt(x2, y2))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)


def build():
    comps, pad_nets = read_netlist()
    parts = {p.ref: p for p in design.build().refs.values()}

    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(4)
    outline(board)
    set_origins(board)

    nets = {}
    for name in sorted(set(pad_nets.values())):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    placed = {}
    for ref, c in sorted(comps.items()):
        fp = load_footprint(c["footprint"])
        fp.SetReference(ref)
        fp.SetPath(pcbnew.KIID_PATH(c["path"]))
        fp.SetSheetname(c["sheetname"])
        fp.SetSheetfile(c["sheetfile"])
        part = parts[ref]
        copy_fields(fp, c)
        if not part.in_bom:
            fp.SetExcludedFromBOM(True)
            fp.SetExcludedFromPosFiles(True)
        for pad in fp.Pads():
            net = pad_nets.get((ref, pad.GetNumber()))
            if net:
                pad.SetNet(nets[net])
        board.Add(fp)
        placed[ref] = fp

    mcu = placed["U1"]
    mx, my, mr, *side = L.MCU
    mcu.SetPosition(pt(mx, my))
    if side == ["B"]:
        mcu.Flip(mcu.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    mcu.SetOrientationDegrees(mr)
    positions = dict(L.PLACEMENT)
    # decoupling caps are positioned by pcb_copper; park them off-board for now
    for i, ref in enumerate(sorted(L.DECOUPLING)):
        positions[ref] = (-20.0 - (i % 5) * 3, 10.0 + (i // 5) * 3, 0)

    missing = sorted(set(placed) - set(positions))
    if missing:
        print("unplaced:", ", ".join(missing))
    for ref, (x, y, r, *side) in positions.items():
        if ref == "U1":
            continue
        if ref not in placed:
            sys.exit(f"placement for unknown ref {ref}")
        fp = placed[ref]
        fp.SetPosition(pt(x, y))
        if side == ["B"]:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(r)
    return board


def main():
    board = build()
    pcb_copper.build(board)
    pcbnew.SaveBoard(PCB, board)
    pcb_rules.insert_stackup(PCB)
    pcb_rules.update_project(os.path.join(HW, "USBAudioBridge.kicad_pro"))
    pcb_rules.write_dru(os.path.join(HW, "USBAudioBridge.kicad_dru"))
    print("saved", PCB)


if __name__ == "__main__":
    sync_fields() if "--sync-fields" in sys.argv else main()
