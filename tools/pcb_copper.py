"""Planes, critical routes and fanout for the USB Audio Bridge board.

Layer plan (JLC04161H-3313):
  F.Cu    components, signals, GND pour (also catches the MCU GND pins from inside)
  In1.Cu  solid GND
  In2.Cu  +3V3 plane with a +1V1 island under the MCU (fingers to the three
          VDD_SOC pins, corridor to the DC-DC inductor)
  B.Cu    MCU decoupling caps, a few signals, GND pour
"""

import math

import pcbnew

import pcb_layout as L
from pcb_route import (ALL, CLEAR, PWR_VIA_D, VIA_D, Router, circle, pad, pad_xy, pt,
                       rect, rel, seg)

MCU_C = (L.MCU[0], L.MCU[1])
BOARD = [(0, 0), (L.W, 0), (L.W, L.H), (0, L.H)]

# +1V1 island on In2.Cu (board mm)
ISL = 4.8
V1_POLY = [
    (MCU_C[0] - ISL, MCU_C[1] - ISL),          # island NW corner
    (MCU_C[0] + ISL, MCU_C[1] - ISL),
    (MCU_C[0] + ISL, 24.65), (27.75, 24.65), (27.75, 25.85), (MCU_C[0] + ISL, 25.85),  # pin 14
    (MCU_C[0] + ISL, MCU_C[1] + ISL),
    (25.45, MCU_C[1] + ISL), (25.45, 33.15), (24.25, 33.15), (24.25, MCU_C[1] + ISL),  # pin 77
    (MCU_C[0] - ISL, MCU_C[1] + ISL),
    (MCU_C[0] - ISL, 28.85), (15.45, 28.85), (15.45, 27.65), (MCU_C[0] - ISL, 27.65),  # pin 53
]
V1_VIAS = {"14": (27.14, 25.25), "53": (16.04, 28.25), "77": (24.84, 32.55)}

PLANE_NETS = ("GND", "+3V3", "+1V1")
LOCAL_LDO = ("VDD_HIGH_CAP", "NVCC_PLL", "VDD_SNVS_CAP", "VDD_USB_CAP")


def zones(r):
    r.zone("GND", "In1.Cu", BOARD, priority=0, solid=True)
    r.zone("+3V3", "In2.Cu", BOARD, priority=0)
    r.zone("+1V1", "In2.Cu", V1_POLY, priority=1, solid=True)


def stitch(r, board, grid=3.0):
    """GND vias: one in every outer-layer GND fragment that has no via or
    through-hole pad, plus a regular grid wherever both outer layers are GND."""
    import pcbnew as pn
    zs = {z.GetLayer(): z for z in board.Zones()
          if z.GetNetname() == "GND" and z.GetLayer() in (pn.F_Cu, pn.B_Cu)}
    fills = {lay: z.GetFilledPolysList(lay) for lay, z in zs.items()}
    gnd = [t.GetPosition() for t in board.GetTracks()
           if t.Type() == pn.PCB_VIA_T and t.GetNetname() == "GND"]
    gnd += [p.GetPosition() for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetNetname() == "GND" and p.GetAttribute() == pn.PAD_ATTRIB_PTH]

    def inside_all(poly, c, rad=0.55):
        return all(poly.PointInside(pt(c[0] + dx * rad, c[1] + dy * rad))
                   for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1),
                                  (0.7, 0.7), (-0.7, 0.7), (0.7, -0.7), (-0.7, -0.7)))

    added = 0
    for lay, polys in fills.items():
        for i in range(polys.OutlineCount()):
            ol = polys.Outline(i)
            if any(ol.PointInside(g) for g in gnd):
                continue
            bb = ol.BBox()
            x0, y0 = rel(bb.GetOrigin())
            x1, y1 = rel(bb.GetEnd())
            done = False
            yy = y0
            while yy <= y1 and not done:
                xx = x0
                while xx <= x1 and not done:
                    if inside_all(ol, (xx, yy)) and r.via_ok("GND", (xx, yy)):
                        r.via("GND", (xx, yy))
                        gnd.append(pt(xx, yy))
                        added += 1
                        done = True
                    xx += 0.25
                yy += 0.25
    if pn.F_Cu in fills and pn.B_Cu in fills:
        yy = grid / 2
        while yy < L.H:
            xx = grid / 2
            while xx < L.W:
                c = (xx, yy)
                near = any(math.hypot(pn.ToMM(g.x) - L.ORIGIN[0] - xx,
                                      pn.ToMM(g.y) - L.ORIGIN[1] - yy) < grid * 0.6 for g in gnd)
                if not near and all(inside_all(fills[l].Outline(j), c)
                                    for l in (pn.F_Cu, pn.B_Cu)
                                    for j in [_fragment(fills[l], c)] if j is not None) \
                        and all(_fragment(fills[l], c) is not None for l in (pn.F_Cu, pn.B_Cu)) \
                        and r.via_ok("GND", c):
                    r.via("GND", c)
                    gnd.append(pt(*c))
                    added += 1
                xx += grid
            yy += grid
    return added


