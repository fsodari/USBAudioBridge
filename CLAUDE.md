# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This is a KiCad 10 hardware project for a USB audio bridge built around an NXP i.MX RT1010 (MIMXRT1011DAE5A, LQFP-80). Revision v1.0 is complete and has been reviewed by the owner:
- Schematic and PCB: 43.18 × 62 mm, 4 layers, double-sided assembly, MCU on the bottom. ERC/DRC are clean.
- Every part has a 3D model and is sourced (MPN, manufacturer, LCSC number).
- `tools/fab.py` builds the JLCPCB and PCBWay packages, locally or in GitHub Actions.
- `docs/reference-manual.md` is the firmware/FPGA developer manual. Read it before writing RT1010 or Arty A7 code, and keep it in step with design changes.

## Layout

- `hardware/`: the KiCad project, `USBAudioBridge.kicad_pro`.
  - The root sheet has design notes and the pin map. Six sub-sheets: `power_usb`, `mcu_power`, `mcu_system`, `boot_flash`, `mcu_io`, `audio_pmod`.
  - `USBAudioBridge.kicad_sym` is the project symbol library. It holds the RT1010 as 4 units (A Power, B System/USB, C GPIO bank, D FlexSPI/SD bank) and the `+3V3_CLK` power symbol.
- `tools/`: a Python generator that produces the schematic. It uses only the standard library.
  - `design.py` describes every part, value, footprint and net, plus sourcing. `CAP_SRC`/`RES_SRC`/`LED_SRC` tables and `src()` fields give every BOM line an MPN, Manufacturer and LCSC number; `fab.py` refuses to build if one is missing.
  - `projlib.py` builds the RT1010 symbol from datasheet Tables 51 and 52.
  - `schgen.py` handles placement and rendering. Each pin gets a short stub plus a label or power symbol. `Sheet.link`/`tap` draw direct wires for local chains.
  - `build.py` regenerates, normalises and verifies (see below).
- `tools/fab.py`: fabrication outputs (see "Fabrication outputs" below). `.github/workflows/fab.yml` runs it in the `kicad/kicad:10.0.7` container.
- `docs/reference-manual.md`: the developer manual (pin map, clocks, boot, SAI/USB/SPI, Arty constraints, errata).
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
  - MCU supply and GND fanout (a via just inside the pad ring for each pin, with its cap on the opposite side, behind the via)
  - bulk-cap placement
  - generic plane-net fanout
