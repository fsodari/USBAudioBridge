"""Fabrication and assembly outputs for JLCPCB and PCBWay.

Usage: python3 tools/fab.py [--no-checks] [--step] [--out DIR]

Runs ERC and DRC (any violation stops the build), then writes, under
hardware/build/fab/ by default:

  USBAudioBridge-<rev>-jlcpcb/   Gerbers + drill zip, BOM (LCSC numbers), CPL
  USBAudioBridge-<rev>-pcbway/   Gerbers + drill zip, BOM (MPNs), centroid
  both:                          schematic PDF, assembly drawings, order notes

plus a .zip of each folder.  Needs only kicad-cli and KiCad's pcbnew Python
module, so it runs unchanged in the kicad/kicad Docker image (see
.github/workflows/fab.yml).  Part numbers come from the schematic's MPN,
Manufacturer and LCSC fields, which tools/design.py sets.
"""

import csv
import os
import re
import shutil
import subprocess
import sys
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.normpath(os.path.join(HERE, "..", "hardware"))
NAME = "USBAudioBridge"
SCH = os.path.join(HW, NAME + ".kicad_sch")
PCB = os.path.join(HW, NAME + ".kicad_pcb")

GERBER_LAYERS = ("F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,"
                 "F.Mask,B.Mask,Edge.Cuts")

# JLCPCB's part library draws some packages rotated from KiCad's zero.  These
# corrections come from the community database used by kicad-jlcpcb-tools
# (matthewlai/JLCKicadTools cpl_rotations_db.csv); first match wins, so the
# more specific pattern goes first.  JLCPCB's placement preview is the final
# word: check it when ordering and add an entry here if a part shows rotated.
JLC_ROTATION = (
    (r"^SOT-223", 180),
    (r"^SOT-23", -90),
    (r"^(LQFP|TQFP|SOIC|TSSOP)-", 270),
)


def run(args, **kw):
    print("  $", " ".join(os.path.relpath(a, os.getcwd()) if a.startswith("/") else a
                          for a in args))
    return subprocess.run(args, check=True, **kw)


# --- checks -------------------------------------------------------------------

def checks(build):
    run(["kicad-cli", "sch", "erc", "--exit-code-violations", "--severity-all",
         "-o", os.path.join(build, "erc.rpt"), SCH], stdout=subprocess.DEVNULL)
    run(["kicad-cli", "pcb", "drc", "--exit-code-violations", "--severity-all",
         "--schematic-parity", "-o", os.path.join(build, "drc.rpt"), PCB],
        stdout=subprocess.DEVNULL)


# --- board data -------------------------------------------------------------

def revision():
    tb = pcbnew.LoadBoard(PCB).GetTitleBlock()
    return tb.GetRevision() or "draft"