def _fragment(polys, c):
    p = pt(*c)
    for j in range(polys.OutlineCount()):
        if polys.Outline(j).PointInside(p):
            return j
    return None


def outer_pours(r):
    """F.Cu/B.Cu GND pours, added after autorouting so they don't block it."""
    r.zone("GND", "F.Cu", BOARD, priority=0)
    r.zone("GND", "B.Cu", BOARD, priority=0)


def usb(r):
    """D+/D- from the USB-C pads through the ESD array to the MCU (F.Cu, 90 ohm)."""
    w = 0.2
    # D+: both connector pads (B6, A6) joined below the pads, then to U101 pin 6
    r.track("USB_DP", "F.Cu", [(20.84, 7.355), (20.84, 9.6)], 0.15)
    r.track("USB_DP", "F.Cu", [(21.84, 7.355), (21.84, 9.6)], 0.15)
    r.track("USB_DP", "F.Cu", [(20.84, 9.6), (21.84, 9.6)], 0.15)
    r.track("USB_DP", "F.Cu", [(20.84, 9.6), (20.64, 9.8), (20.64, 11.062)], w)
    # D-: A7 drops to B.Cu and rejoins B7's route through a second via
    r.track("USB_DN", "F.Cu", [(21.34, 7.355), (21.34, 8.55)], 0.15)
    r.via("USB_DN", (21.34, 8.55), d=0.45)
    r.track("USB_DN", "B.Cu", [(21.34, 8.55), (22.95, 9.3)], w)
    r.via("USB_DN", (22.95, 9.3), d=0.45)
    r.track("USB_DN", "F.Cu", [(22.34, 7.355), (22.34, 9.3), (22.34, 10.0), (22.54, 10.2),
                               (22.54, 11.062)], w)
    r.track("USB_DN", "F.Cu", [(22.95, 9.3), (22.34, 9.3)], w)
    # U101 -> MCU pins 33 (D+) and 32 (D-), coupled from y=15.84
    r.track("USB_DP", "F.Cu", [(20.64, 13.338), (20.64, 18.2), (20.34, 18.5), (20.34, 20.312)], w)
    r.track("USB_DN", "F.Cu", [(22.54, 13.338), (22.54, 14.3), (21.0, 15.84), (21.0, 18.65),
                               (20.84, 18.81), (20.84, 20.312)], w)


def usb_shield(r, board):
    """Join the receptacle's left and right shield tabs on B.Cu under the
    connector (the 1M || 4.7nF to GND sits on the right side)."""
    net = next(n for n in r.nets if n.endswith("USB_SHIELD"))
    left, right = (17.27, 6.78), (25.91, 6.78)
    for x in (left[0], right[0]):          # front and rear tab on each side
        r.track(net, "F.Cu", [(x, 2.6), (x, 6.78)], 0.4)
    for y in (7.6, 7.9, 8.2, 1.2):
        path = [left, (left[0], y), (right[0], y), right]
        if r.path_free(net, "B.Cu", path, 0.3):
            r.track(net, "B.Cu", path, 0.3)
            return
    raise RuntimeError("no room for the USB shield link")