- `pcb_silk.py` tidies the silkscreen. Reference designators stay on silk only for connectors, ICs, switches, LEDs, crystals and the like; the rest go to Fab. On Fab, the moved field is hidden where the library footprint already has a `${REFERENCE}` text, otherwise it is centred on the part, so the assembly drawings stay legible.
- `python3 tools/pcb.py --sync-fields` copies values, schematic fields and DNP flags onto the existing routed board without touching copper. Use it after a sourcing, value or DNP change; any footprint or part-count change needs a full rebuild and re-route.
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
  - `south_fanout()` dog-bone vias for MCU pins whose loads are on the opposite side (currently none: the flash and straps share the MCU's side)
- Freerouting is `tools/bin/freerouting-2.1.0.jar` (gitignored). It is the newest release that runs on the installed Java 21; 2.2 and later need Java 25.
  - Before routing, the DSN is edited: In1/In2 become `(type power)` so no signals go in the planes, and the scripted copper becomes `(type protect)`.
  - The F.Cu/B.Cu GND pours are added only after routing, so the router doesn't treat them as obstacles.
- Vias are 0.5 mm pad / 0.2 mm drill. The few 0.45 mm vias on USB and VBUS are deliberate. The 0.2 mm drill gives PCBWay's ≥ 5 mil outer annular ring, and JLCPCB charges nothing extra for it.
- VBUS and +5V use their own net class (PowerIn, 0.4 mm; the VBUS bus itself is a scripted 0.5 mm track). Worst-case input current is under 0.4 A (RT1010 DCDC_IN 200 mA plus VDD_HIGH 75 mA max, plus flash, clocks and LEDs), and the PTC trips around 1 A.
- Floorplan: the MCU is on the **bottom** side, mirrored, orientation 0 (`pcb_layout.MCU`, `MCU_LAYER`/`CAP_LAYER`).
  - The USB/crystal pins face the USB-C edge (north), the SAI pins face west toward JB (I2S), GPIO_AD (LPSPI1, SWD) faces east toward JC, and GPIO_SD (flash, straps) faces south.
  - This is the only arrangement where the I2S and SPI buses don't cross. With the MCU on top, SAI and LPSPI1 sit on opposite package sides that face the wrong ports.
  - MCU decoupling caps are on the top side under the chip. The crystals, DC-DC inductor and output caps, reset supervisor, flash and boot straps are on the bottom next to their pins.
  - The USB pair runs on F.Cu from the connector through the ESD array, then each line takes one via down to the MCU. D+ crosses over D− so the pair swaps sides, which matches the mirrored pin order.

## Design requirements (from README)

- MCU: NXP i.MX RT1010.
- High-speed USB-C connector.
- MCU-Link compatible SWD debug header. It's keyed: a Samtec FTSH-105-01-L-DV-K with a keying shroud. The footprint is built from Samtec's land pattern in `footprints.py`. Its 3D model may not be redistributed (SnapMagic terms), so `footprints.extract_models()` unpacks it from the owner's `docs/datasheets/FTSH-105-01-L-DV-K.zip` into gitignored `hardware/3rdparty/`.
- Two PMOD headers designed to mate with a Digilent Arty A7 FPGA board:
  - PMOD 1: two I2S buses, one input and one output.
  - PMOD 2: SPI and GPIO.
- The board targets a USB Audio Class **asynchronous** device. The audio clock is the timing master, and USB feedback endpoints report the rate to the host.
- The audio master clock comes from a stable, accurate 24.576 MHz oscillator. This is the 48 kHz-family MCLK (512 × 48 kHz), so it must feed the SAI/I2S MCLK path rather than being derived from the USB clock.

## Design decisions (confirmed with the owner)

- Power: USB VBUS only, through a 3.3 V LDO. The Arty PMOD VCC pins are not connected to the board's 3.3 V rail (at most a DNP solder jumper) so the two boards never back-feed each other. Grounds are shared.
- I2S: the RT1010 SAI is the clock master. It generates BCLK and LRCLK for both buses from the 24.576 MHz oscillator, and the oscillator's MCLK is buffered out to the FPGA on the I2S PMOD.
- The board mates with Arty A7 ports **JB + JC**, the two adjacent high-speed PMODs, which have no series resistors. JB carries I2S, JC carries SPI + GPIO.
- Extras: reset button and serial-downloader boot button, power and GPIO status LEDs, a 3-pin UART console header, and a 32.768 kHz RTC crystal.
- 44.1 kHz-family rates are out of scope: there is only a 24.576 MHz audio clock, so the 48 kHz family only.
- PCB: 4 layers, built by JLCPCB (their JLC04161H-3313 stackup) or PCBWay; `fab.py` produces both packages. Two M3 mounting holes take USB cable strain off the PMOD headers.
  - The board sits flat beside the Arty. The JB/JC headers are on one edge, on 0.9" (22.86 mm) centres per the PMOD spec, and the USB-C connector is on the far edge.
- Routing: critical nets are placed and routed by script through KiCad's `pcbnew` Python API. Freerouting finishes the rest headless.

## Design facts that took cross-referencing to establish

- **Audio clock:** the 24.576 MHz XO feeds a CDCV304 1:4 buffer.
  - Y0 → SAI1_MCLK input (GPIO_08). Firmware sets GPR1 `SAI1_MCLK_DIR=0` and `SAI1_MCLK1_SEL=011`, and must never set the direction to output. NXP EVK code does that with `BOARD_EnableSaiMclkOutput`.
  - Y1 → R603 (**DNP**) → GPT2_CLK (GPIO_AD_03). The GPT can't count it: its external clock must be below the GPT peripheral clock/4. That clock is PERCLK_CLK_ROOT, at most 75 MHz (RM Table 14-5), so the limit is 18.75 MHz. Async feedback is computed from SAI sample counts at each USB SOF (reference manual §6.3).
  - Y2/Y3 → PMOD JB1 and JB7, the MCLK pin of each I2S row.
  - The oscillator is an Epson SG-210SCBA 24.576000 MHz L (ordering code X1G004591A052, LCSC C5154204): ±50 ppm, 2.7–3.6 V. It is the same SG-210 package and pinout as the SG-210STF it replaced, which is out of stock at JLCPCB, so it uses the same footprint and 3D model.
- **Core voltage:** 500 MHz needs VDD_SOC 1.25–1.3 V (overdrive). The DC-DC resets to 1.15 V (`DCDC_REG3[TRG]`=0xE), which is good for 396 MHz.
- **SPI pins:** LPSPI1 uses GPIO_AD_04/05/06. Its SDI is on GPIO_SD_05 (ALT2, `LPSPI1_SDI_SELECT_INPUT=1`) because GPIO_AD_03 was reserved for GPT2_CLK.
- **Daisy defaults that bite:** `LPUART1_RXD_SELECT_INPUT` resets to GPIO_SD_11, which is the flash IO3 here, so it must be set to 1 for GPIO_09.
- **Boot:** BOOT_MODE[1:0]=10 (internal boot from FlexSPI-A QSPI NOR) is the default strap. The BOOT button pulls BOOT_MODE1 low and, through the P-FET Q401, BOOT_MODE0 high. That gives 01, the serial downloader, whatever the eFuse state.
- **I2S port (JB):** I2S is on **JB** (Digilent Pmod I2S2 pinout, FPGA as host) because the Arty's only clock-capable PMOD pins are on JB.
  - JB1 = E15 (IO_L11P_T1_SRCC_15) and JB3 = D15 (IO_L12P_T1_MRCC_15) are the clock-capable P pins, carrying MCLK and the top-row SCLK.
  - JC (bank 14, pairs L20–L23) has no clock-capable pins.
  - Run SAI1 TX synchronous to RX so the JB3 bit clock serves both directions.
  - Top row, pins 1–4 (MCLK/LRCK/SCLK/SDIN): FPGA→RT1010 audio on SAI1 RX.
  - Bottom row, pins 7–10 (MCLK/LRCK/SCLK/SDOUT): RT1010→FPGA audio on SAI1 TX.
  - This board drives all the clocks, so the FPGA must treat them as inputs.
  - SAI1 DATA1 (GPIO_05) has no free pin and is unconnected.
- **SPI port (JC):** JC follows PMOD Type 2A (expanded SPI).
- **Arty high-speed PMOD pairs:** pins (1,2), (3,4), (7,8) and (9,10) are routed as coupled pairs. With the I2S2 pinout, MCLK shares a pair with LRCK. That's accepted because LRCK changes slowly and is only sampled.
- **USB D+/D−:** no series resistors, on purpose. The RT1010 high-speed PHY has calibrated on-die 45 Ω terminations (reference manual §36.3.5.1), and the NXP evaluation board routes D+/D− directly.
- **Reset supervisor:** the MCP120T-300 trips at 2.925 V.
- **Sourcing substitutions:** these were checked against the JLCPCB library on 2026-10-23.
  - 24 MHz crystal: Suzhou Liming 3225-24-8-10-10/A. NXP wants a crystal rated ≥ 200 µW drive at ~50 Ω ESR; most 3225 parts are rated 100 µW.
  - Switches: C&K PTS810**SJG** (the SJM is out of stock).
  - USB-C: GCT USB4105-GF-A-**120**. The suffix is only the shell stake length.
  - LEDs: the KENTO KT-0603YG/Y parts have Vf ≈ 2 V; a 3 V "green" would be dark through 1 kΩ.
- **PMOD connector footprint:** J601 and J602 use Digilent pin numbering (1–6 on one row, 7–12 on the other). The stock KiCad `PinHeader_2x06` footprint numbers pins odd/even, so the PCB needs a custom footprint or a pin-map check.

## Fabrication outputs

```bash
python3 tools/fab.py           # ERC + DRC gate, then hardware/build/fab/USBAudioBridge-<rev>-{jlcpcb,pcbway}[.zip]
python3 tools/fab.py --step    # also a STEP model (local only: CI lacks the Samtec model)
```

- **Coordinates.** Gerbers, drill and placement files all use the drill/place origin, the board's lower-left corner (`pcb.set_origins`).
- **JLCPCB package:**
  - BOM columns Comment / Designator / Footprint / LCSC.
  - CPL uses pad-centroid positions. Rotations follow the kicad-jlcpcb-tools conventions: the bottom side is mirrored as 180 − rot, plus `JLC_ROTATION` corrections from the community database.
  - Check JLCPCB's placement preview when ordering.
- **PCBWay package:** a BOM with MPNs, plus a centroid file in KiCad's rotation convention, plus assembly drawings.
- **CI:** `.github/workflows/fab.yml` runs `fab.py` in the `kicad/kicad:10.0.7` container on pushes to main and on pull requests. A `v*` tag also attaches the zips to a GitHub release. The routed board is committed, so CI never needs Freerouting.

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
