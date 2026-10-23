"""Board geometry and component placement for the USB Audio Bridge PCB.

Coordinates are millimetres relative to the board's top-left corner, KiCad
orientation (y grows downwards, rotation in degrees CCW).  North (y=0) is the
USB-C edge; south (y=H) is the PMOD edge that plugs into the Arty A7, whose
ports JB (west) and JC (east) sit on 0.9" centres.
"""

W = 43.18          # two PMOD module slots: 0.9" pitch + 0.8" module width
H = 62.0
ORIGIN = (100.0, 100.0)  # board top-left in KiCad page coordinates

# PMOD headers: origin is the pin 6/12 end; pins 1-6 row lies 6.35 mm from the edge
PMOD_Y = H - 6.35
JB_X = 0.4 * 25.4 + 6.35     # slot centre 0.4" from the west edge
JC_X = 1.3 * 25.4 + 6.35     # slot centre 1.3" from the west edge

MCU = (21.59, 27.0, 180)     # U1, pins 21-40 (USB, crystals) face north after rotation

# ref: (x, y, rotation)
PLACEMENT = {
    # --- north: USB-C, protection, regulators, crystals
    "J101": (21.59, 3.675, 180),
    "H1": (4.0, 4.0, 0),
    "H2": (39.18, 4.0, 0),
    "F101": (13.0, 4.2, 0),
    "C102": (13.0, 7.6, 180),
    "U101": (21.59, 12.2, 90),
    "U102": (6.0, 14.6, 0),
    "C103": (2.6, 19.9, 0),
    "C105": (8.4, 19.9, 0),
    "C106": (11.0, 19.9, 0),
    "Y301": (15.8, 16.4, 0),
    "C302": (13.0, 15.6, 90),
    "C303": (13.0, 18.0, 90),
    "R301": (13.0, 13.4, 90),
    "Y302": (27.4, 16.4, 0),
    "C304": (30.4, 15.4, 90),
    "C305": (30.4, 17.6, 90),
    "C301": (24.8, 13.4, 0),
    "R101": (25.6, 10.2, 90),
    "R102": (17.6, 10.2, 90),
    "R103": (27.8, 6.6, 90),
    "C101": (27.8, 8.9, 90),
    "R104": (33.4, 8.8, 0),
    "D101": (36.6, 8.8, 180),
    "TP101": (33.0, 12.0, 0),
    "TP102": (35.6, 12.0, 0),
    "TP103": (38.2, 12.0, 0),
    "TP104": (40.8, 12.0, 0),

    # --- MCU and its DC-DC
    "U1": MCU,
    "L201": (34.0, 21.6, 90),
    "C201": (37.4, 19.6, 90),
    "C202": (39.8, 19.6, 90),
    "R201": (31.2, 26.6, 90),
    "C212": (32.6, 26.6, 90),

    # --- east: reset (near POR_B), UART on the edge; LEDs up by the test points
    "U301": (37.4, 27.0, 90),
    "C306": (40.6, 25.0, 90),
    "R302": (40.6, 28.0, 90),
    "C307": (40.6, 30.4, 90),
    "SW301": (38.8, 33.6, 0),
    "J502": (28.8, 2.6, 90),
    "R503": (32.6, 6.2, 0),
    "R504": (32.6, 7.6, 0),
    "R505": (33.6, 14.0, 0),
    "D501": (36.6, 14.0, 0),
    "R506": (33.6, 15.6, 0),
    "D502": (36.6, 15.6, 0),

    # --- west: debug header; the SPI/GPIO lines run down this side to JB
    "J501": (4.6, 27.6, 90),
    "R501": (9.2, 23.2, 90),
    "R502": (9.2, 33.0, 90),

    # --- south centre: boot flash on the BOTTOM side, boot straps under the SD pins
    "U401": (16.0, 41.0, 0, "B"),
    "R408": (10.6, 38.6, 90, "B"),
    "R409": (10.6, 41.0, 90, "B"),
    "R410": (10.6, 43.4, 90, "B"),
    "C401": (21.6, 38.8, 90, "B"),
    "C402": (21.6, 41.2, 90, "B"),
    "R401": (23.4, 38.0, 90, "B"), "R402": (24.7, 38.0, 90, "B"), "R403": (26.0, 38.0, 90, "B"),
    "R404": (27.3, 38.0, 90, "B"), "R407": (28.6, 38.0, 90, "B"),

    # --- top south centre: audio clock block, then the BOOT circuit between headers
    "X601": (18.4, 39.6, 0),
    "C601": (15.6, 39.6, 90),
    "R601": (21.4, 39.6, 0),
    "U601": (24.6, 41.2, 90),
    "C602": (27.4, 38.6, 90),
    "R602": (27.4, 41.4, 90),
    "R603": (27.4, 43.8, 90),
    "U103": (19.0, 44.4, 0),
    "C104": (15.6, 43.6, 90),
    "C107": (22.0, 46.8, 0),
    "Q401": (21.0, 46.6, 0, "B"),
    "R405": (18.6, 46.6, 90, "B"),
    "R406": (23.6, 46.6, 90, "B"),
    "SW401": (21.59, 54.4, 90),

    # --- PMOD series resistors (row above each header) and headers
    # JB (west, SPI + GPIO): R606-R613 over pins 1-4 / 7-10
    "R606": (3.2, 52.0, 90), "R607": (4.5, 52.0, 90), "R608": (5.8, 52.0, 90),
    "R609": (7.1, 52.0, 90), "R610": (8.4, 52.0, 90), "R611": (9.7, 52.0, 90),
    "R612": (11.0, 52.0, 90), "R613": (12.3, 52.0, 90),
    # JC (east, I2S): clock resistors R604/R605 for MCLK, then R614-R619
    "R604": (26.0, 52.0, 90), "R605": (27.3, 52.0, 90),
    "R614": (28.6, 52.0, 90), "R615": (29.9, 52.0, 90), "R616": (31.2, 52.0, 90),
    "R617": (32.5, 52.0, 90), "R618": (33.8, 52.0, 90), "R619": (35.1, 52.0, 90),
    "JP601": (21.59, 59.6, 0),
    "J601": (JB_X, PMOD_Y, 270),
    "J602": (JC_X, PMOD_Y, 270),
}

# MCU decoupling on the bottom side, positioned by pcb_copper.mcu_power():
#   "ring": 0.1-0.22 uF directly behind the supply pin's fanout via
#   "out" : bulk cap just outside the pad ring (+3V3 ones use the In2 plane,
#           local-LDO ones are wired back to the pin's via on B.Cu)
#   "in"  : +1V1 bulk cap inside the In2 +1V1 island under the MCU
DECOUPLING = {
    "C218": ("25", "out"), "C219": ("26", "ring"),
    "C221": ("31", "ring"), "C220": ("31", "out"),
    "C216": ("35", "ring"), "C215": ("35", "out"),
    "C214": ("39", "ring"), "C213": ("39", "out"), "C217": ("40", "out"),
    "C210": ("18", "ring"), "C211": ("17", "out"), "C209": ("18", "out"),
    "C208": ("17", "out"),
    "C205": ("14", "ring"), "C203": ("14", "in"),
    "C224": ("7", "ring"), "C228": ("7", "out"),
    "C223": ("42", "out"), "C222": ("42", "out"),
    "C225": ("50", "ring"), "C229": ("50", "out"),
    "C206": ("53", "ring"), "C204": ("53", "in"),
    "C226": ("63", "ring"), "C230": ("63", "out"),
    "C227": ("71", "ring"),
    "C207": ("77", "ring"),
}
