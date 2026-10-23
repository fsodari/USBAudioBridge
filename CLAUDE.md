# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This is a KiCad 10 hardware project for a USB audio bridge built around an NXP i.MX RT1010 (MIMXRT1011DAE5A, LQFP-80). The schematic is drafted and awaiting the owner's review. No PCB or output pipeline exists yet.

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
- The board mates with Arty A7 ports **JB + JC**, the two adjacent high-speed PMODs, which have no series resistors.
- Extras: reset button and serial-downloader boot button, power and GPIO status LEDs, a 3-pin UART console header, and a 32.768 kHz RTC crystal.
- 44.1 kHz-family rates are out of scope: there is only a 24.576 MHz audio clock, so the 48 kHz family only.

## Design facts that took cross-referencing to establish

- **Audio clock:** the 24.576 MHz XO feeds a CDCV304 buffer with three outputs.
  - Output 1 → SAI1_MCLK input (GPIO_08). Firmware sets GPR1 `SAI1_MCLK_DIR=0` and `SAI1_MCLK1_SEL=011`.
  - Output 2 → GPT2_CLK (GPIO_AD_03). It counts MCLK between USB start-of-frame packets to compute the async feedback value. GPT external clock must stay below ipg_clk/4, so ipg_clk must be at least 98.4 MHz.
  - Output 3 → PMOD JB9.
- **SPI pins:** LPSPI1 uses GPIO_AD_04/05/06. Its SDI moves to GPIO_SD_05 (ALT2, `LPSPI1_SDI_SELECT_INPUT=1`) because GPIO_AD_03 is taken by GPT2_CLK.
- **Boot:** BOOT_MODE[1:0]=10 (internal boot from FlexSPI-A QSPI NOR) is the default strap. The BOOT button pulls BOOT_MODE1 low and, through the P-FET Q401, BOOT_MODE0 high. That gives 01, the serial downloader, whatever the eFuse state.
- **Arty high-speed PMOD pairs:** pins (1,2), (3,4), (7,8) and (9,10) are routed as coupled pairs. The JB pinout therefore pairs MCLK with the quiet aux data line and never puts two clocks in one pair. JB follows PMOD Type 7; JC follows Type 2A.
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
