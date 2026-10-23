"""Regenerate the schematic, normalise it with kicad-cli, run ERC and verify
that KiCad's netlist matches the intended connectivity in design.py.

Usage: python3 tools/build.py [--no-upgrade]
"""

import json
import os
import subprocess
import sys

import design
from sexpr import find, find_all, parse

HW = os.path.abspath(design.OUT)
PRO = os.path.join(HW, "USBAudioBridge.kicad_pro")
SCH = os.path.join(HW, "USBAudioBridge.kicad_sch")


def write_project_files():
    if not os.path.exists(PRO):
        with open(PRO, "w") as f:
            json.dump({"meta": {"filename": "USBAudioBridge.kicad_pro", "version": 3},
                       "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
                       "sheets": [], "boards": [], "text_variables": {}}, f, indent=2)
    with open(os.path.join(HW, "sym-lib-table"), "w") as f:
        f.write('(sym_lib_table\n  (version 7)\n'
                '  (lib (name "USBAudioBridge")(type "KiCad")'
                '(uri "${KIPRJMOD}/USBAudioBridge.kicad_sym")(options "")(descr "Project symbols"))\n)\n')


def write_fp_table():
    with open(os.path.join(HW, "fp-lib-table"), "w") as f:
        f.write('(fp_lib_table\n  (version 7)\n'
                '  (lib (name "USBAudioBridge")(type "KiCad")'
                '(uri "${KIPRJMOD}/USBAudioBridge.pretty")(options "")(descr "Project footprints"))\n)\n')


def run(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    return r.returncode, out


def kicad_netlist():
    path = os.path.join(HW, "build", "netlist.net")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    code, out = run("kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr",
                    "-o", path, SCH)
    if code:
        sys.exit(f"netlist export failed:\n{out}")
    with open(path) as f:
        root = parse(f.read())
    nets = {}
    for n in find_all(find(root, "nets"), "net"):
        name = find(n, "name")[1].split("/")[-1]
        nodes = {(find(x, "ref")[1], find(x, "pin")[1]) for x in find_all(n, "node")}
        nets[name] = nodes
    return nets


def compare(intended, actual, nc_pins):
    problems = []
    # map actual nets by their node sets
    for net, nodes in sorted(intended.items()):
        match = [a for a, an in actual.items() if an == nodes]
        if not match:
            best = max(actual.items(), key=lambda kv: len(kv[1] & nodes))
            problems.append(f"net {net}: expected {sorted(nodes)}\n"
                            f"    closest KiCad net {best[0]}: {sorted(best[1])}")
        elif net not in match:
            if not any(m.endswith(net) or m.startswith("Net-(") for m in match):
                problems.append(f"net {net}: matched KiCad net named {match}")
    intended_nodes = {n for nodes in intended.values() for n in nodes}
    for a, an in actual.items():
        if a.startswith("unconnected-") and an <= nc_pins:
            continue
        extra = an - intended_nodes
        if extra:
            problems.append(f"KiCad net {a} has unexpected nodes {sorted(extra)}")
    return problems


def main():
    d = design.main()
    write_project_files()
    write_fp_table()
    if "--no-upgrade" not in sys.argv:
        for s in [d.root] + d.sheets:
            code, out = run("kicad-cli", "sch", "upgrade", os.path.join(HW, s.filename))
            if code:
                sys.exit(f"upgrade failed for {s.filename}:\n{out}")
    problems = compare(d.intended_netlist(), kicad_netlist(), d.nc_pins())
    print(f"netlist check: {len(problems)} problem(s)")
    for p in problems:
        print("  " + p)
    rpt = os.path.join(HW, "build", "erc.rpt")
    code, out = run("kicad-cli", "sch", "erc", "--severity-all", "-o", rpt, SCH)
    print(out.splitlines()[-1] if out else "")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
