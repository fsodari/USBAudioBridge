"""USB Audio Bridge schematic description.

Run `tools/build.sh` (or `python3 tools/design.py`) to regenerate the KiCad
schematic in hardware/.  Net names are the source of truth: every pin is
attached to a named net, a power net, or "NC".
"""

import os
import sys

import footprints
from projlib import RT_NAME, write_library
from schgen import Design

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "hardware")

RT = f"USBAudioBridge:{RT_NAME}"

R0402 = "Resistor_SMD:R_0402_1005Metric"
C0402 = "Capacitor_SMD:C_0402_1005Metric"
C0603 = "Capacitor_SMD:C_0603_1608Metric"
C0805 = "Capacitor_SMD:C_0805_2012Metric"
LED0603 = "LED_SMD:LED_0603_1608Metric"
TP_FP = "TestPoint:TestPoint_Pad_D1.0mm"
PMOD_FP = "USBAudioBridge:PMOD_Peripheral_2x06_P2.54mm_Horizontal"
SW_FP = "Button_Switch_SMD:SW_SPST_PTS810"

CAP_FP = {"0402": C0402, "0603": C0603, "0805": C0805}


# ---------------------------------------------------------------------------
# helpers


def cap(sh, ref, value, at, top, bot="GND", size="0402", spec="X5R", dnp=False):
    """Vertical capacitor: pin 1 on top."""
    return sh.add("Device:C", ref, value, at, footprint=CAP_FP[size], text="right",
                  fields={"Spec": f"{spec} {size}"}, dnp=dnp).connect({"1": top, "2": bot})


def res(sh, ref, value, at, n1, n2, horizontal=False, spec="1% 0402", dnp=False):
    """Resistor; vertical has pin 1 on top, horizontal has pin 1 on the left."""
    return sh.add("Device:R", ref, value, at, angle=90 if horizontal else 0,
                  footprint=R0402, text="above" if horizontal else "right",
                  fields={"Spec": spec}, dnp=dnp).connect({"1": n1, "2": n2})


def led(sh, ref, value, at, anode, cathode="GND"):
    return sh.add("Device:LED", ref, value, at, angle=90, footprint=LED0603, text="right",
                  fields={"Spec": "0603, Vf ~2 V"}).connect({"A": anode, "K": cathode})


def testpoint(sh, ref, net, at):
    return sh.add("Connector:TestPoint", ref, net, at, footprint=TP_FP, in_bom=False,
                  text=((1.905, -4.06), (1.905, -2.29), "left")).connect({"1": net})


def cap_row(sh, x, y, specs, pitch=10.16):
    """Place a row of decoupling capacitors left to right."""
    for i, s in enumerate(specs):
        cap(sh, *s[:2], (x + i * pitch, y), *s[2:])


# ---------------------------------------------------------------------------


def build():
    d = Design(OUT, "USB Audio Bridge", "A", "2026-10-22")
    d.power_nets = {
        "GND": "power:GND",
        "VBUS": "power:VBUS",
        "+5V": "power:+5V",
        "+3V3": "power:+3V3",
        "+1V1": "power:+1V1",
        "+3V3_CLK": "USBAudioBridge:+3V3_CLK",
    }
    g = {}
    for n in ["USB_DP", "USB_DN", "POR_B", "MCLK_SAI", "MCLK_GPT",
              "I2S_TX_BCLK", "I2S_TX_LRCLK", "I2S_TX_DATA", "I2S_RX_BCLK", "I2S_RX_LRCLK",
              "I2S_RX_DATA", "SPI_CS", "SPI_MOSI", "SPI_MISO", "SPI_SCK",
              "PMOD_INT", "PMOD_RST", "PMOD_GPIO0", "PMOD_GPIO1"]:
        g[n] = "bidirectional"
    d.globals = g

    root = d.add_root("Overview")
    s_pwr = d.add_sheet("power", "power_usb.kicad_sch", "USB-C & Power")
    s_mp = d.add_sheet("mcu_power", "mcu_power.kicad_sch", "MCU Power")
    s_sys = d.add_sheet("mcu_system", "mcu_system.kicad_sch", "MCU System, Clocks & Reset")
    s_boot = d.add_sheet("boot_flash", "boot_flash.kicad_sch", "Boot Flash & Boot Mode")
    s_io = d.add_sheet("mcu_io", "mcu_io.kicad_sch", "MCU I/O & Debug")
    s_aud = d.add_sheet("audio_pmod", "audio_pmod.kicad_sch", "Audio Clock & PMOD")

    sheet_root(root)
    sheet_power(s_pwr)
    sheet_mcu_power(s_mp)
    sheet_mcu_system(s_sys)
    sheet_boot(s_boot)
    sheet_io(s_io)
    sheet_audio(s_aud)
    return d


# ---------------------------------------------------------------------------


