"""Route the remaining nets with Freerouting and finish the board.

Usage: python3 tools/autoroute.py [max_passes]
       python3 tools/autoroute.py --reuse   (after tools/pcb.py: re-import the last session)

1. export hardware/build/board.dsn from the generated board
2. mark In1/In2 as power layers (no signal routing in the planes) and the
   scripted copper as protected
3. run Freerouting headless, import the session
4. add the F.Cu/B.Cu GND pours, refill all zones, save
"""

import json
import os
import subprocess
import sys

import pcbnew

import pcb_copper
import pcb_silk
from pcb_route import Router

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.join(HERE, "..", "hardware")
BUILD = os.path.join(HW, "build")
PCB = os.path.join(HW, "USBAudioBridge.kicad_pcb")
JAR = os.path.join(HERE, "bin", "freerouting-2.1.0.jar")


def prepare_dsn(board):
    raw = os.path.join(BUILD, "board_raw.dsn")
    dsn = os.path.join(BUILD, "board.dsn")
    if not pcbnew.ExportSpecctraDSN(board, raw):
        sys.exit("DSN export failed")
    s = open(raw).read()
    for lay in ("In1.Cu", "In2.Cu"):
        s = s.replace(f"(layer {lay}\n      (type signal)", f"(layer {lay}\n      (type power)")
    s = s.replace("(type route)", "(type protect)")
    open(dsn, "w").write(s)
    return dsn


FR_SETTINGS = "/tmp/freerouting/freerouting.json"


def write_settings(passes):
    """Freerouting reads this file at start-up and it overrides command-line
    flags; keep telemetry off and the pass limit real."""
    os.makedirs(os.path.dirname(FR_SETTINGS), exist_ok=True)
    d = {}
    if os.path.exists(FR_SETTINGS):
        d = json.load(open(FR_SETTINGS))
    d.setdefault("profile", {}).update({"allow_telemetry": False, "allow_contact": False})
    d.setdefault("usage_and_diagnostic_data", {})["disable_analytics"] = True
    d.setdefault("gui", {})["enabled"] = False
    r = d.setdefault("router", {})
    r["max_passes"] = passes
    r["job_timeout"] = "00:20:00"
    r.setdefault("fanout", {})["enabled"] = True
    r["max_threads"] = 4
    r.setdefault("optimizer", {})["max_passes"] = 20
    json.dump(d, open(FR_SETTINGS, "w"), indent=2)


def freeroute(dsn, passes):
    write_settings(passes)
    ses = os.path.join(BUILD, "board.ses")
    if os.path.exists(ses):
        os.remove(ses)
    log = open(os.path.join(BUILD, "freerouting.log"), "w")
    subprocess.run(["java", "-jar", JAR, "-de", dsn, "-do", ses, "-mp", str(passes),
                    f"--router.max_passes={passes}", "-mt", "4", "--gui.enabled=false"],
                   stdout=log, stderr=subprocess.STDOUT, timeout=3600)
    if not os.path.exists(ses):
        sys.exit("Freerouting produced no session file; see build/freerouting.log")
    return ses


