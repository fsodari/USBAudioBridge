"""Project symbol library: i.MX RT1010 (80-LQFP) and custom power symbols.

Pin numbers come from the i.MX RT1010 data sheet (IMXRT1010CEC Rev. 0),
Tables 51/52 and Figure 36.
"""

import copy
import math

from kilib import load_symbol
from sexpr import QStr, dumps, find, find_all

RT_NAME = "MIMXRT1011DAE5A"

# Each unit: (unit name, left pins, right pins); None inserts a blank row.
# Pin tuple: (number, name, electrical type)
PWR, PWO, IN, OUT, BID, PAS = "power_in", "power_out", "input", "output", "bidirectional", "passive"
RT_UNITS = [
    ("Power",
     [("18", "DCDC_IN", PWR), ("17", "DCDC_IN_Q", PWR), ("15", "DCDC_PSWITCH", IN), None,
      ("39", "VDD_HIGH_IN", PWR), ("25", "VDD_SNVS_IN", PWR), ("42", "VDDA_ADC_3P3", PWR), None,
      ("7", "NVCC_GPIO", PWR), ("50", "NVCC_GPIO", PWR), ("63", "NVCC_GPIO", PWR),
      ("71", "NVCC_GPIO", PWR), None,
      ("16", "VSS", PWR), ("30", "VSS", PWR), ("54", "VSS", PWR), ("78", "VSS", PWR)],
     [("19", "DCDC_LP", PAS), ("20", "DCDC_GND", PWR), None,
      ("14", "VDD_SOC_IN/DCDC_SENSE", PWR), ("53", "VDD_SOC_IN", PWR), ("77", "VDD_SOC_IN", PWR),
      None,
      ("35", "VDD_HIGH_CAP", PWO), ("40", "NVCC_PLL", PWO), ("26", "VDD_SNVS_CAP", PWO),
      ("31", "VDD_USB_CAP", PWO), None,
      ("41", "VSSA_ADC_3P3", PWR), ("34", "NGND_KEL0", PWR)]),
    ("System",
     [("22", "POR_B", IN), ("21", "ONOFF", IN), ("23", "TEST_MODE", IN),
      ("24", "PMIC_ON_REQ", OUT), None,
      ("37", "XTALI", PAS), ("38", "XTALO", PAS), None,
      ("27", "RTC_XTALI", PAS), ("28", "RTC_XTALO", PAS)],
     [("33", "USB_OTG1_DP", BID), ("32", "USB_OTG1_DN", BID), None,
      ("29", "USB_OTG1_VBUS", PWR), ("36", "USB_OTG1_CHD_B", PAS)]),
    ("GPIO",
     [("13", "GPIO_00", BID), ("12", "GPIO_01", BID), ("11", "GPIO_02", BID),
      ("10", "GPIO_03", BID), ("9", "GPIO_04", BID), ("8", "GPIO_05", BID),
      ("6", "GPIO_06", BID), ("5", "GPIO_07", BID), ("4", "GPIO_08", BID),
      ("3", "GPIO_09", BID), ("2", "GPIO_10", BID), ("1", "GPIO_11", BID),
      ("80", "GPIO_12", BID), ("79", "GPIO_13", BID)],
     [("60", "GPIO_AD_00", BID), ("59", "GPIO_AD_01", BID), ("58", "GPIO_AD_02", BID),
      ("57", "GPIO_AD_03", BID), ("56", "GPIO_AD_04", BID), ("55", "GPIO_AD_05", BID),
      ("52", "GPIO_AD_06", BID), ("51", "GPIO_AD_07", BID), ("49", "GPIO_AD_08", BID),
      ("48", "GPIO_AD_09", BID), ("47", "GPIO_AD_10", BID), ("46", "GPIO_AD_11", BID),
      ("45", "GPIO_AD_12", BID), ("44", "GPIO_AD_13", BID), ("43", "GPIO_AD_14", BID)]),
    ("FlexSPI",
     [("76", "GPIO_SD_00", BID), ("75", "GPIO_SD_01", BID), ("74", "GPIO_SD_02", BID),
      ("73", "GPIO_SD_03", BID), ("72", "GPIO_SD_04", BID), ("70", "GPIO_SD_05", BID),
      ("69", "GPIO_SD_06", BID)],
     [("68", "GPIO_SD_07", BID), ("67", "GPIO_SD_08", BID), ("66", "GPIO_SD_09", BID),
      ("65", "GPIO_SD_10", BID), ("64", "GPIO_SD_11", BID), ("62", "GPIO_SD_12", BID),
      ("61", "GPIO_SD_13", BID)]),
]


