"""Design rules, net classes and stackup for JLCPCB 4-layer (JLC04161H-3313).

JLCPCB 4-layer capabilities: 0.09 mm min track/space, 0.3 mm min via drill
(0.2 mm at extra cost), 0.15 mm min via annular ring for free vias, 0.3 mm
copper to routed edge.  The rules below keep comfortable margin above those.

USB 90 ohm differential on F.Cu over the In1.Cu GND plane, 0.0994 mm 3313
prepreg (er ~4.1): 0.20 mm width / 0.15 mm gap by microstrip estimate.
Confirm with JLCPCB's impedance calculator when ordering with impedance
control.
"""

import json

STACKUP = """		(stackup
			(layer "F.SilkS" (type "Top Silk Screen"))
			(layer "F.Paste" (type "Top Solder Paste"))
			(layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))
			(layer "F.Cu" (type "copper") (thickness 0.035))
			(layer "dielectric 1" (type "prepreg") (color "FR4 natural") (thickness 0.0994)
				(material "3313") (epsilon_r 4.1) (loss_tangent 0.02))
			(layer "In1.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 2" (type "core") (color "FR4 natural") (thickness 1.265)
				(material "FR4") (epsilon_r 4.6) (loss_tangent 0.02))
			(layer "In2.Cu" (type "copper") (thickness 0.0152))
			(layer "dielectric 3" (type "prepreg") (color "FR4 natural") (thickness 0.0994)
				(material "3313") (epsilon_r 4.1) (loss_tangent 0.02))
			(layer "B.Cu" (type "copper") (thickness 0.035))
			(layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))
			(layer "B.Paste" (type "Bottom Solder Paste"))
			(layer "B.SilkS" (type "Bottom Silk Screen"))
			(copper_finish "ENIG")
			(dielectric_constraints no)
		)
"""

POWER_NETS = ["GND", "VBUS", "+5V", "+3V3", "+1V1", "+3V3_CLK", "DCDC_LP"]
CLOCK_NETS = ["MCLK_SAI", "MCLK_GPT", "JC_RX_MCLK", "JC_TX_MCLK", "*CLK_Y*", "XO_OUT",
              "CLK_BUF_IN"]


def _netclass(name, track, clearance, via_d=0.5, via_drill=0.3, dp_w=None, dp_gap=None,
              priority=0):
    return {
        "name": name, "priority": priority,
        "track_width": track, "clearance": clearance,
        "via_diameter": via_d, "via_drill": via_drill,
        "microvia_diameter": 0.3, "microvia_drill": 0.1,
        "diff_pair_width": dp_w or track, "diff_pair_gap": dp_gap or 0.2,
        "diff_pair_via_gap": 0.25, "bus_width": 12, "wire_width": 6, "line_style": 0,
        "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
        "tuning_profile": "",
    }


def update_project(pro_path):
    d = json.load(open(pro_path))
    d.setdefault("board", {})["design_settings"] = {
        "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2,
                     "silk_line_width": 0.12, "silk_text_size_h": 0.8,
                     "silk_text_size_v": 0.8, "silk_text_thickness": 0.12,
                     "zones": {"min_clearance": 0.2}},
        "rules": {
            "min_clearance": 0.127, "min_track_width": 0.127, "min_connection": 0.0,
            "min_via_diameter": 0.45, "min_through_hole_diameter": 0.3,
            "min_via_annular_width": 0.075, "min_hole_clearance": 0.15,
            "min_hole_to_hole": 0.25, "min_copper_edge_clearance": 0.3,
            "min_silk_clearance": 0.0, "min_text_height": 0.8,
            "min_text_thickness": 0.12, "min_microvia_diameter": 0.2,
            "min_microvia_drill": 0.1, "max_error": 0.005, "min_resolved_spokes": 1,
            "solder_mask_to_copper_clearance": 0.0, "min_groove_width": 0.0,
            "use_height_for_length_calcs": True,
        },
        "track_widths": [0.0, 0.15, 0.2, 0.3, 0.4, 0.6],
        "via_dimensions": [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.5, "drill": 0.3},
                           {"diameter": 0.6, "drill": 0.3}],
        "diff_pair_dimensions": [{"gap": 0.0, "via_gap": 0.0, "width": 0.0},
                                 {"gap": 0.15, "via_gap": 0.25, "width": 0.2}],
        "drc_exclusions": [],
        "meta": {"version": 2},
    }
    patterns = [{"netclass": "Power", "pattern": n} for n in POWER_NETS]
    patterns += [{"netclass": "USB90", "pattern": n} for n in ("USB_DP", "USB_DN")]
    patterns += [{"netclass": "Clock", "pattern": n} for n in CLOCK_NETS]
    d["net_settings"] = {
        "classes": [
            _netclass("Default", 0.15, 0.15, priority=2147483647),
            _netclass("Power", 0.3, 0.2, via_d=0.6, priority=0),
            _netclass("USB90", 0.2, 0.2, dp_w=0.2, dp_gap=0.15, priority=1),
            _netclass("Clock", 0.2, 0.2, priority=2),
        ],
        "meta": {"version": 5},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": patterns,
    }
    with open(pro_path, "w") as f:
        json.dump(d, f, indent=2)


DRU = """(version 1)
# GCT USB4105 land pattern: GND pads sit ~0.18 mm from the plastic locating-peg
# NPTH holes. This is the manufacturer's recommended footprint; allow it there only.
# The board-level minimum is 0.15 mm; 0.25 mm applies everywhere else.
(rule "hole clearance"
  (constraint hole_clearance (min 0.25))
  (condition "!(A.memberOfFootprint('J101') && B.memberOfFootprint('J101'))"))
"""


def write_dru(path):
    with open(path, "w") as f:
        f.write(DRU)


def insert_stackup(pcb_path):
    text = open(pcb_path).read()
    if "(stackup" not in text:
        text = text.replace("\t(setup\n", "\t(setup\n" + STACKUP, 1)
        open(pcb_path, "w").write(text)