def remove_dangling(board):
    """Delete vias and track stubs left connected at one end only.

    All geometry is read into plain floats in one pass first: the SWIG proxies
    become unreliable after many calls in one process."""
    from pcb_copper import V1_POLY
    from pcb_route import point_in_poly, rel
    MM = pcbnew.ToMM
    tracks, vias, pads = [], [], []
    for t in board.GetTracks():
        net = t.GetNetname()
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            vias.append([t, net, MM(p.x), MM(p.y), MM(t.GetWidth(pcbnew.F_Cu)) / 2])
        else:
            a, b = t.GetStart(), t.GetEnd()
            tracks.append([t, net, t.GetLayer(), MM(a.x), MM(a.y), MM(b.x), MM(b.y),
                           MM(t.GetWidth()) / 2])
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            o, e = bb.GetOrigin(), bb.GetEnd()
            layers = {l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if p.IsOnLayer(l)}
            pads.append((p.GetNetname(), layers, MM(o.x), MM(o.y), MM(e.x), MM(e.y)))

    def near(ax, ay, bx, by, tol):
        return abs(ax - bx) <= tol and abs(ay - by) <= tol

    def on_seg(px, py, t, tol):
        _, _, _, x1, y1, x2, y2, w = t
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        k = 0 if L2 == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L2))
        return ((px - x1 - k * dx) ** 2 + (py - y1 - k * dy) ** 2) ** 0.5 <= w + tol

    def in_plane(net, x, y):
        if net in ("GND", "+3V3"):
            return True
        if net == "+1V1":
            return point_in_poly((x - 100.0, y - 100.0), V1_POLY)
        return False

    removed = 0
    # Freerouting 2.1 sometimes emits the same segment twice (or on both outer
    # layers); exact duplicates would keep each other "connected"
    seen, uniq = set(), []
    for t in tracks:
        key = (t[1], t[2]) + tuple(sorted([(round(t[3], 4), round(t[4], 4)),
                                           (round(t[5], 4), round(t[6], 4))]))
        if key in seen:
            board.Remove(t[0])
            removed += 1
        else:
            seen.add(key)
            uniq.append(t)
    tracks = uniq
    while True:
        dead_t, dead_v = set(), set()
        for i, v in enumerate(vias):
            _, net, x, y, r = v
            # a track counts if it reaches anywhere inside the via's pad
            layers = {t[2] for t in tracks if t[1] == net and
                      (on_seg(x, y, t, r) or near(t[3], t[4], x, y, r) or near(t[5], t[6], x, y, r))}
            on_pad = any(pn == net and x1 <= x <= x2 and y1 <= y <= y2
                         for pn, _, x1, y1, x2, y2 in pads)
            if len(layers) + (1 if in_plane(net, x, y) else 0) < 2 and not on_pad:
                dead_v.add(i)
        for i, t in enumerate(tracks):
            _, net, lay, x1, y1, x2, y2, w = t
            for ex, ey in ((x1, y1), (x2, y2)):
                ok = any(pn == net and lay in pl and a - 0.01 <= ex <= c + 0.01 and
                         b - 0.01 <= ey <= d + 0.01 for pn, pl, a, b, c, d in pads)
                ok = ok or any(v[1] == net and near(ex, ey, v[2], v[3], v[4])
                               for k, v in enumerate(vias) if k not in dead_v)
                ok = ok or any(j != i and o[1] == net and o[2] == lay and on_seg(ex, ey, o, 0.01)
                               for j, o in enumerate(tracks))
                # inner-layer tracks end in their plane zone
                ok = ok or (lay in (pcbnew.In1_Cu, pcbnew.In2_Cu) and in_plane(net, ex, ey))
                if not ok:
                    dead_t.add(i)
                    break
        if not dead_t and not dead_v:
            return removed
        for i in sorted(dead_v, reverse=True):
            board.Remove(vias.pop(i)[0])
            removed += 1
        for i in sorted(dead_t, reverse=True):
            board.Remove(tracks.pop(i)[0])
            removed += 1


def finish():
    """Second stage, in a fresh process: pours, zone fill, silkscreen."""
    board = pcbnew.LoadBoard(PCB)
    r = Router(board)
    pcb_copper.outer_pours(r)
    r.fill()
    print("GND stitching vias:", pcb_copper.stitch(r, board))
    r.fill()
    pcb_silk.tidy(board)
    pcb_silk.labels(board)
    pcbnew.SaveBoard(PCB, board)
    print("routed and saved", PCB)


def main():
    """python3 tools/autoroute.py [passes] | --reuse (re-import build/board.ses)"""
    if "--finish" in sys.argv:
        return finish()
    if "--clean" in sys.argv:
        return clean()
    if "--repair" in sys.argv:
        return repair()
    board = pcbnew.LoadBoard(PCB)
    if "--reuse" in sys.argv:
        ses = os.path.join(BUILD, "board.ses")
    else:
        passes = int(sys.argv[1]) if len(sys.argv) > 1 else 40
        ses = freeroute(prepare_dsn(board), passes)
    if not pcbnew.ImportSpecctraSES(board, ses):
        sys.exit("SES import failed")
    pcbnew.SaveBoard(PCB, board)
    # SWIG proxies degrade over long sessions: clean and finish in fresh processes
    for stage in ("--clean", "--repair", "--finish"):
        subprocess.run([sys.executable, os.path.abspath(__file__), stage], check=True)