def sheet_root(sh):
    sh.text("USB Audio Bridge", (30.48, 30.48), size=5.0, bold=True)
    sh.text("NXP i.MX RT1010 USB 2.0 HS asynchronous audio device bridging to an Arty A7 "
            "FPGA board over two PMOD ports (JB: I2S, JC: SPI + GPIO).", (30.48, 38.1), size=1.8)
    notes = (
        "DESIGN NOTES\n"
        "Power: USB VBUS (PTC fused) -> AP7361C 3.3 V main rail; LP5907 3.3 V low-noise rail "
        "(+3V3_CLK) for the audio clock.\n"
        "  RT1010 internal DC-DC (4.7 uH) generates the 1.1 V VDD_SOC rail. VDD_SNVS_IN is tied to "
        "3.3 V (no backup battery).\n"
        "  Arty PMOD VCC (pins 6/12) is NOT connected to 3.3 V: JP601 is an open solder jumper. "
        "Grounds are common.\n"
        "Clocks: 24.000 MHz crystal (system/USB PLL), 32.768 kHz crystal (RTC), 24.576 MHz XO "
        "(audio master, Epson SG-210STF) -> CDCV304 1:4 buffer:\n"
        "  Y0 -> GPIO_08 SAI1_MCLK (input, GPR1 SAI1_MCLK_DIR=0, SAI1_MCLK1_SEL=011)\n"
        "  Y1 -> GPIO_AD_03 GPT2_CLK (counts MCLK between USB SOFs for the async feedback "
        "endpoint; needs ipg_clk >= 98.4 MHz)\n"
        "  Y2/Y3 -> PMOD JB1/JB7, the MCLK pin of each I2S row.  RT1010 SAI1 is I2S clock master for "
        "both buses.\n"
        "PMOD JB matches the Digilent Pmod I2S2 (JB1/JB3 are Artix-7 clock-capable pins): top row (1-4) MCLK/LRCK/SCLK/SDIN carries FPGA -> "
        "RT1010 audio, bottom row (7-10) MCLK/LRCK/SCLK/SDOUT carries RT1010 -> FPGA audio.\n"
        "Boot: BOOT_MODE[1:0]=10 (internal boot, FlexSPI-A QSPI NOR) by default. Hold BOOT and "
        "press RESET for 01 (serial downloader over USB).\n"
        "Debug: MCU-Link 10-pin Cortex debug header (SWD + SWO), 3-pin LPUART1 console header.\n"
        "\n"
        "PIN MAP\n"
        "  GPIO_01..03  SAI1 RX BCLK/SYNC/DATA0   (I2S input bus, FPGA -> RT1010)\n"
        "  GPIO_04,06,07 SAI1 TX DATA0/BCLK/SYNC  (I2S output bus, RT1010 -> FPGA)\n"
        "  GPIO_08      SAI1_MCLK in              GPIO_00, 05, 13, AD_08, AD_14  spare (NC)\n"
        "  GPIO_09/10   LPUART1 RX/TX             GPIO_11/12  LED1/LED2\n"
        "  GPIO_AD_04/05/06 LPSPI1 SDO/PCS0/SCK   GPIO_SD_05  LPSPI1 SDI (daisy select 1)\n"
        "  GPIO_AD_00 PMOD_INT, AD_07 PMOD_RST, AD_01/02 PMOD_GPIO0/1 (LPI2C2 or LPUART4 capable)\n"
        "  GPIO_AD_09..13 SWO/TDI/JTAG_MOD/SWCLK/SWDIO\n"
        "  GPIO_SD_06..11 FlexSPI-A QSPI flash    GPIO_SD_00..04 BT_CFG / BOOT_MODE straps"
    )
    sh.text(notes, (30.48, 152.4), size=1.6)
    for i, ref in enumerate(("H1", "H2")):
        sh.add("Mechanical:MountingHole", ref, "MountingHole_M3", (215.9 + i * 12.7, 63.5),
               footprint="MountingHole:MountingHole_3.2mm_M3", in_bom=False)
    sh.text("H1, H2: M3 holes for a standoff that takes USB cable strain\noff the PMOD headers.",
            (205.74, 73.66))


