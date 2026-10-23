# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This is a KiCad 10 hardware project for a USB audio bridge built around an NXP i.MX RT1010 (MIMXRT1011DAE5A, LQFP-80). The schematic has been reviewed. The PCB (43.18 × 62 mm, 4 layers, double-sided assembly) is routed with ERC and DRC clean (including warnings and schematic parity) and is awaiting the owner's review. The fabrication output pipeline is not built yet.

## Layout

- `hardware/`: the KiCad project, `USBAudioBridge.kicad_pro`.
  - The root sheet has design notes and the pin map. Six sub-sheets: `power_usb`, `mcu_power`, `mcu_system`, `boot_flash`, `mcu_io`, `audio_pmod`.
  - `USBAudioBridge.kicad_sym` is the project symbol library. It holds the RT1010 as 4 units (A Power, B System/USB, C GPIO bank, D FlexSPI/SD bank) and the `+3V3_CLK` power symbol.
- `tools/`: a Python generator that produces the schematic. It uses only the standard library.
  - `design.py` describes every part, value, footprint and net.
  - `projlib.py` builds the RT1010 symbol from datasheet Tables 51 and 52.
  - `schgen.py` handles placement and rendering. Each pin gets a short stub plus a label or power symbol. `Sheet.link`/`tap` draw direct wires for local chains.
  - `build.py` regenerates, normalises and verifies (see below).
- `docs/datasheets/`: reference PDFs. These are gitignored.
  - RT1010 data sheet, reference manual and hardware development guide (HDUG)
  - EVK schematic `SPF-45852_C.pdf`
  - Arty A7 reference manual and schematic
  - PMOD specification

## Schematic workflow

The schematic was generated, not drawn by hand. To change it, edit `tools/design.py` and rebuild:

```bash
python3 tools/build.py   # generate → kicad-cli sch upgrade → netlist cross-check → ERC
kicad-cli sch erc --exit-code-violations --severity-all hardware/USBAudioBridge.kicad_sch
kicad-cli sch export pdf -o hardware/build/schematic.pdf hardware/USBAudioBridge.kicad_sch
```

`build.py` exports KiCad's netlist and compares it with the nets `design.py` intended. Any difference is reported as a problem. Pins deliberately marked `"NC"` show up as `unconnected-*` nets and are allowed.

UUIDs are deterministic (uuid5 of sheet and reference), so regenerating keeps the links between schematic and PCB intact. If the schematic is later edited in the KiCad GUI, the generator becomes stale: either port the edits back into `design.py` or stop regenerating.

Render pages for a visual check with `pdftoppm -r 90 -f N -l N -png hardware/build/schematic.pdf out`. The netlist check does not catch overlapping text.

## PCB workflow

The PCB is also generated, using KiCad's `pcbnew` Python API (KiCad 10.0.7). Run `tools/build.py` first so the netlist exists:

```bash
python3 tools/pcb.py         # board from the netlist: outline, placement, rules, stackup, planes, scripted copper
python3 tools/autoroute.py   # Specctra DSN → Freerouting → SES import → GND pours → zone fill
kicad-cli pcb drc --severity-all --schematic-parity -o hardware/build/drc.rpt hardware/USBAudioBridge.kicad_pcb
tools/render_pcb.sh out.png "F.Cu,F.CrtYd,F.Fab,Edge.Cuts" 400   # PNG for visual review
```

- `pcb_layout.py` holds the board size and every top/bottom placement, plus how each MCU decoupling cap relates to its pin.
- `pcb_rules.py` holds the JLC04161H-3313 stackup, net classes (Power, USB90, Clock), design rules and the custom `.kicad_dru` rule.
- `pcb_route.py` is a small obstacle model (pads, vias, tracks) used to search for clear via positions.
- `pcb_copper.py` handles copper:
  - the plane zones
  - the scripted USB and DC-DC routes
  - MCU supply and GND fanout (a via just inside the pad ring for each pin, with its bottom-side cap behind it)
  - bulk-cap placement
  - generic plane-net fanout
