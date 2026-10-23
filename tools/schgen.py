"""Small framework for generating KiCad schematics from a net-based description.

Every pin is connected by a short wire stub ending in a net label, a power
symbol, or a no-connect flag.  Connectivity therefore lives entirely in net
names, which keeps the generated sheets readable and lets the result be
cross-checked against KiCad's own netlist export.
"""

import copy
import math
import os
import uuid

from kilib import load_symbol, pins, prop
from sexpr import QStr, dumps, find, find_all

SCH_VERSION = "20260101"
PROJECT = "USBAudioBridge"
NS = uuid.UUID("9b0e7a52-31d4-4c55-9d6c-1f0f6a2d7a10")
GRID = 1.27


def uid(*parts):
    return QStr(str(uuid.uuid5(NS, "/".join(str(p) for p in parts))))


def snap(v):
    return round(round(v / GRID) * GRID, 4)


def font(size=1.27, **kw):
    f = ["font", ["size", size, size]]
    if kw.get("bold"):
        f.append(["bold", "yes"])
    return f


def effects(size=1.27, justify=None, hide=False, bold=False):
    e = ["effects", font(size, bold=bold)]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append(["hide", "yes"])
    return e


def rot(vx, vy, angle):
    """Rotate a screen-space vector CCW (as displayed) by angle degrees."""
    a = math.radians(angle)
    c, s = round(math.cos(a)), round(math.sin(a))
    return vx * c + vy * s, -vx * s + vy * c


def dir_angle(dx, dy):
    if abs(dx) > abs(dy):
        return 0 if dx > 0 else 180
    return 270 if dy > 0 else 90


class Part:
    def __init__(self, sheet, lib_id, ref, value, at, angle=0, unit=1, footprint="",
                 fields=None, text=None, dnp=False, in_bom=True):
        self.sheet = sheet
        self.lib_id = lib_id
        self.ref = ref
        self.value = value
        self.x, self.y = snap(at[0]), snap(at[1])
        self.angle = angle
        self.unit = unit
        self.footprint = footprint
        self.fields = fields or {}
        self.text = text  # override for ref/value placement: "right", "above", "left"
        self.dnp = dnp
        self.in_bom = in_bom
        self.sym = sheet.lib(lib_id)
        self.pins = [p for p in pins(self.sym) if p["unit"] in (0, unit)]
        self.conns = {}
        self.linked = set()  # pin numbers wired directly by Sheet.link()

    def pin(self, key):
        """Pins matching a number (preferred) or a unique visible name."""
        hits = [p for p in self.pins if p["number"] == key]
        if not hits:
            hits = [p for p in self.pins if p["name"] == key]
        if not hits:
            raise KeyError(f"{self.ref}: no pin {key!r}")
        return hits

    def pin_xy(self, p):
        vx, vy = rot(p["x"], -p["y"], self.angle)
        return snap(self.x + vx), snap(self.y + vy)

    def pin_out(self, p):
        a = math.radians(p["angle"])
        vx, vy = rot(-round(math.cos(a)), round(math.sin(a)), self.angle)
        return vx, vy

    def connect(self, mapping):
        for key, net in mapping.items():
            for p in self.pin(str(key)):
                self.conns[p["number"]] = net
                # hidden pins stacked on this one are wired by the same stub
                for q in self.pins:
                    if q["hidden"] and self.pin_xy(q) == self.pin_xy(p):
                        self.conns[q["number"]] = net
        return self