def sheet_power(sh):
    sh.box(20.32, 25.4, 165.1, 170.18, "USB-C receptacle (UFP, USB 2.0)")
    j = sh.add("Connector:USB_C_Receptacle_USB2.0_16P", "J101", "USB_C_Receptacle",
               (55.88, 91.44),
               footprint="Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
               fields={"MPN": "USB4105-GF-A", "Manufacturer": "GCT"})
    j.connect({"A4": "VBUS", "A5": "CC1", "B5": "CC2", "A6": "USB_DP", "B6": "USB_DP",
               "A7": "USB_DN", "B7": "USB_DN", "A8": "NC", "B8": "NC", "A1": "GND",
               "SH": "USB_SHIELD"})
    res(sh, "R101", "5.1k", (101.6, 147.32), "CC1", "GND")
    res(sh, "R102", "5.1k", (116.84, 147.32), "CC2", "GND")
    res(sh, "R103", "1M", (45.72, 147.32), "USB_SHIELD", "GND", spec="5% 0402")
    cap(sh, "C101", "4.7nF 50V", (27.94, 147.32), "USB_SHIELD", spec="X7R")
    sh.text("CC1/CC2 5.1k pull-downs\nadvertise a UFP (sink)", (96.52, 162.56))
    sh.text("Shield: 1M || 4.7nF to GND", (25.4, 162.56))

    u = sh.add("Power_Protection:USBLC6-2SC6", "U101", "USBLC6-2SC6", (134.62, 66.04),
               footprint="Package_TO_SOT_SMD:SOT-23-6", text=((3.81, -6.35), (3.81, -4.32), "left"),
               fields={"MPN": "USBLC6-2SC6", "Manufacturer": "STMicroelectronics"})
    u.connect({"1": "USB_DP", "6": "USB_DP", "3": "USB_DN", "4": "USB_DN", "5": "VBUS", "2": "GND"})
    sh.text("ESD: place U101 at the connector,\nroute D+/D- through its pads (flow-through).\n"
            "90 ohm differential pair.\n"
            "No series resistors: the RT1010 HS PHY has\ncalibrated on-die 45 ohm terminations "
            "(RM 36.3.5.1).", (104.14, 86.36))

    sh.box(172.72, 25.4, 398.78, 170.18, "Power")
    f = sh.add("Device:Polyfuse", "F101", "0.5A", (195.58, 50.8), angle=90,
               footprint="Fuse:Fuse_1206_3216Metric", text="above",
               fields={"Spec": "PTC resettable, 0.5 A hold, >=6 V, 1206"})
    f.connect({"1": "VBUS", "2": "+5V"})
    sh.flag("VBUS", (182.88, 66.04))
    sh.flag("+5V", (228.6, 38.1))
    cap(sh, "C102", "4.7uF 10V", (213.36, 71.12), "+5V", size="0603")
    sh.text("USB limits VBUS capacitance to 10 uF:\nC102+C103+C104+C301 = 7.7 uF", (185.42, 91.44))

    reg = sh.add("Regulator_Linear:AP7361C-33E", "U102", "AP7361C-33E", (271.78, 60.96),
                 footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
                 fields={"MPN": "AP7361C-33E-13", "Manufacturer": "Diodes Inc."})
    reg.connect({"1": "+5V", "2": "GND", "3": "+3V3"})
    cap(sh, "C103", "1uF 10V", (248.92, 71.12), "+5V", size="0603")
    cap(sh, "C105", "10uF 10V", (294.64, 71.12), "+3V3", size="0603")
    cap(sh, "C106", "0.1uF 16V", (309.88, 71.12), "+3V3")
    sh.text("3.3 V main rail, 1 A LDO\n(~250 mA expected)", (256.54, 88.9))

    ldo = sh.add("Regulator_Linear:LP5907MFX-3.3", "U103", "LP5907MFX-3.3", (271.78, 124.46),
                 footprint="Package_TO_SOT_SMD:SOT-23-5",
                 fields={"MPN": "LP5907MFX-3.3/NOPB", "Manufacturer": "Texas Instruments"})
    ldo.connect({"1": "+5V", "3": "+5V", "5": "+3V3_CLK", "2": "GND"})
    cap(sh, "C104", "1uF 10V", (248.92, 134.62), "+5V", size="0603")
    cap(sh, "C107", "1uF 10V", (294.64, 134.62), "+3V3_CLK", size="0603")
    sh.text("Low-noise 3.3 V for the 24.576 MHz XO\nand clock buffer only", (256.54, 152.4))

    r = res(sh, "R104", "1k", (342.9, 60.96), "+3V3", "LED_PWR")
    dd = led(sh, "D101", "PWR (green)", (342.9, 76.2), "LED_PWR")
    sh.link("LED_PWR", (r, "2"), (dd, "A"), label=False)
    testpoint(sh, "TP101", "+5V", (360.68, 63.5))
    testpoint(sh, "TP102", "+3V3", (370.84, 63.5))
    testpoint(sh, "TP103", "+3V3_CLK", (381.0, 63.5))
    testpoint(sh, "TP104", "GND", (360.68, 91.44))
    sh.flag("GND", (381.0, 101.6))