def placements():
    """Every assembled footprint: pad-centroid position in mm from the drill/place
    origin (lower-left board corner, y up), KiCad rotation, side and mount type."""
    board = pcbnew.LoadBoard(PCB)
    ox, oy = board.GetDesignSettings().GetAuxOrigin()
    parts = {}
    for fp in board.GetFootprints():
        if fp.IsExcludedFromPosFiles() or fp.IsDNP():
            continue
        pads = [p for p in fp.Pads() if p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
        if pads:
            bb = pads[0].GetBoundingBox()
            for p in pads[1:]:
                bb.Merge(p.GetBoundingBox())
            c = bb.GetCenter()
        else:
            c = fp.GetPosition()
        ref = fp.GetReference()
        parts[ref] = {
            "ref": ref,
            "value": fp.GetValue(),
            "package": str(fp.GetFPID().GetLibItemName()),
            "x": pcbnew.ToMM(c.x - ox),
            "y": pcbnew.ToMM(oy - c.y),
            "rot": fp.GetOrientationDegrees() % 360,
            "side": "bottom" if fp.IsFlipped() else "top",
            "type": "THT" if fp.GetAttributes() & pcbnew.FP_THROUGH_HOLE else "SMD",
        }
    return parts


def bom(build):
    """Schematic BOM grouped by value, footprint and MPN (DNP and excluded parts left out)."""
    fields = "Reference,Value,Footprint,MPN,Manufacturer,LCSC,Spec,${QUANTITY}"
    path = os.path.join(build, "bom-raw.csv")
    run(["kicad-cli", "sch", "export", "bom", "-o", path, "--fields", fields,
         "--labels", "Refs,Value,Footprint,MPN,Manufacturer,LCSC,Spec,Qty",
         "--group-by", "Value,Footprint,MPN", "--ref-range-delimiter", "",
         "--exclude-dnp", SCH], stdout=subprocess.DEVNULL)
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["refs"] = [x.strip() for x in r["Refs"].split(",")]
        r["package"] = r["Footprint"].split(":")[-1]
    return rows


def validate(lines, parts):
    errors = []
    bom_refs = {ref for line in lines for ref in line["refs"]}
    if bom_refs - set(parts):
        errors.append(f"in BOM but not placed: {sorted(bom_refs - set(parts))}")
    if set(parts) - bom_refs:
        errors.append(f"placed but not in BOM: {sorted(set(parts) - bom_refs)}")
    for line in lines:
        missing = [k for k in ("MPN", "Manufacturer", "LCSC") if not line[k]]
        if missing:
            errors.append(f"{','.join(line['refs'])}: no {'/'.join(missing)}")
    if errors:
        sys.exit("BOM problems:\n  " + "\n  ".join(errors))


def jlc_rotation(part):
    rot = part["rot"]
    if part["side"] == "bottom":
        # JLCPCB reads bottom rotations mirrored about the Y axis
        rot = (180 - rot) % 360
    for pattern, corr in JLC_ROTATION:
        if re.search(pattern, part["package"]):
            return (rot + corr) % 360
    return rot


# --- outputs ----------------------------------------------------------------

def gerbers(build, base):
    gdir = os.path.join(build, "gerbers")
    shutil.rmtree(gdir, ignore_errors=True)
    os.makedirs(gdir)
    run(["kicad-cli", "pcb", "export", "gerbers", "-o", gdir, "--layers", GERBER_LAYERS,
         "--subtract-soldermask", "--use-drill-file-origin", "--check-zones", PCB],
        stdout=subprocess.DEVNULL)
    run(["kicad-cli", "pcb", "export", "drill", "-o", gdir, "--format", "excellon",
         "--excellon-units", "mm", "--excellon-separate-th", "--drill-origin", "plot", PCB],
        stdout=subprocess.DEVNULL)
    zpath = os.path.join(build, f"{base}-gerbers.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(gdir)):
            z.write(os.path.join(gdir, name), name)
    return zpath


def documents(build, base):
    """Schematic PDF and top/bottom assembly drawings (fab layers, outline, pads)."""
    out = []
    sch = os.path.join(build, f"{base}-schematic.pdf")
    run(["kicad-cli", "sch", "export", "pdf", "-o", sch, SCH], stdout=subprocess.DEVNULL)
    out.append(sch)
    for side, layers, extra in (("top", "F.Fab,Edge.Cuts", []),
                                ("bottom", "B.Fab,Edge.Cuts", ["--mirror"])):
        path = os.path.join(build, f"{base}-assembly-{side}.pdf")
        run(["kicad-cli", "pcb", "export", "pdf", "-o", path, "--layers", layers,
             "--mode-single", "--exclude-value", "--sketch-pads-on-fab-layers",
             "--black-and-white", "--scale", "0", *extra, PCB], stdout=subprocess.DEVNULL)
        out.append(path)
    return out


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return path


def jlcpcb(build, base, lines, parts):
    bom_path = write_csv(
        os.path.join(build, f"{base}-bom-jlcpcb.csv"),
        ["Comment", "Designator", "Footprint", "LCSC"],
        [[line["Value"], ",".join(line["refs"]), line["package"], line["LCSC"]]
         for line in lines])
    cpl_path = write_csv(
        os.path.join(build, f"{base}-cpl-jlcpcb.csv"),
        ["Designator", "Val", "Package", "Mid X", "Mid Y", "Rotation", "Layer"],
        [[p["ref"], p["value"], p["package"], f"{p['x']:.4f}", f"{p['y']:.4f}",
          f"{jlc_rotation(p):g}", p["side"]] for p in sorted(parts.values(), key=sort_key)])
    return [bom_path, cpl_path]


def pcbway(build, base, lines, parts):
    rows = []
    for i, line in enumerate(lines, 1):
        types = {parts[r]["type"] for r in line["refs"]}
        sides = {parts[r]["side"] for r in line["refs"]}
        rows.append([i, ",".join(line["refs"]), line["Qty"], line["Manufacturer"],
                     line["MPN"], f"{line['Value']}; {line['Spec']}".strip("; "),
                     line["package"], "/".join(sorted(types)),
                     f"LCSC {line['LCSC']}; side: {'/'.join(sorted(sides))}"])
    bom_path = write_csv(
        os.path.join(build, f"{base}-bom-pcbway.csv"),
        ["Item #", "Designator", "Qty", "Manufacturer", "Mfg Part #", "Description / Value",
         "Package/Footprint", "Type", "Your Instructions / Notes"], rows)
    # KiCad's own convention (rotation as placed, bottom parts as KiCad reports them),
    # which PCBWay reads directly; the assembly drawings settle any doubt.
    cen_path = write_csv(
        os.path.join(build, f"{base}-centroid-pcbway.csv"),
        ["Designator", "Value", "Footprint", "Mid X(mm)", "Mid Y(mm)", "Rotation", "Layer"],
        [[p["ref"], p["value"], p["package"], f"{p['x']:.4f}", f"{p['y']:.4f}",
          f"{p['rot']:g}", "Top" if p["side"] == "top" else "Bottom"]
         for p in sorted(parts.values(), key=sort_key)])
    return [bom_path, cen_path]


def sort_key(p):
    m = re.match(r"([A-Z]+)(\d+)", p["ref"])
    return (m.group(1), int(m.group(2))) if m else (p["ref"], 0)


def git_version():
    try:
        rev = subprocess.run(["git", "-C", HERE, "describe", "--always", "--dirty"],
                             capture_output=True, text=True, check=True).stdout.strip()
        return rev or "unknown"
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def dnp_refs():
    return [fp.GetReference() for fp in pcbnew.LoadBoard(PCB).GetFootprints() if fp.IsDNP()]


def board_size():
    """Outline extent from the Edge.Cuts geometry (the bounding box would add the stroke)."""
    xs, ys = [], []
    for d in pcbnew.LoadBoard(PCB).GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            for v in (d.GetStart(), d.GetEnd()):
                xs.append(pcbnew.ToMM(v.x))
                ys.append(pcbnew.ToMM(v.y))
    return max(xs) - min(xs), max(ys) - min(ys)


COMMON_NOTES = """\
{title} {rev}  (source {git})

Board
  Size              {w:.2f} x {h:.2f} mm, 4 layers, 1.6 mm, 1 oz outer / 0.5 oz inner
  Material          FR-4 TG150-155 class preferred (two lead-free reflows, double-sided);
                    standard TG130-140 is acceptable
  Layer order       F.Cu (top) / In1.Cu GND plane / In2.Cu +3V3 & +1V1 planes / B.Cu (bottom)
  Min track/space   0.15 / 0.15 mm
  Vias              0.3 mm drill; 0.5 mm pad (0.45 on USB/VBUS, 0.6 on power); tented
  Surface finish    OSP (flat pads for the 0.5 mm pitch LQFP-80; assembled soon after
                    fabrication).  ENIG also fine; avoid HASL (uneven on fine pitch)
  Solder mask       any colour; silkscreen white, text 1.0 mm / 0.16 mm stroke
  Impedance         USB D+/D- 90 ohm differential on F.Cu over In1 GND: 0.20 mm / 0.15 mm
Assembly
  Double-sided SMT. Bottom: U1 (LQFP-80), DC-DC inductor, crystals, flash, reset/boot
  parts. Top: decoupling, USB-C, regulators, clock buffer, connectors.
  Through-hole: J502 (1x3 header), J601/J602 (2x6 right-angle PMOD headers, top side,
  pins over the board edge).
  {nparts} placements, {nlines} BOM lines.  Not assembled: test points, mounting holes,
  JP601 (solder jumper) and the DNP parts {dnp}.
"""

JLC_NOTES = COMMON_NOTES + """
JLCPCB order
  Upload {base}-gerbers.zip.  Layers 4, thickness 1.6 mm, surface finish OSP,
  material FR-4 TG155.  Min via hole size/diameter: 0.3 mm / (0.4/0.45 mm), the
  standard option.
  Impedance control: yes, stackup JLC04161H-3313 (the USB pair was sized for it).
  Via covering: tented.  Remove order number: optional.
  If JLCPCB asks for edge rails (parts overhang both short edges), let them add them.
  PCB Assembly: both sides, Standard PCBA.  Upload {base}-bom-jlcpcb.csv and
  {base}-cpl-jlcpcb.csv.  Check every part in the placement preview, especially U1
  pin 1, the SOT parts, J101, J501 and the PMOD headers, before confirming.
"""

PCBWAY_NOTES = COMMON_NOTES + """
PCBWay order
  Upload {base}-gerbers.zip.  Layers 4, thickness 1.6 mm, surface finish OSP,
  FR-4 TG150, min track/space 6/6 mil, min hole 0.3 mm, via tented.
  Via annular ring is 0.1 mm (4 mil) on 0.5 mm vias and 0.075 mm on the four
  0.45 mm USB/VBUS vias: below PCBWay's 5 mil standard, so expect an engineering
  question; tangency on vias is acceptable for this design.
  Impedance control: request 90 ohm differential for the USB pair (nets USB_DP/USB_DN
  on the top layer, reference In1 GND); let PCBWay adjust width/gap to their stackup.
  Assembly: turnkey, both sides.  Upload {base}-bom-pcbway.csv,
  {base}-centroid-pcbway.csv and the two assembly drawing PDFs.  Centroid
  rotations follow KiCad's convention; the assembly drawings show pin 1 for
  every part.  LCSC numbers in the BOM notes are known-good equivalents.
"""


def package(out, base, vendor, files, notes):
    d = os.path.join(out, f"{base}-{vendor}")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    for f in files:
        shutil.copy(f, d)
    with open(os.path.join(d, "ORDER-NOTES.txt"), "w") as f:
        f.write(notes)
    zpath = d + ".zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(os.listdir(d)):
            z.write(os.path.join(d, name), os.path.join(os.path.basename(d), name))
    print("  ->", os.path.relpath(zpath))


def main():
    args = sys.argv[1:]
    out = os.path.join(HW, "build", "fab")
    if "--out" in args:
        out = os.path.abspath(args[args.index("--out") + 1])
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)

    if "--no-checks" not in args:
        print("checks")
        checks(work)

    rev = revision()
    base = f"{NAME}-{rev}"
    print("outputs for", base)
    parts = placements()
    lines = bom(work)
    validate(lines, parts)
    gzip = gerbers(work, base)
    docs = documents(work, base)
    if "--step" in args:
        step = os.path.join(work, f"{base}.step")
        run(["kicad-cli", "pcb", "export", "step", "-o", step, "--subst-models",
             "--no-dnp", "--force", PCB], stdout=subprocess.DEVNULL)
        docs.append(step)

    w, h = board_size()
    info = dict(title=NAME, rev=rev, git=git_version(), base=base, w=w, h=h,
                nparts=len(parts), nlines=len(lines), dnp=", ".join(sorted(dnp_refs())) or "-")
    package(out, base, "jlcpcb", [gzip, *jlcpcb(work, base, lines, parts), *docs],
            JLC_NOTES.format(**info))
    package(out, base, "pcbway", [gzip, *pcbway(work, base, lines, parts), *docs],
            PCBWAY_NOTES.format(**info))


if __name__ == "__main__":
    main()