class Sheet:
    def __init__(self, design, name, filename, title, paper="A3"):
        self.design = design
        self.name = name
        self.filename = filename
        self.title = title
        self.paper = paper
        self.parts = []
        self.items = []  # extra sexpr items (wires, labels, text, power syms)
        self.symbols = {}
        self.pwr_count = 0
        self.uuid = uid("sheet-file", name)
        self.inst_uuid = uid("sheet-inst", name)  # uuid of the sheet symbol in root

    def lib(self, lib_id):
        if lib_id not in self.symbols:
            self.symbols[lib_id] = load_symbol(lib_id, self.design.lib_dir)
        return self.symbols[lib_id]

    def add(self, lib_id, ref, value, at, **kw):
        p = Part(self, lib_id, ref, value, at, **kw)
        self.parts.append(p)
        self.design.register(p)
        return p

    # ---- drawing helpers -------------------------------------------------
    def wire(self, x1, y1, x2, y2):
        self.items.append(["wire", ["pts", ["xy", x1, y1], ["xy", x2, y2]],
                           ["stroke", ["width", 0], ["type", "default"]],
                           ["uuid", uid(self.name, "w", x1, y1, x2, y2)]])

    def text(self, s, at, size=1.27, bold=False, justify="left"):
        self.items.append(["text", QStr(s), ["exclude_from_sim", "no"],
                           ["at", at[0], at[1], 0],
                           effects(size, justify=justify, bold=bold),
                           ["uuid", uid(self.name, "t", s[:40], at)]])

    def box(self, x1, y1, x2, y2, title=None):
        self.items.append(["rectangle", ["start", x1, y1], ["end", x2, y2],
                           ["stroke", ["width", 0.254], ["type", "dash"]],
                           ["fill", ["type", "none"]],
                           ["uuid", uid(self.name, "box", x1, y1)]])
        if title:
            self.text(title, (x1 + 1.27, y1 + 2.54), size=2.0, bold=True)

    def power(self, net, x, y, angle):
        lib_id = self.design.power_lib(net)
        self.lib(lib_id)
        self.pwr_count += 1
        is_flag = net == "PWR_FLAG"
        ref = f"#{'FLG' if is_flag else 'PWR'}{self.design.sheet_index(self) * 1000 + self.pwr_count:04d}"
        value = "PWR_FLAG" if is_flag else net
        self.items.append(self._symbol_sexpr(
            lib_id, ref, value, x, y, angle, 1, "", {}, power=True))

    def label(self, net, x, y, angle):
        # resolved in render(): the global/local choice depends on the final
        # set of global nets, which is only known once all sheets are built
        self.items.append(("LABEL", net, x, y, angle))

    def _label_sexpr(self, net, x, y, angle):
        just = "left bottom" if angle in (0, 90) else "right bottom"
        if net in self.design.globals:
            shape = self.design.globals[net]
            return ["global_label", QStr(net), ["shape", shape],
                               ["at", x, y, angle], ["fields_autoplaced", "yes"],
                               effects(justify=just.split()[0]),
                               ["uuid", uid(self.name, "gl", net, x, y)],
                               ["property", QStr("Intersheetrefs"), QStr("${INTERSHEET_REFS}"),
                                ["at", x, y, 0], effects(hide=True)]]
        return ["label", QStr(net), ["at", x, y, angle], effects(justify=just),
                ["uuid", uid(self.name, "lb", net, x, y)]]

    def no_connect(self, x, y):
        self.items.append(["no_connect", ["at", x, y], ["uuid", uid(self.name, "nc", x, y)]])

    def link(self, net, a, b, label=True, mid=None):
        """Wire pin a=(part, key) straight to pin b with a Manhattan route.

        The route leaves pin a along its outward direction, turns once at
        `mid` (x for horizontal pins, y for vertical pins; default halfway)
        and arrives at pin b.  With label=True the net name is placed on the
        first segment so the net can also be reached by label elsewhere.
        """
        pts = []
        for part, key in (a, b):
            p = part.pin(str(key))[0]
            part.connect({key: net})
            part.linked.add(p["number"])
            for q in part.pins:
                if q["hidden"] and part.pin_xy(q) == part.pin_xy(p):
                    part.linked.add(q["number"])
            pts.append((part.pin_xy(p), part.pin_out(p)))
        (xa, ya), (dxa, dya) = pts[0]
        (xb, yb), _ = pts[1]
        if xa == xb or ya == yb:
            path = [(xa, ya), (xb, yb)]
        elif dxa:
            xm = snap(mid if mid is not None else (xa + xb) / 2)
            path = [(xa, ya), (xm, ya), (xm, yb), (xb, yb)]
        else:
            ym = snap(mid if mid is not None else (ya + yb) / 2)
            path = [(xa, ya), (xa, ym), (xb, ym), (xb, yb)]
        for (x1, y1), (x2, y2) in zip(path, path[1:]):
            if (x1, y1) != (x2, y2):
                self.wire(x1, y1, x2, y2)
        if label:
            if net in self.design.power_nets:
                raise ValueError("link() is for signal nets")
            (x1, y1), (x2, y2) = path[0], path[1]
            self.label(net, snap((x1 + x2) / 2), snap((y1 + y2) / 2), 0)

    def tap(self, net, a, point):
        """Wire pin a=(part, key) straight to a point on an existing wire."""
        part, key = a
        p = part.pin(str(key))[0]
        part.connect({key: net})
        part.linked.add(p["number"])
        x, y = part.pin_xy(p)
        self.wire(x, y, snap(point[0]), snap(point[1]))

    def _junctions(self):
        wires = [(w[1][1][1], w[1][1][2], w[1][2][1], w[1][2][2])
                 for w in self.items if w[0] == "wire"]
        pin_pts = {part.pin_xy(p) for part in self.parts for p in part.pins}

        def on_segment(px, py, x1, y1, x2, y2):
            if x1 == x2 == px:
                return min(y1, y2) < py < max(y1, y2)
            if y1 == y2 == py:
                return min(x1, x2) < px < max(x1, x2)
            return False

        pts = {(w[0], w[1]) for w in wires} | {(w[2], w[3]) for w in wires}
        for px, py in sorted(pts):
            n = sum(((w[0], w[1]) == (px, py)) + ((w[2], w[3]) == (px, py)) for w in wires)
            n += 2 * sum(on_segment(px, py, *w) for w in wires)
            n += (px, py) in pin_pts
            if n >= 3:
                self.items.append(["junction", ["at", px, py], ["diameter", 0],
                                   ["color", 0, 0, 0, 0], ["uuid", uid(self.name, "j", px, py)]])

    def flag(self, net, at, angle=0):
        """PWR_FLAG tied to a power net: power symbol, short wire, flag."""
        x, y = snap(at[0]), snap(at[1])
        self.power(net, x, y, 0 if net != "GND" else 0)
        if net == "GND":
            self.wire(x, y, x, y - 2.54)
            self.power("PWR_FLAG", x, y - 2.54, 0)
        else:
            self.wire(x, y, x, y + 2.54)
            self.power("PWR_FLAG", x, y + 2.54, 180)

    # ---- rendering --------------------------------------------------------
    def _render_part(self, part):
        seen = set()
        for p in part.pins:
            if p["number"] in seen:
                continue
            seen.add(p["number"])
            net = part.conns.get(p["number"])
            if p["hidden"] or p["number"] in part.linked:
                continue
            if net is None:
                if p["type"] == "no_connect":
                    continue
                raise ValueError(f"{part.ref} pin {p['number']} ({p['name']}) unassigned")
            x, y = part.pin_xy(p)
            if net == "NC":
                self.no_connect(x, y)
                continue
            dx, dy = part.pin_out(p)
            stub = self.design.stub
            ex, ey = snap(x + dx * stub), snap(y + dy * stub)
            self.wire(x, y, ex, ey)
            ang = dir_angle(dx, dy)
            if net in self.design.power_nets:
                if net == "GND" or net in self.design.ground_nets:
                    pa = {270: 0, 90: 180, 180: 270, 0: 90}[ang]
                else:
                    pa = {90: 0, 270: 180, 180: 90, 0: 270}[ang]
                self.power(net, ex, ey, pa)
            else:
                self.label(net, ex, ey, ang)

    def _symbol_sexpr(self, lib_id, ref, value, x, y, angle, unit, footprint, fields,
                      power=False, part=None):
        sym = self.symbols[lib_id]
        key = (lib_id, ref, unit)
        props = []
        hide_value = False

        def place(name):
            # Field angles are stored relative to the symbol (KiCad swaps
            # horizontal/vertical for symbols rotated by 90/270), so the
            # library angle and justification carry over unchanged.
            lp = next((q for q in find_all(sym, "property") if q[1] == name), None)
            if lp is None:
                return x, y, 0, None
            at = find(lp, "at")
            vx, vy = rot(float(at[1]), -float(at[2]), angle)
            ta = float(at[3]) if len(at) > 3 else 0
            j = find(find(lp, "effects") or [], "justify")
            return snap(x + vx), snap(y + vy), ta, " ".join(j[1:]) if j else None

        # text modes describe the *displayed* layout; compensate for rotation
        quarter = angle % 180 == 90
        ta = 90 if quarter else 0
        # KiCad maps a field's justification through the symbol transform:
        # for 90 and 180 degree placements "left" in field space displays as "right".
        flip = angle % 360 in (90, 180)

        def j(display):
            if display in ("left", "right") and flip:
                return "right" if display == "left" else "left"
            return display

        if part is not None and isinstance(part.text, tuple):
            (rdx, rdy), (vdx, vdy), just = part.text
            rpos = (x + rdx, y + rdy, ta, j(just))
            vpos = (x + vdx, y + vdy, ta, j(just))
        elif part is not None and part.text:
            mode = part.text
            jl, jr = j("left"), j("right")
            if mode == "right":
                rpos = (x + 2.54, y - 1.27, ta, jl)
                vpos = (x + 2.54, y + 1.27, ta, jl)
            elif mode == "left":
                rpos = (x - 2.54, y - 1.27, ta, jr)
                vpos = (x - 2.54, y + 1.27, ta, jr)
            elif mode == "above":
                rpos = (x, y - 3.81, ta, None)
                vpos = (x, y - 2.03, ta, None)
            elif mode == "below":
                rpos = (x, y + 2.03, ta, None)
                vpos = (x, y + 3.81, ta, None)
            else:
                raise ValueError(mode)
        elif power and quarter:
            rpos = place("Reference")
            px, py, _, _ = place("Value")
            # anchor the text at the symbol tip and let it run away from the symbol
            display = "left" if px > x else "right"
            vpos = (px, py + 0.4, 90, j(display))
            # sideways grounds are unambiguous without text and crowd adjacent pins
            hide_value = lib_id == "power:GND"
        else:
            rpos = place("Reference")
            vpos = place("Value")

        def prop_expr(name, val, pos, hide):
            px, py, pa, just = pos
            return ["property", QStr(name), QStr(val), ["at", round(px, 4), round(py, 4), pa],
                    effects(justify=just, hide=hide)]

        ref_hidden = power
        props.append(prop_expr("Reference", ref, rpos, ref_hidden))
        props.append(prop_expr("Value", value, vpos, hide_value))
        props.append(prop_expr("Footprint", footprint, (x, y, 0, None), True))
        ds = fields.get("Datasheet", prop(sym, "Datasheet") or "")
        props.append(prop_expr("Datasheet", ds, (x, y, 0, None), True))
        desc = prop(sym, "Description") or ""
        props.append(prop_expr("Description", desc, (x, y, 0, None), True))
        for k, v in fields.items():
            if k != "Datasheet":
                props.append(prop_expr(k, v, (x, y, 0, None), True))

        sym_pins = [p for p in pins(sym) if p["unit"] in (0, unit)]
        numbers = []
        for p in sym_pins:
            if p["number"] not in numbers:
                numbers.append(p["number"])
        path = f"/{self.design.root_uuid}/{self.inst_uuid}"
        dnp = part.dnp if part is not None else False
        in_bom = (not power) and (part is None or part.in_bom)
        return (["symbol", ["lib_id", QStr(lib_id)], ["at", x, y, angle], ["unit", unit],
                 ["exclude_from_sim", "no"], ["in_bom", "yes" if in_bom else "no"],
                 ["on_board", "no" if power else "yes"], ["dnp", "yes" if dnp else "no"],
                 ["uuid", uid(self.name, *key, x, y)]]
                + props
                + [["pin", QStr(n), ["uuid", uid(self.name, *key, "pin", n)]] for n in numbers]
                + [["instances", ["project", QStr(PROJECT),
                                  ["path", QStr(path), ["reference", QStr(ref)], ["unit", unit]]]]])

    def render(self):
        body = []
        for part in self.parts:
            self._render_part(part)
            body.append(self._symbol_sexpr(part.lib_id, part.ref, part.value, part.x, part.y,
                                           part.angle, part.unit, part.footprint,
                                           part.fields, part=part))
        self.items = [self._label_sexpr(*i[1:]) if i[0] == "LABEL" else i for i in self.items]
        self._junctions()
        lib_syms = []
        for lib_id, s in self.symbols.items():
            lib_syms.append(s)
        d = self.design
        tb = ["title_block", ["title", QStr(d.title)], ["date", QStr(d.date)],
              ["rev", QStr(d.rev)], ["comment", 1, QStr(self.title)]]
        if d.author:
            tb.append(["comment", 2, QStr(d.author)])
        doc = (["kicad_sch", ["version", SCH_VERSION], ["generator", QStr("eeschema")],
                ["generator_version", QStr("10.0")], ["uuid", self.uuid],
                ["paper", QStr(self.paper)], tb, ["lib_symbols"] + lib_syms]
               + self.items + body)
        if self is d.root:
            doc += d.sheet_symbols()
            doc.append(["sheet_instances", ["path", QStr("/"), ["page", QStr("1")]]])
        doc.append(["embedded_fonts", "no"])
        return dumps(doc) + "\n"