def sheet_mcu_power(sh):
    u = sh.add(RT, "U1", RT_NAME, (139.7, 88.9), unit=1,
               footprint="Package_QFP:LQFP-80_12x12mm_P0.5mm")
    u.connect({"18": "+3V3", "17": "+3V3", "15": "DCDC_PSWITCH", "39": "+3V3", "25": "+3V3",
               "42": "+3V3", "7": "+3V3", "50": "+3V3", "63": "+3V3", "71": "+3V3",
               "16": "GND", "30": "GND", "54": "GND", "78": "GND",
               "19": "DCDC_LP", "20": "GND", "14": "+1V1", "53": "+1V1", "77": "+1V1",
               "35": "VDD_HIGH_CAP", "40": "NVCC_PLL", "26": "VDD_SNVS_CAP",
               "31": "VDD_USB_CAP", "41": "GND", "34": "GND"})

    sh.box(228.6, 25.4, 398.78, 99.06, "Internal DC-DC (VDD_SOC 1.1 V)")
    sh.add("Device:L", "L201", "4.7uH", (254.0, 55.88), angle=90, text="above",
           footprint="Inductor_SMD:L_Bourns-SRN4018",
           fields={"MPN": "SRN4018-4R7M", "Manufacturer": "Bourns",
                   "Spec": "4.7 uH, Isat >= 1 A, DCR <= 0.2 ohm"}).connect({"1": "DCDC_LP", "2": "+1V1"})
    sh.flag("+1V1", (274.32, 43.18))
    cap_row(sh, 281.94, 63.5, [("C201", "22uF 6.3V", "+1V1", "GND", "0805"),
                               ("C202", "0.22uF 10V", "+1V1")], 15.24)
    r = res(sh, "R201", "30k", (335.28, 55.88), "+3V3", "DCDC_PSWITCH")
    c = cap(sh, "C212", "0.22uF 10V", (335.28, 71.12), "DCDC_PSWITCH")
    sh.link("DCDC_PSWITCH", (r, "2"), (c, "1"))
    sh.text("PSWITCH RC delay (6.6 ms):\nDC-DC starts >1 ms after DCDC_IN", (345.44, 76.2))
    sh.text("Total VDD_SOC capacitance ~33 uF (C201, C203-C207)", (233.68, 91.44))

    sh.box(20.32, 132.08, 287.02, 269.24, "Decoupling (place at pins; HDUG Table 2)")
    p = 15.24
    y1, y2, y3 = 160.02, 205.74, 251.46
    sh.text("VDD_SOC_IN (14, 53, 77)", (25.4, 144.78))
    cap_row(sh, 30.48, y1, [("C203", "4.7uF 6.3V", "+1V1"), ("C204", "4.7uF 6.3V", "+1V1"),
                            ("C205", "0.22uF 10V", "+1V1"), ("C206", "0.22uF 10V", "+1V1"),
                            ("C207", "0.22uF 10V", "+1V1")], p)
    sh.text("DCDC_IN / DCDC_IN_Q (18, 17)", (111.76, 144.78))
    cap_row(sh, 116.84, y1, [("C208", "10uF 10V", "+3V3", "GND", "0603"),
                             ("C209", "4.7uF 6.3V", "+3V3"), ("C210", "0.22uF 10V", "+3V3"),
                             ("C211", "0.22uF 10V", "+3V3")], p)
    sh.text("VDD_HIGH_IN (39)", (182.88, 144.78))
    cap_row(sh, 187.96, y1, [("C213", "4.7uF 6.3V", "+3V3"), ("C214", "0.22uF 10V", "+3V3")], p)
    sh.text("VDD_SNVS_IN (25)", (223.52, 144.78))
    cap_row(sh, 228.6, y1, [("C218", "0.22uF 10V", "+3V3")], p)
    sh.text("VDDA_ADC_3P3 (42)", (248.92, 144.78))
    cap_row(sh, 254.0, y1, [("C222", "1uF 10V", "+3V3"), ("C223", "0.22uF 10V", "+3V3")], p)

    sh.text("NVCC_GPIO (7, 50, 63, 71): one 0.1 uF per pin", (25.4, 190.5))
    cap_row(sh, 30.48, y2, [("C224", "0.1uF 16V", "+3V3"), ("C225", "0.1uF 16V", "+3V3"),
                            ("C226", "0.1uF 16V", "+3V3"), ("C227", "0.1uF 16V", "+3V3"),
                            ("C228", "4.7uF 6.3V", "+3V3"), ("C229", "4.7uF 6.3V", "+3V3"),
                            ("C230", "4.7uF 6.3V", "+3V3")], p)

    sh.text("Internal LDO outputs: no external loads", (25.4, 223.52))
    cap_row(sh, 30.48, y3, [("C215", "4.7uF 6.3V", "VDD_HIGH_CAP"),
                            ("C216", "0.22uF 10V", "VDD_HIGH_CAP")], 25.4)
    cap_row(sh, 81.28, y3, [("C217", "0.22uF 10V", "NVCC_PLL")], 25.4)
    cap_row(sh, 106.68, y3, [("C219", "0.22uF 10V", "VDD_SNVS_CAP")], 25.4)
    cap_row(sh, 132.08, y3, [("C220", "10uF 10V", "VDD_USB_CAP", "GND", "0603"),
                             ("C221", "0.1uF 16V", "VDD_USB_CAP")], 25.4)