def repair():
    """Close the few connections the autorouter left open: read KiCad's DRC
    unconnected pairs and join each with a short track (plus a via when the two
    ends are on different outer layers)."""
    import re
    import pcb_layout as Lay
    from pcb_route import Router
    rpt = os.path.join(BUILD, "repair_drc.rpt")
    subprocess.run(["kicad-cli", "pcb", "drc", "-o", rpt, PCB], capture_output=True)
    pairs = []
    for blk in re.split(r"\n(?=\[)", open(rpt).read()):
        if not blk.startswith("[unconnected_items]"):
            continue
        ends = []
        for line in blk.splitlines():
            m = re.search(r"@\(([\d.]+) mm, ([\d.]+) mm\): .*?\[(.+?)\]", line)
            if m:
                lay = re.search(r" on ([FB])\.Cu", line)
                # through-hole pads carry no layer: reach them on F.Cu
                ends.append((float(m.group(1)) - Lay.ORIGIN[0], float(m.group(2)) - Lay.ORIGIN[1],
                             (lay.group(1) if lay else "F") + ".Cu", m.group(3)))
        if len(ends) == 2 and ends[0][3] == ends[1][3]:
            pairs.append(ends)
    board = pcbnew.LoadBoard(PCB)
    r = Router(board)
    fixed = 0
    for (ax, ay, al, net), (bx, by, bl, _) in pairs:
        done = False
        cl, vd = 0.16, 0.45     # rule minimums (+0.01 margin) for these short repairs
        if al == bl:
            for path in ([(ax, ay), (bx, by)], [(ax, ay), (bx, ay), (bx, by)],
                         [(ax, ay), (ax, by), (bx, by)]):
                if r.path_free(net, al, path, 0.15, clearance=cl):
                    r.track(net, al, path, 0.15)
                    done = True
                    break
        if not done:
            # a via between the ends; also used when a same-layer path is blocked
            leg2 = bl if al != bl else ("B.Cu" if al == "F.Cu" else "F.Cu")
            cands = [(ax + i * 0.1, ay + j * 0.1) for i in range(-40, 41) for j in range(-40, 41)]
            cands.sort(key=lambda v: 2 * (abs(v[0] - ax) + abs(v[1] - ay)) +
                       abs(v[0] - bx) + abs(v[1] - by))
            def legs(p, q):
                # straight, then the two L-shapes
                return ([p, q], [p, (q[0], p[1]), q], [p, (p[0], q[1]), q])

            for v in cands[:2500]:
                if not r.via_ok(net, v, d=vd, clearance=cl):
                    continue
                l1 = next((pth for pth in legs((ax, ay), v)
                           if r.path_free(net, al, pth, 0.15, clearance=cl)), None)
                l2 = l1 and next((pth for pth in legs(v, (bx, by))
                                  if r.path_free(net, leg2, pth, 0.15, clearance=cl)), None)
                if l1 and l2:
                    r.track(net, al, l1, 0.15)
                    r.via(net, v, d=vd)
                    r.track(net, leg2, l2, 0.15)
                    done = True
                    break
        fixed += done
        if not done:
            print(f"  repair: could not join {net} {al}({ax:.2f},{ay:.2f}) - {bl}({bx:.2f},{by:.2f})")
    pcbnew.SaveBoard(PCB, board)
    print(f"repaired {fixed} of {len(pairs)} open connections")


def clean():
    board = pcbnew.LoadBoard(PCB)
    print("removed dangling items:", remove_dangling(board))
    pcbnew.SaveBoard(PCB, board)


if __name__ == "__main__":
    main()