class Design:
    def __init__(self, out_dir, title, rev, date, author=""):
        self.out_dir = out_dir
        self.lib_dir = out_dir
        self.title = title
        self.rev = rev
        self.date = date
        self.author = author
        self.sheets = []
        self.root = None
        self.globals = {}       # net -> label shape
        self.power_nets = {}    # net -> lib_id
        self.ground_nets = set()
        self.refs = {}
        self.stub = 2.54

    @property
    def root_uuid(self):
        return self.root.uuid

    def power_lib(self, net):
        if net == "PWR_FLAG":
            return "power:PWR_FLAG"
        return self.power_nets[net]

    def add_root(self, title):
        self.root = Sheet(self, "root", PROJECT + ".kicad_sch", title)
        return self.root

    def add_sheet(self, name, filename, title, paper="A3"):
        s = Sheet(self, name, filename, title, paper)
        self.sheets.append(s)
        return s

    def sheet_index(self, sheet):
        return 0 if sheet is self.root else self.sheets.index(sheet) + 1

    def register(self, part):
        key = (part.ref, part.unit)
        if key in self.refs:
            raise ValueError(f"duplicate {part.ref} unit {part.unit}")
        self.refs[key] = part

    def sheet_symbols(self, x0=30.48, y0=50.8, w=50.8, h=20.32, cols=3):
        out = []
        for i, s in enumerate(self.sheets):
            x = x0 + (i % cols) * (w + 20.32)
            y = y0 + (i // cols) * (h + 17.78)
            out.append(["sheet", ["at", x, y], ["size", w, h],
                        ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
                        ["dnp", "no"], ["fields_autoplaced", "yes"],
                        ["stroke", ["width", 0.1524], ["type", "solid"]],
                        ["fill", ["color", 0, 0, 0, 0.0]],
                        ["uuid", s.inst_uuid],
                        ["property", QStr("Sheetname"), QStr(s.title),
                         ["at", x, round(y - 0.7116, 4), 0], effects(justify="left bottom")],
                        ["property", QStr("Sheetfile"), QStr(s.filename),
                         ["at", x, round(y + h + 0.5846, 4), 0],
                         effects(justify="left top")],
                        ["instances", ["project", QStr(PROJECT),
                                       ["path", QStr(f"/{self.root_uuid}"),
                                        ["page", QStr(str(i + 2))]]]]])
        return out

    def intended_netlist(self):
        nets = {}
        for part in self.refs.values():
            if part.ref.startswith("#"):
                continue
            for num, net in part.conns.items():
                if net == "NC":
                    continue
                nets.setdefault(net, set()).add((part.ref, num))
        return nets

    def nc_pins(self):
        out = {(p.ref, num) for p in self.refs.values() for num, net in p.conns.items()
               if net == "NC"}
        # pins of type no_connect are left unassigned on purpose
        for p in self.refs.values():
            out |= {(p.ref, q["number"]) for q in p.pins if q["type"] == "no_connect"}
        return out

    def write(self, mcu_prefix=None):
        os.makedirs(self.out_dir, exist_ok=True)
        if mcu_prefix:
            # every signal on the MCU uses a global label: consistent style,
            # and global flags never collide with local text on adjacent pins
            for part in self.refs.values():
                if part.lib_id.startswith(mcu_prefix):
                    for net in part.conns.values():
                        if net != "NC" and net not in self.power_nets:
                            self.globals.setdefault(net, "bidirectional")
        for s in [self.root] + self.sheets:
            with open(os.path.join(self.out_dir, s.filename), "w") as f:
                f.write(s.render())