def sheet_mcu_system(sh):
    u = sh.add(RT, "U1", RT_NAME, (165.1, 101.6), unit=2,
               footprint="Package_QFP:LQFP-80_12x12mm_P0.5mm")
    u.connect({"22": "POR_B", "21": "NC", "23": "GND", "24": "NC",
               "37": "XTALI", "38": "XTALO", "27": "RTC_XTALI", "28": "RTC_XTALO",
               "33": "USB_DP", "32": "USB_DN", "29": "+5V", "36": "NC"})
    sh.text("TEST_MODE tied to GND. ONOFF, PMIC_ON_REQ and\nUSB_OTG1_CHD_B unused (on-chip pulls).",
            (134.62, 134.62))
    cap(sh, "C301", "1uF 10V", (238.76, 101.6), "+5V", size="0603")
    sh.text("USB_OTG1_VBUS bypass", (233.68, 119.38))

    sh.box(20.32, 25.4, 116.84, 116.84, "24 MHz system crystal")
    y = sh.add("Device:Crystal_GND24", "Y301", "24MHz", (66.04, 50.8),
               footprint="Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
               text=((0, -5.59), (0, -3.81), None),
               fields={"Spec": "24.000 MHz fundamental, CL 8 pF, ESR <= 80 ohm, drive >= 250 uW, +/-20 ppm"})
    y.connect({"1": "XTALI", "3": "XTALO", "2": "GND"})
    cap(sh, "C302", "10pF 50V", (45.72, 76.2), "XTALI", spec="C0G")
    cap(sh, "C303", "10pF 50V", (86.36, 76.2), "XTALO", spec="C0G")
    res(sh, "R301", "2.2M", (30.48, 76.2), "XTALI", "GND", spec="5% 0402")
    sh.text("Load caps sized for CL = 8 pF (~3 pF stray).\nR301 per NXP EVK (start-up aid).",
            (25.4, 101.6))

    sh.box(20.32, 124.46, 116.84, 195.58, "32.768 kHz RTC crystal")
    sh.add("Device:Crystal", "Y302", "32.768kHz", (66.04, 142.24),
           footprint="Crystal:Crystal_SMD_3215-2Pin_3.2x1.5mm",
           text=((0, -5.08), (0, -3.3), None),
           fields={"Spec": "32.768 kHz, CL 7 pF, ESR <= 70 kohm"}).connect(
        {"1": "RTC_XTALI", "2": "RTC_XTALO"})
    cap(sh, "C304", "10pF 50V", (45.72, 165.1), "RTC_XTALI", spec="C0G")
    cap(sh, "C305", "10pF 50V", (86.36, 165.1), "RTC_XTALO", spec="C0G")
    sh.text("No bias resistor (on-chip). Keep RTC_XTALI/O\nleakage > 100 Mohm.", (25.4, 187.96))

    sh.box(271.78, 25.4, 398.78, 132.08, "Reset (POR_B)")
    sup = sh.add("Power_Supervisor:MCP120-xxxxTT", "U301", "MCP120T-300I/TT", (299.72, 66.04),
                 footprint="Package_TO_SOT_SMD:SOT-23",
                 fields={"MPN": "MCP120T-300I/TT", "Manufacturer": "Microchip",
                         "Spec": "open-drain, Vtrip 2.925 V (> 2.6 V DCDC_IN UVLO)"})
    sup.connect({"1": "POR_B", "2": "+3V3", "3": "GND"})
    cap(sh, "C306", "0.1uF 16V", (284.48, 50.8), "+3V3")
    r = res(sh, "R302", "10k", (325.12, 50.8), "+3V3", "POR_B")
    c = cap(sh, "C307", "0.1uF 16V", (325.12, 76.2), "POR_B")
    sh.link("POR_B", (r, "2"), (c, "1"))
    sw = sh.add("Switch:SW_Push", "SW301", "RESET", (350.52, 81.28), angle=90, footprint=SW_FP,
                text="right", fields={"MPN": "PTS810SJM250SMTRLFS", "Manufacturer": "C&K"})
    sw.connect({"1": "GND", "2": "POR_B"})
    sh.text("POR_B also driven by MCU-Link nRESET (J501-10).\nPull-up to 3.3 V = VDD_SNVS_IN.",
            (276.86, 116.84))


