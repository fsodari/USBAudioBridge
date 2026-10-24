"""Scripted copper: zones, critical routes and plane fanout.

A small obstacle model (pads as rectangles/circles, vias as circles, tracks
as capsules, all in board-relative mm) lets the fanout code search for via
positions that keep clearance to every other net.  Signal nets are left for
Freerouting.
"""

import math

import pcbnew

import pcb_layout as L

CLEAR = 0.2          # clearance used for scripted copper (rule minimum is 0.15)
VIA_D, VIA_DRILL = 0.5, 0.3
PWR_VIA_D = 0.6
LAYERS = {"F.Cu": pcbnew.F_Cu, "In1.Cu": pcbnew.In1_Cu, "In2.Cu": pcbnew.In2_Cu,
          "B.Cu": pcbnew.B_Cu}
ALL = tuple(LAYERS)


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(L.ORIGIN[0] + x), mm(L.ORIGIN[1] + y))


def rel(v):
    return pcbnew.ToMM(v.x) - L.ORIGIN[0], pcbnew.ToMM(v.y) - L.ORIGIN[1]


# --- geometry ---------------------------------------------------------------

def _seg_point(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _seg_seg(a, b, c, d):
    def ccw(p, q, r):
        return (r[1] - p[1]) * (q[0] - p[0]) - (q[1] - p[1]) * (r[0] - p[0])
    if (ccw(a, b, c) * ccw(a, b, d) < 0) and (ccw(c, d, a) * ccw(c, d, b) < 0):
        return 0.0
    return min(_seg_point(*a, *c, *d), _seg_point(*b, *c, *d),
               _seg_point(*c, *a, *b), _seg_point(*d, *a, *b))


class Shape:
    """kind 'seg' (a, b, r) covers circles (a == b) and tracks; 'rect' (x1,y1,x2,y2)."""

    def __init__(self, kind, net, layers, **g):
        self.kind, self.net, self.layers, self.g = kind, net, set(layers), g

    def edges(self):
        x1, y1, x2, y2 = self.g["box"]
        c = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
        return list(zip(c, c[1:] + c[:1]))

    def dist(self, o):
        if self.kind == "rect" and o.kind == "rect":
            ax1, ay1, ax2, ay2 = self.g["box"]
            bx1, by1, bx2, by2 = o.g["box"]
            dx = max(0, max(ax1, bx1) - min(ax2, bx2))
            dy = max(0, max(ay1, by1) - min(ay2, by2))
            return math.hypot(dx, dy)
        if self.kind == "rect":
            return o.dist(self)
        a, b, r = self.g["a"], self.g["b"], self.g["r"]
        if o.kind == "seg":
            return _seg_seg(a, b, o.g["a"], o.g["b"]) - r - o.g["r"]
        x1, y1, x2, y2 = o.g["box"]
        if any(x1 <= p[0] <= x2 and y1 <= p[1] <= y2 for p in (a, b)):
            return -r
        return min(_seg_seg(a, b, e0, e1) for e0, e1 in o.edges()) - r


def seg(net, layers, a, b, width):
    return Shape("seg", net, layers, a=a, b=b, r=width / 2)


def circle(net, layers, c, d):
    return Shape("seg", net, layers, a=c, b=c, r=d / 2)


def rect(net, layers, box):
    return Shape("rect", net, layers, box=box)


def point_in_poly(p, poly):
    x, y = p
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def poly_margin(p, poly):
    """Distance from point to polygon boundary."""
    return min(_seg_point(*p, *a, *b) for a, b in zip(poly, poly[1:] + poly[:1]))


# --- the router ---------------------------------------------------------------

class Router:
    def __init__(self, board):
        self.board = board
        self.obs = []
        self.nets = {str(name): net for name, net in board.GetNetsByName().items()}
        for fp in board.GetFootprints():
            for p in fp.Pads():
                self.obs.append(self._pad_shape(p))
        # existing copper (e.g. after autorouting) is an obstacle too
        names = {v: k for k, v in LAYERS.items()}
        for t in board.GetTracks():
            net = t.GetNetname()
            if t.Type() == pcbnew.PCB_VIA_T:
                self.obs.append(circle(net, ALL, rel(t.GetPosition()),
                                       pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu))))
            elif t.GetLayer() in names:
                self.obs.append(seg(net, [names[t.GetLayer()]], rel(t.GetStart()),
                                    rel(t.GetEnd()), pcbnew.ToMM(t.GetWidth())))
        self.zones = []   # (layer, net, polygon) for keep-in tests

    def _pad_shape(self, p):
        layers = [n for n, lid in LAYERS.items() if p.IsOnLayer(lid)]
        if p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
            layers = list(ALL)
        bb = p.GetBoundingBox()
        x1, y1 = rel(bb.GetOrigin())
        x2, y2 = rel(bb.GetEnd())
        if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
            return circle(p.GetNetname(), layers, ((x1 + x2) / 2, (y1 + y2) / 2), x2 - x1)
        return rect(p.GetNetname(), layers, (x1, y1, x2, y2))

    def free(self, shape, clearance=CLEAR, ignore=()):
        for o in self.obs:
            if o.net == shape.net and shape.net:
                continue
            if o in ignore or not (o.layers & shape.layers):
                continue
            if shape.dist(o) < clearance - 1e-6:
                return False
        return True

    # copper creation
    def track(self, net, layer, pts, width):
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(pt(*a))
            t.SetEnd(pt(*b))
            t.SetWidth(mm(width))
            t.SetLayer(LAYERS[layer])
            t.SetNet(self.nets[net])
            self.board.Add(t)
            self.obs.append(seg(net, [layer], a, b, width))

    def via(self, net, c, d=VIA_D):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(pt(*c))
        v.SetWidth(mm(d))
        v.SetDrill(mm(VIA_DRILL))
        v.SetNet(self.nets[net])
        self.board.Add(v)
        self.obs.append(circle(net, ALL, c, d))

    def path_free(self, net, layer, pts, width, clearance=CLEAR):
        return all(self.free(seg(net, [layer], a, b, width), clearance)
                   for a, b in zip(pts, pts[1:]))

    def via_ok(self, net, c, d=VIA_D, keep_in=None, keep_out=(), clearance=CLEAR):
        if not self.free(circle(net, ALL, c, d), clearance):
            return False
        # drill holes need 0.25 mm between them even on the same net (0.3 for margin)
        for o in self.obs:
            if o.kind == "seg" and o.g["a"] == o.g["b"] and o.layers == set(ALL) and o.net == net:
                if math.hypot(o.g["a"][0] - c[0], o.g["a"][1] - c[1]) < VIA_DRILL + 0.3:
                    return False
        if not (0.6 < c[0] < L.W - 0.6 and 0.6 < c[1] < L.H - 0.6):
            return False
        if keep_in is not None and not (point_in_poly(c, keep_in) and
                                        poly_margin(c, keep_in) > d / 2 + 0.25):
            return False
        for poly in keep_out:
            if point_in_poly(c, poly) or poly_margin(c, poly) < d / 2 + 0.25:
                return False
        return True

    def zone(self, net, layer, poly, priority=0, clearance=0.2, min_w=0.2, solid=False):
        z = pcbnew.ZONE(self.board)
        z.SetLayer(LAYERS[layer])
        if net:
            z.SetNet(self.nets[net])
        ol = z.Outline()
        ol.NewOutline()
        for x, y in poly:
            ol.Append(mm(L.ORIGIN[0] + x), mm(L.ORIGIN[1] + y))
        z.SetAssignedPriority(priority)
        z.SetLocalClearance(mm(clearance))
        z.SetMinThickness(mm(min_w))
        z.SetThermalReliefGap(mm(0.25))
        z.SetThermalReliefSpokeWidth(mm(0.3))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL if solid else
                           pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        self.board.Add(z)
        self.zones.append((layer, net, poly))
        return z

    def fill(self):
        pcbnew.ZONE_FILLER(self.board).Fill(self.board.Zones())


def pad(board, ref, num):
    fp = board.FindFootprintByReference(ref)
    return next(p for p in fp.Pads() if p.GetNumber() == str(num))


def pad_xy(board, ref, num):
    return rel(pad(board, ref, num).GetPosition())