def dcdc(r):
    """Pin 19 (DCDC_LP) straight east into L201 pin 1; L201 pin 2 (+1V1) to its
    output caps on F.Cu and to the In2 +1V1 island through a protected In2 track
    (a zone corridor would be cut by other nets' via antipads)."""
    r.track("DCDC_LP", "F.Cu", [(28.278, 22.75), (29.7, 22.75)], 0.25)
    r.track("DCDC_LP", "F.Cu", [(29.7, 22.75), (33.2, 22.75)], 0.6)
    r.track("+1V1", "F.Cu", [(35.0, 20.55), (39.8, 20.55), (39.8, 20.08)], 0.6)
    r.track("+1V1", "F.Cu", [(32.6, 20.075), (31.4, 20.075)], 0.6)
    for v in ((31.4, 19.55), (31.4, 20.6)):
        r.via("+1V1", v, d=0.6)
    r.track("+1V1", "F.Cu", [(31.4, 19.55), (31.4, 20.6)], 0.6)
    r.track("+1V1", "In2.Cu", [(31.4, 19.55), (31.4, 25.25), (27.6, 25.25)], 0.8)


def _normal(c):
    dx, dy = c[0] - MCU_C[0], c[1] - MCU_C[1]
    if abs(dx) > abs(dy):
        return (1 if dx > 0 else -1, 0), (0, 1)
    return (0, 1 if dy > 0 else -1), (1, 0)


def _place_cap(board, ref, centre, outward, flip=True):
    """Put a two-pad cap at centre on B.Cu with pad 1 towards `outward`."""
    fp = board.FindFootprintByReference(ref)
    fp.SetPosition(pt(*centre))
    if flip and not fp.IsFlipped():
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    for rot in (0, 90, 180, 270):
        fp.SetOrientationDegrees(rot)
        p1 = rel(next(p for p in fp.Pads() if p.GetNumber() == "1").GetPosition())
        d = (p1[0] - centre[0], p1[1] - centre[1])
        if d[0] * outward[0] + d[1] * outward[1] > 0.3:
            break
    return fp


def _register_fp(r, fp):
    for p in fp.Pads():
        r.obs.append(r._pad_shape(p))