def _fx(size=1.27):
    return ["effects", ["font", ["size", size, size]]]


def _prop(name, value, at, hide=False, justify=None):
    e = _fx()
    if justify:
        e.append(["justify", justify])
    if hide:
        e.append(["hide", "yes"])
    return ["property", QStr(name), QStr(value), ["at", at[0], at[1], 0], e]


def _pin(num, name, etype, x, y, angle):
    return ["pin", etype, "line", ["at", x, y, angle], ["length", 2.54],
            ["name", QStr(name), _fx()], ["number", QStr(num), _fx()]]


def rt1010_symbol():
    all_names = [p[1] for u in RT_UNITS for side in u[1:] for p in side if p]
    assert len({p[0] for u in RT_UNITS for side in u[1:] for p in side if p}) == 80
    units = []
    max_h = 0
    for i, (uname, left, right) in enumerate(RT_UNITS, start=1):
        ln = max((len(p[1]) for p in left if p), default=0)
        rn = max((len(p[1]) for p in right if p), default=0)
        w = math.ceil(((ln + rn) * 1.0 + 6) / 5.08) * 5.08
        rows = max(len(left), len(right))
        top = math.ceil((rows - 1) / 2) * 2.54
        h_top, h_bot = top + 2.54, top - (rows - 1) * 2.54 - 2.54
        max_h = max(max_h, h_top)
        body = [["rectangle", ["start", -w / 2, h_top], ["end", w / 2, h_bot],
                 ["stroke", ["width", 0.254], ["type", "default"]],
                 ["fill", ["type", "background"]]],
                ["text", QStr(uname), ["at", 0, h_bot + 1.27, 0], _fx()]]
        for side, x, ang in ((left, -w / 2 - 2.54, 0), (right, w / 2 + 2.54, 180)):
            for r, p in enumerate(side):
                if p:
                    body.append(_pin(p[0], p[1], p[2], round(x, 4), round(top - r * 2.54, 4), ang))
        units.append(["symbol", QStr(f"{RT_NAME}_{i}_1")] + body)
    sym = (["symbol", QStr(RT_NAME), ["pin_names", ["offset", 1.016]],
            ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            _prop("Reference", "U", (0, max_h + 1.27), justify="left"),
            _prop("Value", RT_NAME, (0, max_h + 3.81), justify="left"),
            _prop("Footprint", "Package_QFP:LQFP-80_12x12mm_P0.5mm", (0, 0), hide=True),
            _prop("Datasheet", "https://www.nxp.com/docs/en/data-sheet/IMXRT1010CEC.pdf", (0, 0), hide=True),
            _prop("Description", "i.MX RT1010 crossover MCU, Cortex-M7 500 MHz, 128 KB OCRAM, USB HS OTG, LQFP-80", (0, 0), hide=True),
            _prop("MPN", RT_NAME, (0, 0), hide=True),
            _prop("Manufacturer", "NXP", (0, 0), hide=True),
            _prop("ki_keywords", "NXP iMXRT RT1010 RT1011 Cortex-M7", (0, 0), hide=True),
            _prop("ki_fp_filters", "LQFP*12x12mm*P0.5mm*", (0, 0), hide=True)]
           + units + [["embedded_fonts", "no"]])
    return sym


def power_symbol(net, base="power:+3V3"):
    s = copy.deepcopy(load_symbol(base))
    old = base.split(":")[1]
    s[1] = QStr(net)
    for p in find_all(s, "property"):
        if p[1] == "Value":
            p[2] = QStr(net)
        if p[1] == "Description":
            p[2] = QStr(f'Power symbol creates a global label with name "{net}"')
    for sub in find_all(s, "symbol"):
        sub[1] = QStr(sub[1].replace(old, net, 1))
    return s


def write_library(path):
    lib = ["kicad_symbol_lib", ["version", "20251024"], ["generator", QStr("kicad_symbol_editor")],
           ["generator_version", QStr("10.0")],
           rt1010_symbol(), power_symbol("+3V3_CLK")]
    with open(path, "w") as f:
        f.write(dumps(lib) + "\n")