- `pcb_silk.py` tidies the silkscreen. Reference designators stay on silk only for connectors, ICs, switches, LEDs, crystals and the like; the rest go to Fab.
- `autoroute.py` runs these stages:
  1. DSN export, Freerouting, SES import.
  2. `--clean`: remove dangling copper, including Freerouting's duplicate segments.
  3. `--repair`: read KiCad's DRC unconnected pairs and close them with short tracks and vias.
  4. `--finish`: GND pours, stitching vias, zone fill, silkscreen.
- Stages 2–4 each run in a fresh Python process, because KiCad's SWIG proxies degrade during long sessions and eventually segfault. A full route takes about 25–30 minutes.
  - `python3 tools/pcb.py && python3 tools/autoroute.py --reuse` re-applies the last `build/board.ses` without re-routing. Only valid if the scripted copper hasn't changed: SES import replaces all tracks.
  - Never run `--reuse` on an already-finished board without running `pcb.py` first; it duplicates the pours.
- Scripted copper that must exist before routing:
  - the USB pair
  - USB shield links
  - DCDC_LP
  - +1V1 from L201 to the island: a protected In2.Cu track, not a zone corridor, because other nets' via antipads cut corridors
  - MCU supply/GND fanout
  - dog-bone fanout of the south-side MCU pins whose loads are on B.Cu (flash, boot straps)
- Freerouting is `tools/bin/freerouting-2.1.0.jar` (gitignored). It is the newest release that runs on the installed Java 21; 2.2 and later need Java 25.
  - Before routing, the DSN is edited: In1/In2 become `(type power)` so no signals go in the planes, and the scripted copper becomes `(type protect)`.
  - The F.Cu/B.Cu GND pours are added only after routing, so the router doesn't treat them as obstacles.
- Floorplan: MCU rotated 180° so the USB/crystal side faces the USB-C edge. SAI pins are then on the east side and SPI/GPIO_AD pins on the west, which is why I2S goes to JC (east) and SPI to JB (west).
- Boot flash and its passives are on the bottom side. Double-sided assembly is required anyway for the MCU decoupling caps under the chip.

## Design requirements (from README)

- MCU: NXP i.MX RT1010.
- High-speed USB-C connector.
- MCU-Link compatible SWD debug header.
- Two PMOD headers designed to mate with a Digilent Arty A7 FPGA board:
  - PMOD 1: two I2S buses, one input and one output.
  - PMOD 2: SPI and GPIO.
- The board targets a USB Audio Class **asynchronous** device. The audio clock is the timing master, and USB feedback endpoints report the rate to the host.
- The audio master clock comes from a stable, accurate 24.576 MHz oscillator. This is the 48 kHz-family MCLK (512 × 48 kHz), so it must feed the SAI/I2S MCLK path rather than being derived from the USB clock.

## Design decisions (confirmed with the owner)

- Power: USB VBUS only, through a 3.3 V LDO. The Arty PMOD VCC pins are not connected to the board's 3.3 V rail (at most a DNP solder jumper) so the two boards never back-feed each other. Grounds are shared.
- I2S: the RT1010 SAI is the clock master. It generates BCLK and LRCLK for both buses from the 24.576 MHz oscillator, and the oscillator's MCLK is buffered out to the FPGA on the I2S PMOD.
- The board mates with Arty A7 ports **JB + JC**, the two adjacent high-speed PMODs, which have no series resistors. JB carries SPI + GPIO, JC carries I2S.
- Extras: reset button and serial-downloader boot button, power and GPIO status LEDs, a 3-pin UART console header, and a 32.768 kHz RTC crystal.
- 44.1 kHz-family rates are out of scope: there is only a 24.576 MHz audio clock, so the 48 kHz family only.
- PCB: 4 layers, built by JLCPCB (their stackup, LCSC part numbers, their BOM and pick-and-place formats). Two M3 mounting holes take USB cable strain off the PMOD headers.
  - The board sits flat beside the Arty. The JB/JC headers are on one edge, on 0.9" (22.86 mm) centres per the PMOD spec, and the USB-C connector is on the far edge.
- Routing: critical nets are placed and routed by script through KiCad's `pcbnew` Python API. Freerouting finishes the rest headless.

## Design facts that took cross-referencing to establish