def mcu_power(r, board):
    """Fan out every MCU supply pin to a via just inside the pad ring and put
    its decoupling cap on B.Cu right behind the via."""
    caps_by_pin = {}
    for ref, (num, kind) in L.DECOUPLING.items():
        caps_by_pin.setdefault(num, []).append((ref, kind))
    u1 = board.FindFootprintByReference("U1")
    placed_boxes = r.bottom_boxes

    def box_free(box):
        return _box_free(r, box)

    # supply pins claim via spots first; GND pins fill in (or tie to a GND via) after
    for p in sorted(u1.Pads(), key=lambda p: (p.GetNetname() == "GND", int(p.GetNumber()))):
        net = p.GetNetname()
        if net not in ("+3V3", "+1V1", "GND") + LOCAL_LDO:
            continue
        num = p.GetNumber()
        c = rel(p.GetPosition())
        n, t = _normal(c)
        inner = (c[0] - n[0] * 0.7375, c[1] - n[1] * 0.7375)
        ring = [ref for ref, kind in caps_by_pin.get(num, []) if kind == "ring"]
        best = None
        if num in V1_VIAS:
            v = V1_VIAS[num]
            s = (v[0] - inner[0]) * t[0] + (v[1] - inner[1]) * t[1]
            dep = abs((v[0] - inner[0]) * n[0] + (v[1] - inner[1]) * n[1])
            cands = [(dep, s)]
        else:
            # adjacent supply pins fan out in opposite directions along the row
            pref, sides = 0, 0
            for nb in (str(int(num) - 1), str(int(num) + 1)):
                q = next((x for x in u1.Pads() if x.GetNumber() == nb), None)
                if q is not None and q.GetNetname() in ("+3V3", "+1V1", "GND") + LOCAL_LDO \
                        and _normal(rel(q.GetPosition()))[0] == n:
                    qc = rel(q.GetPosition())
                    pref = -1 if (qc[0] - c[0]) * t[0] + (qc[1] - c[1]) * t[1] > 0 else 1
                    sides += 1
            if sides == 2:
                # boxed in by fanout neighbours on both sides: go straight in, deeper
                cands = [(d, s / 20) for d in (0.45, 0.6, 0.9, 1.2) for s in range(-6, 7)]
                cands.sort(key=lambda ds: (abs(ds[1]), ds[0]))
            else:
                cands = [(d, s / 20) for d in (0.45, 0.6) for s in range(-40, 41)
                         if not pref or (s / 20) * pref >= 0.3]
            cands.sort(key=lambda ds: (abs(ds[1]), ds[0]))
        for dep, s in cands:
            knee = (inner[0] - n[0] * dep, inner[1] - n[1] * dep)
            v = (knee[0] + t[0] * s, knee[1] + t[1] * s)
            path = [c, inner, knee, v] if s else [c, inner, v]
            if not r.via_ok(net, v, keep_out=[L1V1_KEEP] if net == "+3V3" else []):
                continue
            if not r.path_free(net, "F.Cu", path[1:], 0.25, clearance=0.2):
                continue
            if ring:
                cc = (v[0] - n[0] * 1.15, v[1] - n[1] * 1.15)   # cap centre on B.Cu
                box = (cc[0] - (0.55 if t[0] else 1.0), cc[1] - (0.55 if t[1] else 1.0),
                       cc[0] + (0.55 if t[0] else 1.0), cc[1] + (0.55 if t[1] else 1.0))
                gv = (v[0] - n[0] * 2.35, v[1] - n[1] * 2.35)   # GND via behind the cap
                if not box_free(box) or not r.via_ok("GND", gv):
                    continue
                if not r.free(rect("?", ["B.Cu"], box), clearance=0.15):
                    continue
            best = (v, path, s)
            break
        if best is None and net == "GND":
            # no room for its own via inside the ring:
            # 1) stub to a nearby GND via under the chip, 2) else a via just past the pad tip
            gvias = sorted((o.g["a"] for o in r.obs if o.kind == "seg" and o.net == "GND"
                            and o.g["a"] == o.g["b"] and "In1.Cu" in o.layers),
                           key=lambda g: math.hypot(g[0] - inner[0], g[1] - inner[1]))
            tied = False
            for g in [g for g in gvias if math.hypot(g[0] - inner[0], g[1] - inner[1]) < 3.5]:
                for kd in (0.0, 0.2, 0.4, 0.6, 0.8):
                    knee = (inner[0] - n[0] * kd, inner[1] - n[1] * kd)
                    path = [c, inner, knee, g] if kd else [c, inner, g]
                    if r.path_free("GND", "F.Cu", path[1:], 0.2, clearance=0.2):
                        r.track("GND", "F.Cu", path, 0.2)
                        tied = True
                        break
                if tied:
                    break
            if not tied:
                tip = (c[0] + n[0] * 0.7375, c[1] + n[1] * 0.7375)
                for dist in (0.45, 0.6, 0.8, 1.0):
                    v = (tip[0] + n[0] * dist, tip[1] + n[1] * dist)
                    if r.via_ok("GND", v) and r.path_free("GND", "F.Cu", [tip, v], 0.2):
                        r.track("GND", "F.Cu", [c, tip, v], 0.2)
                        r.via("GND", v)
                        tied = True
                        print(f"  U1 pin {num} (GND): via outside the pad ring")
                        break
            if not tied:
                raise RuntimeError(f"no GND connection for U1 pin {num}")
            continue
        if best is None:
            raise RuntimeError(f"no fanout for U1 pin {num}")
        v, path, s = best
        r.track(net, "F.Cu", path, 0.25)
        r.via(net, v)
        if ring:
            ref = ring[0]
            cc = (v[0] - n[0] * 1.15, v[1] - n[1] * 1.15)
            fp = _place_cap(board, ref, cc, n)
            _register_fp(r, fp)
            placed_boxes.append((cc[0] - (0.55 if t[0] else 1.0), cc[1] - (0.55 if t[1] else 1.0),
                                 cc[0] + (0.55 if t[0] else 1.0), cc[1] + (0.55 if t[1] else 1.0)))
            p1 = rel(next(q for q in fp.Pads() if q.GetNumber() == "1").GetPosition())
            p2 = rel(next(q for q in fp.Pads() if q.GetNumber() == "2").GetPosition())
            r.track(net, "B.Cu", [v, p1], 0.3)
            gv = (v[0] - n[0] * 2.35, v[1] - n[1] * 2.35)
            r.track("GND", "B.Cu", [p2, gv], 0.3)
            r.via("GND", gv)
        caps_by_pin[num] = [(ref, kind) for ref, kind in caps_by_pin.get(num, []) if kind != "ring"]
        r.pin_vias = getattr(r, "pin_vias", {})
        r.pin_vias[num] = (v, n, t)
    return caps_by_pin