def sheet_boot(sh):
    u = sh.add(RT, "U1", RT_NAME, (190.5, 106.68), unit=4,
               footprint="Package_QFP:LQFP-80_12x12mm_P0.5mm")
    u.connect({"76": "BT_CFG2", "75": "BT_CFG1", "74": "BT_CFG0", "73": "BOOT_MODE1",
               "72": "BOOT_MODE0", "70": "SPI_MISO", "69": "FLASH_CS",
               "68": "FLASH_IO1", "67": "FLASH_IO2", "66": "FLASH_IO0", "65": "FLASH_CLK",
               "64": "FLASH_IO3", "62": "NC", "61": "NC"})
    sh.text("GPIO_SD_05 = LPSPI1_SDI (ALT2) for PMOD JC.\nGPIO_SD_12 (FlexSPI A_DQS) left "
            "open for\ninternal read-strobe loopback.", (167.64, 134.62))

    sh.box(20.32, 25.4, 147.32, 101.6, "Boot configuration straps")
    res(sh, "R401", "10k", (30.48, 50.8), "BT_CFG2", "GND")
    res(sh, "R402", "10k", (45.72, 50.8), "BT_CFG1", "GND")
    res(sh, "R403", "10k", (60.96, 50.8), "BT_CFG0", "GND")
    sh.text("BT_CFG[2:0] = 000:\nFlexSPI serial NOR,\nno encrypted XIP", (25.4, 71.12))
    res(sh, "R404", "10k", (93.98, 45.72), "+3V3", "BOOT_MODE1")
    res(sh, "R407", "10k", (124.46, 71.12), "BOOT_MODE0", "GND")
    sh.text("Default BOOT_MODE[1:0] = 10\n(internal boot from QSPI flash)", (83.82, 91.44))

    sh.box(20.32, 109.22, 147.32, 195.58, "BOOT button: serial downloader")
    q = sh.add("Transistor_FET:BSS84", "Q401", "BSS84", (76.2, 142.24), angle=180,
               footprint="Package_TO_SOT_SMD:SOT-23", text=((-6.35, -1.27), (-6.35, 1.27), "right"),
               fields={"MPN": "BSS84", "Spec": "P-MOSFET, Vgs(th) -0.8..-2.0 V"})
    q.connect({"2": "+3V3"})
    r406 = res(sh, "R406", "1k", (73.66, 157.48), "BOOT_FET_D", "BOOT_MODE0")
    sh.link("BOOT_FET_D", (q, "3"), (r406, "1"), label=False)
    r405 = res(sh, "R405", "1k", (101.6, 132.08), "BOOT_MODE1", "BOOT_SW")
    sw = sh.add("Switch:SW_Push", "SW401", "BOOT", (101.6, 154.94), angle=90, footprint=SW_FP,
                text="right", fields={"MPN": "PTS810SJM250SMTRLFS", "Manufacturer": "C&K"})
    sw.connect({"1": "GND"})
    sh.link("BOOT_SW", (r405, "2"), (sw, "2"))
    sh.tap("BOOT_SW", (q, "1"), (101.6, 142.24))
    sh.text("Hold BOOT, tap RESET -> BOOT_MODE1=0 (0.3 V), BOOT_MODE0=1 (3.0 V)\n"
            "= 01 Serial Downloader (USB HID). Works regardless of eFuses.", (25.4, 180.34))

    sh.box(259.08, 25.4, 398.78, 152.4, "QSPI NOR flash (FlexSPI port A)")
    f = sh.add("Memory_Flash:W25Q128JVS", "U401", "W25Q128JVSIQ", (330.2, 88.9),
               footprint="Package_SO:SOIC-8_5.3x5.3mm_P1.27mm",
               fields={"MPN": "W25Q128JVSIQ", "Manufacturer": "Winbond",
                       "Spec": "128 Mbit, 3.3 V QSPI NOR, SOIC-8 208 mil"})
    f.connect({"1": "FLASH_CS", "6": "FLASH_CLK", "5": "FLASH_IO0", "2": "FLASH_IO1",
               "3": "FLASH_IO2", "7": "FLASH_IO3", "8": "+3V3", "4": "GND"})
    res(sh, "R408", "10k", (276.86, 50.8), "+3V3", "FLASH_CS")
    res(sh, "R409", "10k", (289.56, 50.8), "+3V3", "FLASH_IO2")
    res(sh, "R410", "10k", (302.26, 50.8), "+3V3", "FLASH_IO3")
    cap(sh, "C401", "0.1uF 16V", (355.6, 63.5), "+3V3")
    cap(sh, "C402", "1uF 10V", (370.84, 63.5), "+3V3")
    sh.text("IO2/IO3 pull-ups keep /WP and /HOLD inactive\nduring single-bit ROM reads.",
            (264.16, 134.62))


def sheet_io(sh):
    u = sh.add(RT, "U1", RT_NAME, (165.1, 104.14), unit=3,
               footprint="Package_QFP:LQFP-80_12x12mm_P0.5mm")
    u.connect({"13": "NC", "12": "I2S_RX_BCLK", "11": "I2S_RX_LRCLK", "10": "I2S_RX_DATA",
               "9": "I2S_TX_DATA", "8": "NC", "6": "I2S_TX_BCLK", "5": "I2S_TX_LRCLK",
               "4": "MCLK_SAI", "3": "UART_RX", "2": "UART_TX", "1": "LED1", "80": "LED2",
               "79": "NC",
               "60": "PMOD_INT", "59": "PMOD_GPIO0", "58": "PMOD_GPIO1", "57": "MCLK_GPT",
               "56": "SPI_MOSI", "55": "SPI_CS", "52": "SPI_SCK", "51": "PMOD_RST",
               "49": "NC", "48": "SWO", "47": "JTAG_TDI", "46": "JTAG_MOD", "45": "SWCLK",
               "44": "SWDIO", "43": "NC"})
    sh.text("SAI1: GPIO_01-08 ALT0. LPUART1: GPIO_09/10 ALT0.\nLPSPI1: GPIO_AD_04-06 ALT0. "
            "GPT2_CLK: GPIO_AD_03 ALT4.", (134.62, 149.86))

    sh.box(274.32, 25.4, 398.78, 106.68, "MCU-Link debug (10-pin Cortex, 1.27 mm, keyed)")
    j = sh.add("Connector_Generic:Conn_02x05_Odd_Even", "J501", "SWD", (325.12, 63.5),
               footprint="USBAudioBridge:Samtec_FTSH-105-01-L-DV-K",
               fields={"MPN": "FTSH-105-01-L-DV-K", "Manufacturer": "Samtec",
                       "Spec": "2x5 1.27 mm SMD header with keying shroud (Cortex debug)"})
    j.connect({"1": "+3V3", "2": "SWDIO", "3": "GND", "4": "SWCLK", "5": "GND", "6": "SWO",
               "7": "NC", "8": "JTAG_TDI", "9": "GND", "10": "POR_B"})
    res(sh, "R501", "10k", (360.68, 43.18), "+3V3", "SWDIO")
    res(sh, "R502", "4.7k", (289.56, 88.9), "JTAG_MOD", "GND")
    sh.text("JTAG_MOD low = SWD/common debug\n(HDUG: 4.7k pull-down)", (299.72, 91.44))

    sh.box(274.32, 114.3, 398.78, 177.8, "UART console (LPUART1, ROM serial-download port)")
    sh.add("Connector_Generic:Conn_01x03", "J502", "UART", (370.84, 147.32),
           footprint="Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
           fields={"Spec": "1x3 2.54 mm header: 1 TX(out) 2 RX(in) 3 GND"}).connect(
        {"1": "UART_TX", "2": "UART_RX", "3": "GND"})
    res(sh, "R503", "10k", (299.72, 137.16), "+3V3", "UART_TX")
    res(sh, "R504", "10k", (325.12, 137.16), "+3V3", "UART_RX")
    sh.text("10k pull-ups avoid false ROM UART triggers (HDUG Table 8)", (279.4, 172.72))

    sh.box(274.32, 185.42, 398.78, 248.92, "User LEDs (active high)")
    for ref_r, ref_d, net, colour, x in (("R505", "D501", "LED1", "green", 299.72),
                                         ("R506", "D502", "LED2", "yellow", 340.36)):
        r = res(sh, ref_r, "1k", (x, 208.28), net, net + "_A")
        dd = led(sh, ref_d, f"{net} ({colour})", (x, 223.52), net + "_A")
        sh.link(net + "_A", (r, "2"), (dd, "A"), label=False)