- **Audio clock:** the 24.576 MHz XO feeds a CDCV304 buffer with three outputs.
  - Output 1 → SAI1_MCLK input (GPIO_08). Firmware sets GPR1 `SAI1_MCLK_DIR=0` and `SAI1_MCLK1_SEL=011`.
  - Output 2 → GPT2_CLK (GPIO_AD_03). It counts MCLK between USB start-of-frame packets to compute the async feedback value. GPT external clock must stay below ipg_clk/4, so ipg_clk must be at least 98.4 MHz.
  - Outputs 3 and 4 → PMOD JC1 and JC7, the MCLK pin of each I2S row.
  - The oscillator is an Epson SG-210STF 24.5760ML: ±50 ppm, and it has a KiCad 3D model.
- **SPI pins:** LPSPI1 uses GPIO_AD_04/05/06. Its SDI moves to GPIO_SD_05 (ALT2, `LPSPI1_SDI_SELECT_INPUT=1`) because GPIO_AD_03 is taken by GPT2_CLK.
- **Boot:** BOOT_MODE[1:0]=10 (internal boot from FlexSPI-A QSPI NOR) is the default strap. The BOOT button pulls BOOT_MODE1 low and, through the P-FET Q401, BOOT_MODE0 high. That gives 01, the serial downloader, whatever the eFuse state.
- **I2S port (JC):** I2S is on **JC** and SPI+GPIO on **JB**, swapped with the owner's approval to avoid the two buses crossing under the MCU. JC matches the Digilent Pmod I2S2 (owner's requirement), with the FPGA as host.
  - Top row, pins 1–4 (MCLK/LRCK/SCLK/SDIN): FPGA→RT1010 audio on SAI1 RX.
  - Bottom row, pins 7–10 (MCLK/LRCK/SCLK/SDOUT): RT1010→FPGA audio on SAI1 TX.
  - This board drives all the clocks, so the FPGA must treat them as inputs.
  - SAI1 DATA1 (GPIO_05) has no free pin and is unconnected.
- **SPI port (JB):** JB follows PMOD Type 2A (expanded SPI).
- **Arty high-speed PMOD pairs:** pins (1,2), (3,4), (7,8) and (9,10) are routed as coupled pairs. With the I2S2 pinout, MCLK shares a pair with LRCK. That's accepted because LRCK changes slowly and is only sampled.
- **USB D+/D−:** no series resistors, on purpose. The RT1010 high-speed PHY has calibrated on-die 45 Ω terminations (reference manual §36.3.5.1), and the NXP evaluation board routes D+/D− directly.
- **Reset supervisor:** the MCP120T-300 trips at 2.925 V.
- **PMOD connector footprint:** J601 and J602 use Digilent pin numbering (1–6 on one row, 7–12 on the other). The stock KiCad `PinHeader_2x06` footprint numbers pins odd/even, so the PCB needs a custom footprint or a pin-map check.

## Project acceptance criteria (from README)

- ERC and DRC must pass with no violations.
- Every part must have a 3D model attached.
- A pipeline must generate the deliverables a PCBA manufacturer needs: Gerbers, drill files, BOM, and pick-and-place.

## Tooling

KiCad 10 is installed (`kicad-cli` is at `/usr/bin/kicad-cli`). The usual checks and exports, with `<name>` standing for the project's base name:

```bash
# Checks: --exit-code-violations makes these fail (nonzero exit) on any violation
kicad-cli sch erc --exit-code-violations <name>.kicad_sch
kicad-cli pcb drc --exit-code-violations --schematic-parity <name>.kicad_pcb

# PCBA deliverables
kicad-cli pcb export gerbers -o fab/ <name>.kicad_pcb
kicad-cli pcb export drill -o fab/ <name>.kicad_pcb
kicad-cli pcb export pos -o fab/<name>-pos.csv --format csv --units mm <name>.kicad_pcb   # pick-and-place
kicad-cli sch export bom -o fab/<name>-bom.csv <name>.kicad_sch
kicad-cli sch export pdf -o fab/<name>-schematic.pdf <name>.kicad_sch

# Jobsets: KiCad's built-in output pipeline, if one is defined
kicad-cli jobset run --stop-on-error -f <file>.kicad_jobset <name>.kicad_pro
```

KiCad files are S-expression text. They can be read and diffed directly, but prefer editing schematics and layouts in the KiCad GUI. Hand edits can corrupt UUIDs and references between files.