L1V1_KEEP = V1_POLY


def _box_free(r, box):
    x1, y1, x2, y2 = box
    return all(x2 <= a1 or x1 >= a2 or y2 <= b1 or y1 >= b2
               for a1, b1, a2, b2 in r.bottom_boxes)


def _courtyard(fp):
    bb = fp.GetCourtyard(pcbnew.B_CrtYd if fp.IsFlipped() else pcbnew.F_CrtYd).BBox()
    x1, y1 = rel(bb.GetOrigin())
    x2, y2 = rel(bb.GetEnd())
    return (x1, y1, x2, y2)


def bulk_caps(r, board, leftovers):
    """Bulk caps on B.Cu: +3V3 ones just outside the pad ring, local-LDO ones
    outside too (wired back to the pin's via), +1V1 ones in the island."""
    u1 = board.FindFootprintByReference("U1")
    for num, items in leftovers.items():
        for ref, kind in items:
            p = next(q for q in u1.Pads() if q.GetNumber() == num)
            c = rel(p.GetPosition())
            n, t = _normal(c)
            net = p.GetNetname()
            placed = False
            # outside caps keep their vias clear of the MCU's top-layer escape zone
            dists = (4.6,) if kind == "in" else (5.2, 6.2, 7.2, 8.5)
            span = 30 if kind == "in" else 60
            for s, dist in sorted(((x / 10, dd) for dd in dists for x in range(-span, span + 1)),
                                  key=lambda sd: (sd[1], abs(sd[0]))):
                sign = -1 if kind == "in" else 1
                cc = (c[0] + sign * n[0] * dist + t[0] * s, c[1] + sign * n[1] * dist + t[1] * s)
                fp = _place_cap(board, ref, cc, n if kind == "in" else (-n[0], -n[1]))
                if not _box_free(r, _courtyard(fp)):
                    continue
                pads = {q.GetNumber(): q for q in fp.Pads()}
                shapes = [r._pad_shape(q) for q in pads.values()]
                if not all(r.free(sh, clearance=0.25) for sh in shapes):
                    continue
                p1, p2 = rel(pads["1"].GetPosition()), rel(pads["2"].GetPosition())
                d1 = (p1[0] - p2[0], p1[1] - p2[1])
                ln = math.hypot(*d1)
                u = (d1[0] / ln, d1[1] / ln)
                v1 = (p1[0] + u[0] * 0.75, p1[1] + u[1] * 0.75)
                v2 = (p2[0] - u[0] * 0.75, p2[1] - u[1] * 0.75)
                keep = {"in": V1_POLY}.get(kind)
                if net in LOCAL_LDO:
                    pv = r.pin_vias[num][0]
                    if not r.via_ok("GND", v2) or not r.path_free(net, "B.Cu", [pv, p1], 0.3):
                        continue
                else:
                    if not r.via_ok(net, v1, keep_in=keep,
                                    keep_out=[] if net == "+1V1" else [V1_POLY]):
                        continue
                    if not r.via_ok("GND", v2):
                        continue
                for sh in shapes:
                    r.obs.append(sh)
                r.bottom_boxes.append(_courtyard(fp))
                if net in LOCAL_LDO:
                    r.track(net, "B.Cu", [r.pin_vias[num][0], p1], 0.3)
                else:
                    r.track(net, "B.Cu", [p1, v1], 0.3)
                    r.via(net, v1)
                r.track("GND", "B.Cu", [p2, v2], 0.3)
                r.via("GND", v2)
                placed = True
                break
            if not placed:
                raise RuntimeError(f"could not place bulk cap {ref}")


