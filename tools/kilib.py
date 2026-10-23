"""Load KiCad library symbols (flattening `extends`) and report pin geometry."""

import copy
import os

from sexpr import QStr, find, find_all, parse

SYSTEM_SYMBOLS = "/usr/share/kicad/symbols"
_cache = {}


def _load_lib(path):
    if path not in _cache:
        with open(path) as f:
            root = parse(f.read())
        _cache[path] = {s[1]: s for s in find_all(root, "symbol")}
    return _cache[path]


def lib_path(lib, project_dir=None):
    if project_dir:
        p = os.path.join(project_dir, lib + ".kicad_sym")
        if os.path.exists(p):
            return p
    return os.path.join(SYSTEM_SYMBOLS, lib + ".kicad_sym")


def load_symbol(lib_id, project_dir=None):
    """Return a flattened symbol definition renamed to `lib_id`."""
    lib, name = lib_id.split(":", 1)
    syms = _load_lib(lib_path(lib, project_dir))
    sym = copy.deepcopy(syms[name])
    ext = find(sym, "extends")
    if ext:
        parent = copy.deepcopy(syms[ext[1]])
        # child supplies properties; parent supplies body (sub-symbols, pin settings)
        child_props = {p[1]: p for p in find_all(sym, "property")}
        merged = [parent[0], QStr(name)]
        for item in parent[2:]:
            if isinstance(item, list) and item[0] == "property" and item[1] in child_props:
                merged.append(child_props.pop(item[1]))
            elif isinstance(item, list) and item[0] == "symbol":
                item[1] = QStr(item[1].replace(ext[1], name, 1))
                merged.append(item)
            else:
                merged.append(item)
        # properties that exist only on the child go before the first sub-symbol
        idx = next(i for i, x in enumerate(merged) if isinstance(x, list) and x[0] == "symbol")
        for p in child_props.values():
            merged.insert(idx, p)
        sym = merged
    sym[1] = QStr(lib_id)
    return sym


def pins(sym):
    """List of dicts: number, name, type, x, y (lib coords, Y up), angle, unit."""
    out = []
    for sub in find_all(sym, "symbol"):
        # sub-symbol names end in _<unit>_<style>
        unit = int(sub[1].rsplit("_", 2)[-2])
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            out.append(
                {
                    "type": p[1],
                    "number": find(p, "number")[1],
                    "name": find(p, "name")[1],
                    "x": float(at[1]),
                    "y": float(at[2]),
                    "angle": float(at[3]) if len(at) > 3 else 0.0,
                    "unit": unit,
                    "hidden": "hide" in p or any(
                        isinstance(x, list) and x[0] == "hide" for x in p
                    ),
                }
            )
    return out


def prop(sym, key):
    p = next((p for p in find_all(sym, "property") if p[1] == key), None)
    return p[2] if p else None