def sheet_audio(sh):
    sh.box(20.32, 25.4, 205.74, 137.16, "24.576 MHz audio master clock")
    xo = sh.add("Oscillator:SG-210STF", "X601", "24.576MHz", (55.88, 71.12),
                footprint="Oscillator:Oscillator_SMD_SeikoEpson_SG210-4Pin_2.5x2.0mm",
                text=((-1.27, -9.65), (-1.27, -7.87), "right"),
                fields={"MPN": "SG-210STF 24.5760ML", "Manufacturer": "Epson",
                        "Spec": "24.576 MHz CMOS SPXO, 1.62-3.63 V, +/-50 ppm, -40..85 C, "
                                "2.5x2.0 mm, pin 1 /ST (high = run)"})
    xo.connect({"1": "+3V3_CLK", "4": "+3V3_CLK", "2": "GND"})
    cap(sh, "C601", "0.1uF 16V", (35.56, 50.8), "+3V3_CLK")
    r601 = res(sh, "R601", "22", (76.2, 71.12), "XO_OUT", "CLK_BUF_IN", horizontal=True)
    b = sh.add("Buffer:CDCV304", "U601", "CDCV304PW", (127.0, 71.12),
               footprint="Package_SO:TSSOP-8_4.4x3mm_P0.65mm",
               fields={"MPN": "CDCV304PWR", "Manufacturer": "Texas Instruments",
                       "Spec": "1:4 LVCMOS clock fanout buffer"})
    b.connect({"2": "+3V3_CLK", "6": "+3V3_CLK", "4": "GND"})
    sh.link("XO_OUT", (xo, "3"), (r601, "1"), label=False)
    sh.link("CLK_BUF_IN", (r601, "2"), (b, "1"), label=False)
    cap(sh, "C602", "0.1uF 16V", (106.68, 50.8), "+3V3_CLK")
    # buffer output -> series resistor; the turn columns keep the four routes from crossing
    for ref, pin, y_r, mid, net in (("R602", "3", 58.42, 149.86, "MCLK_SAI"),
                                    ("R603", "5", 68.58, None, "MCLK_GPT"),
                                    ("R604", "7", 78.74, 149.86, "JB_RX_MCLK"),
                                    ("R605", "8", 88.9, 144.78, "JB_TX_MCLK")):
        r = res(sh, ref, "33", (162.56, y_r), "CLK_" + ref, net, horizontal=True)
        sh.link(f"CLK_Y{int(ref[-1]) - 2}", (b, pin), (r, "1"), label=False, mid=mid)
    sh.text("Series terminations at the buffer outputs.\nY0 -> RT1010 SAI1_MCLK (GPIO_08)\n"
            "Y1 -> RT1010 GPT2_CLK (GPIO_AD_03), async feedback\n"
            "Y2 -> PMOD JB1 (MCLK, top row)\nY3 -> PMOD JB7 (MCLK, bottom row)",
            (25.4, 109.22))

    # PMOD JB (west port): Digilent Pmod I2S2 pinout, viewed from the FPGA as the host.
    # JB1 (E15, SRCC) and JB3 (D15, MRCC) are the Arty's clock-capable P pins.
    sh.box(20.32, 144.78, 205.74, 264.16, "PMOD JB (Arty high-speed port): I2S, Pmod I2S2 pinout")
    jb = sh.add("Connector_Generic:Conn_02x06_Top_Bottom", "J601", "PMOD_JB", (116.84, 200.66),
                footprint=PMOD_FP,
                fields={"Spec": "2x6 2.54 mm right-angle male header, Digilent PMOD pin numbering"})
    jb.connect({"1": "JB_RX_MCLK", "2": "JB_RX_LRCLK", "3": "JB_RX_BCLK", "4": "JB_RX_DATA",
                "5": "GND", "6": "PMOD_VCC", "7": "JB_TX_MCLK", "8": "JB_TX_LRCLK",
                "9": "JB_TX_BCLK", "10": "JB_TX_DATA", "11": "GND", "12": "PMOD_VCC"})
    left = [("R606", "I2S_RX_LRCLK", "JB_RX_LRCLK"), ("R607", "I2S_RX_BCLK", "JB_RX_BCLK"),
            ("R608", "I2S_RX_DATA", "JB_RX_DATA")]
    right = [("R609", "JB_TX_LRCLK", "I2S_TX_LRCLK"), ("R610", "JB_TX_BCLK", "I2S_TX_BCLK"),
             ("R611", "JB_TX_DATA", "I2S_TX_DATA")]
    for i, (ref, a, b_) in enumerate(left):
        res(sh, ref, "33", (55.88, 172.72 + i * 10.16), a, b_, horizontal=True)
    for i, (ref, a, b_) in enumerate(right):
        res(sh, ref, "33", (172.72, 172.72 + i * 10.16), a, b_, horizontal=True)
    sh.text("Pmod I2S2 pinout (host = FPGA):\n"
            "  1-4  D/A row: MCLK, LRCK, SCLK, SDIN   = FPGA -> RT1010 (SAI1 RX)\n"
            "  7-10 A/D row: MCLK, LRCK, SCLK, SDOUT = RT1010 -> FPGA (SAI1 TX)\n"
            "All clocks are driven by this board: the FPGA must treat JB1-3 and JB7-9 as inputs.\n"
            "JB1 (MCLK) and JB3 (SCLK) land on Artix-7 clock-capable pins E15 (SRCC) and D15 (MRCC);\n"
            "run SAI1 TX synchronous to RX so JB3 clocks both directions.",
            (25.4, 236.22))

    # PMOD JC (east port): SPI + GPIO, Digilent Type 2A
    sh.box(213.36, 144.78, 398.78, 264.16, "PMOD JC (Arty high-speed port): SPI + GPIO")
    jc = sh.add("Connector_Generic:Conn_02x06_Top_Bottom", "J602", "PMOD_JC", (309.88, 200.66),
                footprint=PMOD_FP,
                fields={"Spec": "2x6 2.54 mm right-angle male header, Digilent PMOD pin numbering"})
    jc.connect({"1": "JC_SPI_CS", "2": "JC_SPI_MOSI", "3": "JC_SPI_MISO", "4": "JC_SPI_SCK",
                "5": "GND", "6": "PMOD_VCC", "7": "JC_INT", "8": "JC_RST",
                "9": "JC_GPIO0", "10": "JC_GPIO1", "11": "GND", "12": "PMOD_VCC"})
    left = [("R612", "SPI_CS", "JC_SPI_CS"), ("R613", "SPI_MOSI", "JC_SPI_MOSI"),
            ("R614", "SPI_MISO", "JC_SPI_MISO"), ("R615", "SPI_SCK", "JC_SPI_SCK")]
    right = [("R616", "JC_INT", "PMOD_INT"), ("R617", "JC_RST", "PMOD_RST"),
             ("R618", "JC_GPIO0", "PMOD_GPIO0"), ("R619", "JC_GPIO1", "PMOD_GPIO1")]
    for i, (ref, a, b_) in enumerate(left):
        res(sh, ref, "33", (248.92, 167.64 + i * 10.16), a, b_, horizontal=True)
    for i, (ref, a, b_) in enumerate(right):
        res(sh, ref, "33", (365.76, 167.64 + i * 10.16), a, b_, horizontal=True)
    sh.text("PMOD Type 2A (expanded SPI): RT1010 LPSPI1 is master by default;\n"
            "LPSPI PINCFG can swap SDI/SDO if the FPGA is master. INT on 7, RST on 8.",
            (218.44, 248.92))

    sh.box(213.36, 25.4, 398.78, 99.06, "PMOD VCC")
    sh.add("Jumper:SolderJumper_2_Open", "JP601", "PMOD_VCC", (299.72, 55.88),
           footprint="Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm", in_bom=False,
           fields={"Spec": "Open by default"}).connect({"A": "PMOD_VCC", "B": "+3V3"})
    sh.text("Board is USB powered. Arty PMOD VCC (pins 6, 12) is isolated from +3V3\n"
            "by open jumper JP601 to avoid back-feeding either regulator.\n"
            "Do not close with USB connected.", (218.44, 81.28))


def main():
    os.makedirs(OUT, exist_ok=True)
    write_library(os.path.join(OUT, "USBAudioBridge.kicad_sym"))
    footprints.write_library(os.path.join(OUT, "USBAudioBridge.pretty"))
    d = build()
    d.write(mcu_prefix="USBAudioBridge:MIMXRT")
    return d


if __name__ == "__main__":
    main()