def plane_fanout(r, board, skip=("U1",)):
    """Give every remaining SMD pad on a plane net a short stub and a via."""
    done = 0
    for fp in board.GetFootprints():
        if fp.GetReference() in skip:
            continue
        for p in fp.Pads():
            net = p.GetNetname()
            if net not in PLANE_NETS or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            if net == "+1V1":
                continue   # wired explicitly by dcdc() and mcu_power()
            layer = "B.Cu" if p.IsOnLayer(pcbnew.B_Cu) else "F.Cu"
            if any(isinstance(o, object) and o.kind == "seg" and o.net == net and
                   o.g["a"] == o.g["b"] and _near_pad(o.g["a"], p) for o in r.obs):
                continue   # already has a via (e.g. MCU decoupling)
            c = rel(p.GetPosition())
            bb = p.GetBoundingBox()
            hw, hh = pcbnew.ToMM(bb.GetWidth()) / 2, pcbnew.ToMM(bb.GetHeight()) / 2
            d = PWR_VIA_D if net != "GND" else VIA_D
            keep_in = L1V1_KEEP if net == "+1V1" else None
            keep_out = [] if net != "+3V3" else [L1V1_KEEP]
            w = min(0.4, 2 * min(hw, hh))
            ok = False
            for dist in (0.0, 0.15, 0.3, 0.5, 0.8, 1.2):
                for ang in range(0, 360, 30):
                    a = math.radians(ang)
                    ex = c[0] + math.cos(a) * (hw + d / 2 + 0.15 + dist)
                    ey = c[1] + math.sin(a) * (hh + d / 2 + 0.15 + dist)
                    v = (round(ex, 3), round(ey, 3))
                    if not r.via_ok(net, v, d, keep_in=keep_in, keep_out=keep_out):
                        continue
                    if not r.path_free(net, layer, [c, v], w):
                        continue
                    r.track(net, layer, [c, v], w)
                    r.via(net, v, d)
                    ok = True
                    done += 1
                    break
                if ok:
                    break
            if not ok:
                print(f"  no plane via for {fp.GetReference()}.{p.GetNumber()} ({net})")
    return done


def _near_pad(v, p):
    c = rel(p.GetPosition())
    return math.hypot(v[0] - c[0], v[1] - c[1]) < 1.6


SOUTH_TO_BOTTOM = ("FLASH_", "BT_CFG", "BOOT_MODE")


def south_fanout(r, board):
    """Dog-bone fanout for the MCU's south-side pins whose loads sit on B.Cu
    (QSPI flash, boot straps): a stub straight out of each pad to a 0.45 mm via,
    even pins on a near row and odd pins on a far row so the stubs pass between
    the vias.  Escaping these at 0.5 mm pitch is otherwise very hard."""
    u1 = board.FindFootprintByReference("U1")
    done = 0
    for p in u1.Pads():
        net = p.GetNetname()
        if not net.startswith(SOUTH_TO_BOTTOM):
            continue
        c = rel(p.GetPosition())
        n, _ = _normal(c)
        tip = (c[0] + n[0] * 0.7375, c[1] + n[1] * 0.7375)
        rows = (0.9, 1.8) if int(p.GetNumber()) % 2 == 0 else (1.8, 0.9)
        for d in rows + (2.7,):
            v = (tip[0] + n[0] * d, tip[1] + n[1] * d)
            if r.via_ok(net, v, d=0.45, clearance=0.16) and \
                    r.path_free(net, "F.Cu", [tip, v], 0.15, clearance=0.16):
                r.track(net, "F.Cu", [c, tip, v], 0.15)
                r.via(net, v, d=0.45)
                done += 1
                break
        else:
            print(f"  south fanout: no via for U1 pin {p.GetNumber()} ({net})")
    return done


def build(board):
    r = Router(board)
    # bottom-side parts placed by pcb_layout (flash, straps, boot logic) are fixed obstacles
    r.bottom_boxes = [_courtyard(fp) for fp in board.GetFootprints()
                      if fp.IsFlipped() and fp.GetReference() not in L.DECOUPLING]
    zones(r)
    usb(r)
    usb_shield(r, board)
    dcdc(r)
    leftovers = mcu_power(r, board)
    print(f"south fanout vias: {south_fanout(r, board)}")
    bulk_caps(r, board, leftovers)
    n = plane_fanout(r, board)
    print(f"plane fanout vias: {n}")
    r.fill()
    return r
