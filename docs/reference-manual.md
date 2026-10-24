# USB Audio Bridge v1.0: Developer Reference Manual

This manual is for anyone writing software for the USB Audio Bridge board: the
**i.MX RT1010 firmware** and the **Arty A7 FPGA design** that talks to it. It is
the single place to look up pins, clocks, boot behaviour, interface protocols
and the board's known limitations. Everything here was checked against the
schematic generator (`tools/design.py`), the routed board, and the NXP and
Digilent documents in `docs/datasheets/` (cited as **RM** = i.MX RT1010
Reference Manual Rev. 0, **DS** = RT1010 data sheet, **HDUG** = RT1010 hardware
development guide).

Conventions:
- Pad names are NXP's (`GPIO_AD_05`), not package pin numbers. Pin numbers are
  given where they help with probing.
- "Board" means the USB Audio Bridge; "Arty" means the Digilent Arty A7.
- **Playback** means audio from the USB host to the FPGA. **Capture** means
  audio from the FPGA to the USB host.

---

## 1. System overview

```
                 USB-C (HS, bus powered)
                        |
              +---------+----------+        24.576 MHz XO --> CDCV304 1:4 buffer
              |  i.MX RT1011       |                            | Y0 -> SAI1_MCLK (GPIO_08)
 QSPI NOR --- |  Cortex-M7 500MHz  |                            | Y1 -> R603 (DNP), unused
 16 MB        |  USB OTG1 (device) |                            | Y2 -> JB1 (MCLK)
              |  SAI1  LPSPI1      |                            | Y3 -> JB7 (MCLK)
              +--+------+------+---+
                 |SAI1  |LPSPI1|GPIO
                 v      v      v
             PMOD JB (I2S)   PMOD JC (SPI + 4 GPIO)
                 |                 |
           Arty A7 port JB    Arty A7 port JC
```

- **USB side:** a USB 2.0 high-speed device on USB OTG1. It is intended to be
  an **asynchronous** USB Audio Class device: the 24.576 MHz audio oscillator
  is the timing master, and the host is told the true rate through a
  feedback endpoint.
- **FPGA side:** two I2S buses on JB using the Digilent Pmod I2S2 pinout. The
  RT1010 is the I2S clock master for both. JC carries a Type 2A expanded SPI
  port, an interrupt line, a reset line and two GPIOs.
- **Sample rates:** only the 48 kHz family (8, 16, 24, 32, 48, 96 and 192 kHz).
  There is no 22.5792 MHz clock, so 44.1 kHz and its multiples are not
  possible.

### Key facts

| Item | Value |
|---|---|
| MCU | MIMXRT1011DAE5A, LQFP-80, Cortex-M7, up to 500 MHz |
| On-chip RAM | 128 KB FlexRAM (ITCM/DTCM/OCRAM split, 32 KB banks) |
| Boot flash | Winbond W25Q128JVSIQ, 16 MB QSPI NOR on FlexSPI port A, XIP at `0x6000_0000` |
| System clock | 24.000 MHz crystal (Y301) and 32.768 kHz RTC crystal (Y302) |
| Audio clock | 24.576 MHz CMOS XO (X601, ±50 ppm), 512 × 48 kHz |
| Power | USB VBUS only, about 0.4 A worst case |
| Debug | 10-pin Cortex debug header (SWD + SWO), keyed (J501) |
| Console | LPUART1, 3-pin 2.54 mm header (J502), 3.3 V |
| User I/O | LED1 (green), LED2 (yellow), RESET button, BOOT button (readable after boot) |
| FPGA links | PMOD JB (I2S × 2), PMOD JC (SPI + INT + RST + 2 GPIO), all 3.3 V LVCMOS |

### Board orientation

Viewed from the top (component side), with the PMOD edge at the bottom:

```
 +-------------------------------------------+
 |  H1        [USB-C J101]  [UART J502]    H2 |   <- far edge
 |                                   PWR o    |   D101
 |                                  LED1 o    |   D501
 |                                  LED2 o    |   D502
 |      (RT1011 U1 is on the underside)       |
 |                                [SWD J501]  |
 |                                 (RESET)    |   SW301
 |                                            |
 |          (BOOT)                            |   SW401, between the PMODs
 |  [ J601 -> Arty JB ]   [ J602 -> Arty JC ] |   <- PMOD edge
 +-------------------------------------------+
```

The headers are right-angle. The board plugs flat into the Arty's JB and JC
ports, top side up, and the two M3 holes take a standoff so that USB cable
strain does not land on the PMOD headers.

---

## 2. Power

| Rail | Source | Loads | Test point |
|---|---|---|---|
| VBUS → +5V | USB-C, through a 0.5 A PTC (F101) | regulators, USB_OTG1_VBUS sense | TP101 (+5V) |
| +3V3 | AP7361C LDO (1 A) | RT1010 I/O and analog, flash, LEDs, pull-ups | TP102 |
| +3V3_CLK | LP5907 low-noise LDO | 24.576 MHz XO and CDCV304 buffer only | TP103 |
| VDD_SOC ("+1V1") | RT1010 internal DC-DC, 4.7 µH | RT1010 core | C201 |
| GND | | | TP104 |

- **Core voltage.** The DC-DC comes out of reset at 1.15 V
  (`DCDC_REG3[TRG]` = 0xE; 0.8 V + 25 mV per step, RM 18.7.1.5). That is
  enough for 396 MHz. **500 MHz needs overdrive, VDD_SOC 1.25–1.30 V** (DS
  Table 9). Before raising the core clock above 396 MHz, set `TRG` ≥ 0x12;
  0x13 = 1.275 V gives margin. Lower it again before dropping into
  low-power modes.
- **No PMOD power.** The board takes no power from the Arty, and the Arty
  takes none from the board. The PMOD VCC pins (6 and 12) go only to JP601, an
  open solder jumper. **Leave it open**: closing it ties two regulators
  together. Grounds are common through PMOD pins 5 and 11.
- **Power-sequencing rule for the FPGA.** Either board can be powered while
  the other is off. While the bridge is unpowered, any FPGA output driving JB
  or JC back-powers the RT1010 through its pad diodes. The JC8 reset protocol
  in §8.4 keeps the FPGA's outputs tri-stated until the RT1010 firmware is
  running.
- **USB power.** Declare a bus-powered configuration. `bMaxPower` = 150
  (300 mA) covers the worst-case estimate. Measure the current at bring-up
  and adjust.

---

## 3. Clocks

### 3.1 System clocks

- **24.000 MHz crystal** (XTALI/XTALO): the reference for every RT1010 PLL
  (ARM, SYS 528 MHz, USB1 480 MHz) and the USB PHY. The NXP SDK assumes
  24 MHz, so its clock code works unchanged.
- **32.768 kHz crystal** (RTC_XTALI/O): SNVS RTC and low-power timing.
  VDD_SNVS_IN runs from +3V3 with no backup battery, so the RTC loses time
  when USB power is removed.
- **Unused:** the RT1010 Audio PLL. The audio clock comes from the external
  oscillator (§3.2), never from a PLL.

### 3.2 Audio master clock (24.576 MHz)

```
X601 (24.576 MHz, +/-50 ppm) -> R601 22R -> U601 CDCV304
   Y0 (pin 3) -> R602 33R -> GPIO_08  SAI1_MCLK (input)
   Y1 (pin 5) -> R603 DNP -> GPIO_AD_03  (unused, see 3.4)
   Y2 (pin 7) -> R604 33R -> JB1  (MCLK, Arty E15, clock-capable)
   Y3 (pin 8) -> R605 33R -> JB7  (MCLK, Arty J17)
```

The RT1010 and the FPGA receive the same oscillator through one buffer, so
MCLK, BCLK and LRCLK are frequency-locked across both boards.

**RT1010 configuration** (RM 11.4.2, IOMUXC_GPR_GPR1; RM Table 10-1):

| Setting | Value | Meaning |
|---|---|---|
| `GPIO_08` mux | ALT0 | SAI1_MCLK pad |
| `IOMUXC_GPR->GPR1[19]` SAI1_MCLK_DIR | 0 | MCLK pad is an input |
| `IOMUXC_GPR->GPR1[2:0]` SAI1_MCLK1_SEL | 0b011 | SAI1 MCLK1 = `iomux.sai1_ipg_clk_sai_mclk` (the pad) |
| SAI1 `TCR2/RCR2[MSEL]` | 0b01 | bit clock generated from MCLK1 |
| `GPIO_08` pad control | hysteresis on | clean clock input |

> **Never set `SAI1_MCLK_DIR` = 1.** GPIO_08 is driven by the clock buffer,
> and the NXP EVK examples' `BOARD_EnableSaiMclkOutput(true)` would fight it
> (§7.7).

The SAI1 clock root (`SAI1_CLK_ROOT`) and the Audio PLL do not need to be
configured for audio. The SAI still needs its clock gate (`CCGR5` SAI1)
enabled for register access.

### 3.3 Bit-clock dividers

BCLK = MCLK / ((DIV + 1) × 2) (RM, `TCR2/RCR2[DIV]`). With two 32-bit slots per
frame (64 BCLK per sample):

| fs | BCLK | MCLK / fs | DIV |
|---|---|---|---|
| 8 kHz | 512 kHz | 3072 | 23 |
| 16 kHz | 1.024 MHz | 1536 | 11 |
| 24 kHz | 1.536 MHz | 1024 | 7 |
| 32 kHz | 2.048 MHz | 768 | 5 |
| **48 kHz** | **3.072 MHz** | **512** | **3** |
| 96 kHz | 6.144 MHz | 256 | 1 |
| 192 kHz | 12.288 MHz | 128 | 0 |

The SAI master timing (DS Table 37) is 15 ns maximum output valid and 15 ns
minimum input setup; it holds at every rate in the table.

### 3.4 The GPT2 counter cannot be used (design note)

The design originally fed MCLK to `GPIO_AD_03` (GPT2_CLK) so that a timer
could count audio clocks between USB start-of-frame packets. **That does
not work on this chip:**
- The GPT requires its external clock below 1/4 of its peripheral clock
  (RM 43.3.1).
- GPT2's peripheral clock is `PERCLK_CLK_ROOT` (RM 14, CCM clock table), whose
  maximum is 75 MHz (RM Table 14-5).
- So the external clock can be at most 18.75 MHz, below 24.576 MHz.

R603 is therefore **not fitted** in v1.0. GPIO_AD_03 is a spare input with a
short unterminated stub: configure it as a GPIO input with a pull-down or
keeper, or leave it in its reset state. Asynchronous feedback is computed from
the SAI sample count instead (§6.3), which needs no extra hardware.

---

## 4. RT1010 pin map

All I/O banks are 3.3 V (NVCC_GPIO). GPIO port numbers assume
`IOMUXC_GPR->GPR26` = 0 (its reset value), which routes GPIO_00–13 to
GPIO1_IO00–13, GPIO_AD_00–14 to GPIO1_IO14–28 and GPIO_SD_00–13 to
GPIO2_IO00–13.

### 4.1 Used pins

| Pin | Pad | Net | Function | Mux | Direction | Notes |
|---|---|---|---|---|---|---|
| 12 | GPIO_01 | I2S_RX_BCLK | SAI1_RX_BCLK | ALT0 | out | → R607 → JB3 |
| 11 | GPIO_02 | I2S_RX_LRCLK | SAI1_RX_SYNC | ALT0 | out | → R606 → JB2 |
| 10 | GPIO_03 | I2S_RX_DATA | SAI1_RX_DATA0 | ALT0 | in | ← R608 ← JB4 (capture data from the FPGA) |
| 9 | GPIO_04 | I2S_TX_DATA | SAI1_TX_DATA0 | ALT0 | out | → R611 → JB10 (playback data to the FPGA) |
| 6 | GPIO_06 | I2S_TX_BCLK | SAI1_TX_BCLK | ALT0 | out | → R610 → JB9; see §5.2 |
| 5 | GPIO_07 | I2S_TX_LRCLK | SAI1_TX_SYNC | ALT0 | out | → R609 → JB8; see §5.2 |
| 4 | GPIO_08 | MCLK_SAI | SAI1_MCLK | ALT0 | in | 24.576 MHz from U601 Y0 |
| 3 | GPIO_09 | UART_RX | LPUART1_RXD | ALT0 | in | J502-2; set `LPUART1_RXD_SELECT_INPUT` = 1 |
| 2 | GPIO_10 | UART_TX | LPUART1_TXD | ALT0 | out | J502-1; set `LPUART1_TXD_SELECT_INPUT` = 1 |
| 1 | GPIO_11 | LED1 | GPIO1_IO11 | ALT5 | out | green LED, active high |
| 80 | GPIO_12 | LED2 | GPIO1_IO12 | ALT5 | out | yellow LED, active high |
| 60 | GPIO_AD_00 | PMOD_INT | GPIO1_IO14 | ALT5 | in | ← R616 ← JC7, interrupt from the FPGA |
| 59 | GPIO_AD_01 | PMOD_GPIO0 | GPIO1_IO15 | ALT5 | bidir | JC9; also LPUART4_RXD (ALT0) or LPI2C2_SDA (ALT3) |
| 58 | GPIO_AD_02 | PMOD_GPIO1 | GPIO1_IO16 | ALT5 | bidir | JC10; also LPUART4_TXD (ALT0) or LPI2C2_SCL (ALT3) |
| 57 | GPIO_AD_03 | MCLK_GPT | (spare) | ALT5 | in | R603 not fitted, §3.4 |
| 56 | GPIO_AD_04 | SPI_MOSI | LPSPI1_SDO | ALT0 | out | → R613 → JC2 |
| 55 | GPIO_AD_05 | SPI_CS | LPSPI1_PCS0 | ALT0 | out | → R612 → JC1 |
| 52 | GPIO_AD_06 | SPI_SCK | LPSPI1_SCK | ALT0 | out | → R615 → JC4 |
| 51 | GPIO_AD_07 | PMOD_RST | GPIO1_IO21 | ALT5 | out | → R617 → JC8, FPGA reset (active low, §8.4) |
| 48 | GPIO_AD_09 | SWO | ARM_TRACE_SWO | ALT3 | out | J501-6; resets as JTAG_TDO (ALT7) |
| 47 | GPIO_AD_10 | JTAG_TDI | JTAG_TDI | ALT7 | in | J501-8 (reset default) |
| 46 | GPIO_AD_11 | JTAG_MOD | JTAG_MOD | ALT7 | in | 4.7 kΩ to GND = SWD (reset default) |
| 45 | GPIO_AD_12 | SWCLK | JTAG_TCK | ALT7 | in | J501-4 (reset default) |
| 44 | GPIO_AD_13 | SWDIO | JTAG_TMS | ALT7 | bidir | J501-2, 10 kΩ pull-up (reset default) |
| 70 | GPIO_SD_05 | SPI_MISO | LPSPI1_SDI | ALT2 | in | ← R614 ← JC3; set `LPSPI1_SDI_SELECT_INPUT` = 1 |
| 69 | GPIO_SD_06 | FLASH_CS | FLEXSPI_A_SS0_B | ALT0 | out | W25Q128 /CS, 10 kΩ pull-up |
| 68 | GPIO_SD_07 | FLASH_IO1 | FLEXSPI_A_DATA1 | ALT0 | bidir | |
| 67 | GPIO_SD_08 | FLASH_IO2 | FLEXSPI_A_DATA2 | ALT0 | bidir | 10 kΩ pull-up (/WP) |
| 66 | GPIO_SD_09 | FLASH_IO0 | FLEXSPI_A_DATA0 | ALT0 | bidir | |
| 65 | GPIO_SD_10 | FLASH_CLK | FLEXSPI_A_SCLK | ALT0 | out | |
| 64 | GPIO_SD_11 | FLASH_IO3 | FLEXSPI_A_DATA3 | ALT0 | bidir | 10 kΩ pull-up (/HOLD) |
| 62 | GPIO_SD_12 | (open) | FLEXSPI_A_DQS | ALT0 | — | leave unconnected: read-strobe loopback pad |
| 73 | GPIO_SD_03 | BOOT_MODE1 | GPIO2_IO03 | ALT5 | in | boot strap; BOOT button after boot (§7.2) |
| 72 | GPIO_SD_04 | BOOT_MODE0 | GPIO2_IO04 | ALT5 | in | boot strap; **never drive** (Q401 drives it) |
| 74–76 | GPIO_SD_02/01/00 | BT_CFG0/1/2 | GPIO2_IO02/01/00 | ALT5 | in | 10 kΩ pull-downs; keep as inputs |
| 33/32 | USB_OTG1_DP/DN | USB_DP/DN | USB OTG1 PHY | — | — | dedicated pins, no mux |
| 29 | USB_OTG1_VBUS | +5V | VBUS sense | — | — | after the PTC |
| 22 | POR_B | POR_B | reset in | — | — | MCP120 supervisor, RESET button, J501-10 |

**Daisy-chain (input select) registers you must set.** Several inputs can
come from more than one pad, and the reset defaults point at pads that are
used for something else on this board:

| Register | Value | Reset value selects (wrong here) |
|---|---|---|
| `IOMUXC_LPUART1_RXD_SELECT_INPUT` | 1 (GPIO_09) | GPIO_SD_11, the flash IO3 |
| `IOMUXC_LPUART1_TXD_SELECT_INPUT` | 1 (GPIO_10) | GPIO_SD_12 |
| `IOMUXC_LPSPI1_SDI_SELECT_INPUT` | 1 (GPIO_SD_05) | GPIO_AD_03 |
| `IOMUXC_LPSPI1_SCK_SELECT_INPUT` | 0 (GPIO_AD_06) | correct at reset; needed only in SPI slave mode |
| `IOMUXC_LPSPI1_SDO_SELECT_INPUT` | 0 (GPIO_AD_04) | correct at reset; needed only in SPI slave mode |
| `IOMUXC_LPUART4_RXD/TXD_SELECT_INPUT` | 0 (GPIO_AD_01/02) | correct at reset, if LPUART4 is used |
| `IOMUXC_LPI2C2_SDA/SCL_SELECT_INPUT` | 1 (GPIO_AD_01/02) | GPIO_AD_07/08, if LPI2C2 is used |

The NXP SDK's `IOMUXC_SetPinMux(IOMUXC_GPIO_09_LPUART1_RXD, ...)` style macros
set these automatically. Bare-metal code must write them. SAI1 and GPT2 have
only one pad per signal and no select registers.

### 4.2 Unused pads

`GPIO_00`, `GPIO_05` (SAI1 DATA1), `GPIO_13`, `GPIO_AD_08`, `GPIO_AD_14` and
`GPIO_SD_13` are not connected to anything. Leave them in their reset state, or
make them outputs driven low. ONOFF, PMIC_ON_REQ and USB_OTG1_CHD_B are
unconnected and rely on their on-chip pulls.

### 4.3 Pad settings

- **Outputs to the PMODs** already have 33 Ω source resistors on the board.
  Use a medium drive strength (`DSE` around 4–6) and slow slew for GPIO,
  and fast slew only for the SAI clocks if 192 kHz needs it.
- **Clock inputs** (`GPIO_08`, and `GPIO_AD_03` if it is ever used): turn
  hysteresis on.
- **Interrupt input** (`GPIO_AD_00`): enable the 100 kΩ pull-up so that an
  unpowered FPGA reads as "no interrupt".

---

## 5. Audio interface (SAI1 ↔ PMOD JB)

### 5.1 Signal map

JB uses the **Digilent Pmod I2S2 pinout**, seen from the FPGA as the host. The
board drives every clock: the FPGA must treat all MCLK, LRCLK and SCLK pins as
**inputs**.

| JB pin | Pmod I2S2 name | Net (board) | RT1010 | Arty FPGA pin | Dir (FPGA) | Carries |
|---|---|---|---|---|---|---|
| 1 | D/A MCLK | JB_RX_MCLK | (U601 Y2) | E15 (IO_L11P_T1_SRCC_15) | in | 24.576 MHz MCLK |
| 2 | D/A LRCK | JB_RX_LRCLK | GPIO_02 SAI1_RX_SYNC | E16 | in | capture LRCLK |
| 3 | D/A SCLK | JB_RX_BCLK | GPIO_01 SAI1_RX_BCLK | D15 (IO_L12P_T1_MRCC_15) | in | capture BCLK |
| 4 | D/A SDIN | JB_RX_DATA | GPIO_03 SAI1_RX_DATA0 | C15 | **out** | capture data, FPGA → RT1010 → USB host |
| 5 | GND | GND | | | | |
| 6 | VCC | PMOD_VCC | (JP601, open) | | | not connected |
| 7 | A/D MCLK | JB_TX_MCLK | (U601 Y3) | J17 | in | 24.576 MHz MCLK |
| 8 | A/D LRCK | JB_TX_LRCLK | GPIO_07 SAI1_TX_SYNC | J18 | in | playback LRCLK (independent mode only) |
| 9 | A/D SCLK | JB_TX_BCLK | GPIO_06 SAI1_TX_BCLK | K15 | in | playback BCLK (independent mode only) |
| 10 | A/D SDOUT | JB_TX_DATA | GPIO_04 SAI1_TX_DATA0 | J15 | in | playback data, USB host → RT1010 → FPGA |
| 11 | GND | GND | | | | |
| 12 | VCC | PMOD_VCC | (JP601, open) | | | not connected |

- **Clock-capable pins.** JB1 (E15, SRCC) and JB3 (D15, MRCC) are the only
  clock-capable P-side pins on the Arty's JB and JC ports. That is why I2S is
  on JB, and why MCLK and the bit clock sit on those two pins.
- **Coupled pairs.** The Arty routes pins (1,2), (3,4), (7,8) and (9,10) as
  coupled pairs. MCLK shares a pair with LRCLK. That is acceptable because
  LRCLK changes slowly and is only ever sampled.

### 5.2 Operating modes

**Mode S, synchronous (recommended).** SAI1 RX runs asynchronously as the
bit-clock and frame-sync master. TX is configured *synchronous with the
receiver*, so it uses the RX bit clock and frame sync internally (RM 32.5.3.1).
- Both directions share BCLK on JB3 and LRCLK on JB2. The FPGA clocks all of
  its I2S logic from the clock-capable JB3.
- The RM does not guarantee that the TX_BCLK and TX_SYNC pads (JB9, JB8)
  carry anything in this mode. **Firmware muxes GPIO_06 and GPIO_07 as
  GPIO outputs driven low** (GPIO1_IO06/07, ALT5), and the FPGA ignores JB8
  and JB9.
- Playback data on JB10 and capture data on JB4 are both timed to JB3.

**Mode I, independent.** RX and TX are both asynchronous masters with the
same divider settings. All eight JB signals are live and each row is a
complete I2S bus, which is what an off-the-shelf Pmod I2S2-style FPGA core
expects.
- The two rows run at exactly the same frequency (one MCLK), but with an
  arbitrary but constant phase offset.
- JB9 (K15) is not clock-capable. The FPGA must either oversample the
  bottom row from MCLK or a fast system clock, or use
  `CLOCK_DEDICATED_ROUTE FALSE`.

### 5.3 Frame format

Use standard I2S on both directions, in both modes:
- 2 slots × 32 bits per frame, MSB first.
- Data is delayed one BCLK after the LRCLK edge.
- LRCLK low = left channel.
- Data changes on the BCLK falling edge and is sampled on the rising edge.
- 24-bit audio sits left-justified in the 32-bit slot (the low 8 bits are 0).

SAI1 register recipe for Mode S at 48 kHz (RM chapter 32). Use the same
framing values for TX and RX:

| Register | Field | RX (async master) | TX (sync to RX) |
|---|---|---|---|
| xCR2 | SYNC | 00 | 01 (synchronous with receiver) |
| xCR2 | MSEL | 01 (MCLK1) | 01 |
| xCR2 | BCP | 1 (drive on falling, sample on rising) | 1 |
| xCR2 | BCD | 1 (master) | 1 |
| xCR2 | DIV | 3 (3.072 MHz, §3.3) | 3 |
| xCR3 | RCE/TCE | channel 0 | channel 0 |
| xCR4 | FRSZ | 1 (2 words per frame) | 1 |
| xCR4 | SYWD | 31 (frame sync 32 bits wide) | 31 |
| xCR4 | MF | 1 (MSB first) | 1 |
| xCR4 | FSE | 1 (frame sync one bit early) | 1 |
| xCR4 | FSP | 1 (active low: left channel while LRCLK is low) | 1 |
| xCR4 | FSD | 1 (master) | 1 |
| xCR5 | WNW / W0W / FBT | 31 / 31 / 31 | 31 / 31 / 31 |

- **Enable order:** enable TX first and RX last. Disable RX first.
- **SDK equivalent:**
  1. `SAI_GetClassicI2SConfig(&c, kSAI_WordWidth32bits, kSAI_Stereo, kSAI_Channel0Mask)`
  2. RX: `c.syncMode = kSAI_ModeAsync`; TX: `c.syncMode = kSAI_ModeSync`. Both: `c.masterSlave = kSAI_Master`.
  3. `SAI_TxSetBitClockRate(SAI1, 24576000, fs, 32, 2)`, and the same for RX.
- Move data with eDMA, using the DMAMUX SAI1 RX/TX requests.
- **SAI1 DATA1 (GPIO_05)** has no free PMOD pin and is not connected, so
  there is one data line in each direction.

### 5.4 Timing budget at 192 kHz (worst case)

At 192 kHz, BCLK = 12.288 MHz: period 81.4 ns, half period 40.7 ns.
- **RT1010 → FPGA:** data is valid at most 15 ns after the BCLK falling
  edge. The FPGA samples on the next rising edge, which leaves about 25 ns
  of setup.
- **FPGA → RT1010:** the RT1010 needs 15 ns setup before the rising edge. An
  FPGA launching on the falling edge of a BUFG-buffered JB3 clock has about
  25 ns for its clock-to-out plus board delay.
- At 48 kHz, every margin is four times larger.

---

## 6. USB audio

### 6.1 Device

- **Controller:** USB OTG1 (ChipIdea-style EHCI device controller) with the
  internal HS PHY. The SDK device stack is `usb_device_ehci`.
- **Terminations:** D+/D− have no series resistors on purpose; the PHY has
  calibrated on-die terminations (RM 36.3.5.1).
- **VBUS sense:** VBUS reaches USB_OTG1_VBUS after the PTC.
- **Class:** use **USB Audio Class 2.0** at high speed. Windows 10 1703+,
  macOS and Linux all have native UAC2 drivers.
- **Suggested topology:**
  - Clock source: internal, fixed or programmable over the 48 kHz family,
    marked as not synchronized to SOF.
  - Playback: OUT streaming interface, isochronous **asynchronous** endpoint
    with an **explicit feedback** IN endpoint.
  - Capture: IN streaming interface, isochronous asynchronous endpoint.
  - Formats: 2 channels, 24-bit in 32-bit subslots, or 16-bit.
- **Prototyping alternatives:** NXP's SDK USB audio examples, or TinyUSB's
  UAC2 examples, which support this controller.

### 6.2 Samples per microframe

At high speed there are 8000 microframes per second. At 48 kHz that is 6.000
samples per microframe nominally. Because the audio clock is the master, the
real rate is 48 kHz × (1 ± 50 ppm, the XO tolerance) as measured by the USB
host's clock.
- **Playback:** the host adjusts its packet sizes to follow the feedback
  value.
- **Capture:** the device sends however many samples it actually has (5, 6
  or 7 at 48 kHz) and keeps its capture buffer near half full.

### 6.3 Computing the feedback value

The feedback endpoint reports samples per microframe in **16.16 fixed point**
(4 bytes at high speed). Nominal 48 kHz is `0x0006_0000`.

There is no hardware counter of audio clocks against SOF (§3.4), so count
samples:
1. Enable the USB SOF interrupt (`USBINTR[SRE]`) and read the free-running
   SAI TX frame count at each SOF. The frame count is the number of eDMA
   major loops completed × loop length, plus words done in the current loop
   (from `CITER`), minus the TX FIFO fill level (`TFR0`). Every frame is
   exactly one LRCLK period of the 24.576 MHz oscillator, so the count
   measures the audio clock against the host's SOF clock.
2. Keep the counts from the last N = 2^k SOFs (k = 10, 128 ms, is a good
   start). Then

   `feedback = (count_now − count_N_ago) × 65536 / N`

   Each read is accurate to about ±1 sample. Taking the difference over a
   window cancels the error instead of accumulating it.
3. Check `FRINDEX` so that a missed SOF interrupt does not corrupt the
   window.
4. Add a small correction proportional to the playback buffer's distance
   from half full, so that start-up offsets drain away.

A pure FIFO-level servo (feedback = nominal + K × (target − level)) also
works. It is TinyUSB's `AUDIO_FEEDBACK_METHOD_FIFO_COUNT`, and is a quick way
to get started.

---

## 7. Boot, flash, debug and console

### 7.1 Boot modes

`BOOT_MODE[1:0]` is sampled on the rising edge of POR_B (RM 9.3.1) and can be
read back from `SRC_SBMR2[BMOD]`.

| BOOT_MODE[1:0] | How | Result |
|---|---|---|
| 10 (default) | straps: BOOT_MODE1 has a 10 kΩ pull-up, BOOT_MODE0 a 10 kΩ pull-down | internal boot from QSPI NOR on FlexSPI A |
| 01 | **hold BOOT (SW401), tap RESET (SW301), release BOOT** | serial downloader on USB (HID) and LPUART1 |

The BOOT button pulls BOOT_MODE1 low and, through P-FET Q401, drives
BOOT_MODE0 high. That selects the serial downloader whatever the eFuses say,
so a board with broken firmware can always be recovered.

### 7.2 BOOT button as a user input

After boot, the BOOT button can be read on **GPIO_SD_03 = GPIO2_IO03**,
active low: pressed reads about 0.3 V. GPIO_SD_04 goes high while it is
pressed, but **never configure GPIO_SD_04 as an output**, because Q401 drives
it.

### 7.3 Flash layout and configuration

FlexSPI NOR boot (RM 9.6.1, Table 9-8):

| Flash offset | Address | Content |
|---|---|---|
| 0x0000–0x03FF | 0x6000_0000 | reserved (OTFAD key blob if encrypted) |
| 0x0400–0x05FF | 0x6000_0400 | FlexSPI NOR configuration block (FCB, 512 B), read by the ROM at 30 MHz |
| 0x1000– | 0x6000_1000 | IVT and boot data, then the application (XIP) |
| up to 0xFF_FFFF | 0x60FF_FFFF | 16 MB total: the rest is free for data, audio tables or OTA images |

- **FCB.** Start from the SDK's EVK-MIMXRT1010
  `evkmimxrt1010_flexspi_nor_config.c`:
  - The EVK uses a 16 MB Adesto AT25SF128A on the same pads.
  - Its quad-I/O read LUT (0xEB, 24-bit address on 4 pads, 6 dummy cycles,
    read on 4 pads) is the standard one for Winbond W25Q-series parts.
  - `sflashA1Size` = 16 MB.
  - `readSampleClkSrc = kFlexSPIReadSampleClk_LoopbackFromDqsPad`, which is
    why GPIO_SD_12 is left open.
  - 100–133 MHz serial clock.
- **Quad enable.** The W25Q128JV*IQ* ordering code ships with the Quad
  Enable bit set. At bring-up, read status register 2 (command 0x35, bit 1)
  to confirm. If it reads 0, set it once with command 0x31. The JEDEC ID
  should read `EF 40 18`.
- **RAM.** FlexRAM is 128 KB in 32 KB banks. The SDK's RT1011 linker files
  assume the default fuse split of 32 KB ITCM (0x0000_0000), 32 KB DTCM
  (0x2000_0000) and 64 KB OCRAM (0x2020_0000). It can be reconfigured at run
  time through `IOMUXC_GPR->GPR16/17`.

### 7.4 Programming and recovery

1. **SWD (normal development).** Connect an MCU-Link, or any CMSIS-DAP or
   J-Link probe, to J501. MCUXpresso IDE / LinkServer, pyOCD or J-Link all
   work. Pick the **generic SFDP QSPI** flash driver for MIMXRT1010, not the
   EVK's part-specific one, if there is a choice.
2. **USB serial downloader (no probe).** Enter boot mode 01 (§7.1).
   - The board enumerates as an HID device, **VID 0x1FC9 / PID 0x0145**
     (RM Table 9-17).
   - Use NXP's MCUXpresso Secure Provisioning Tool, or SPSDK (`sdphost` to
     load the flashloader, then `blhost`), to write the FCB and image.
3. **UART serial downloader.** The same boot mode also listens on LPUART1
   (J502).

If firmware remuxes GPIO_AD_12/13, disables the debug clocks or sleeps
immediately, SWD may fail to attach. Recover with method 2, which never runs
the user's code.

### 7.5 Debug header J501

10-pin 1.27 mm Cortex debug connector, Samtec FTSH-105-01-L-DV-K with a
keying shroud. It mates with the MCU-Link's 10-pin cable in one orientation
only.

| Pin | Signal | Pin | Signal |
|---|---|---|---|
| 1 | +3V3 (VTref) | 2 | SWDIO (GPIO_AD_13, 10 kΩ pull-up) |
| 3 | GND | 4 | SWCLK (GPIO_AD_12) |
| 5 | GND | 6 | SWO (GPIO_AD_09) |
| 7 | key / NC | 8 | TDI (GPIO_AD_10) |
| 9 | GND | 10 | nRESET = POR_B |

- The probe can reset the board through pin 10.
- **JTAG_MOD** has a 4.7 kΩ pull-down, which selects SWD.
- **SWO** works only after firmware muxes GPIO_AD_09 to ALT3
  (ARM_TRACE_SWO) and enables the trace clock. At reset the pin is JTAG_TDO.
- The board's 3.3 V powers VTref only. **The probe cannot power the board.**

### 7.6 Console header J502

| Pin | Signal | Direction (board) |
|---|---|---|
| 1 | UART_TX (GPIO_10, LPUART1_TXD) | out |
| 2 | UART_RX (GPIO_09, LPUART1_RXD) | in |
| 3 | GND | |

- 3.3 V logic. Use a 3.3 V USB-UART adapter, its RX to pin 1 and TX to
  pin 2.
- Both lines have 10 kΩ pull-ups (HDUG Table 8).
- The SDK's EVK debug console also uses LPUART1 on GPIO_09/10, so SDK
  examples print here unmodified (115200 8N1).

### 7.7 LEDs and buttons

| Part | Signal | Behaviour |
|---|---|---|
| D101 PWR (green) | +3V3 | on whenever the 3.3 V rail is up |
| D501 LED1 (green) | GPIO1_IO11 (GPIO_11) | high = on, about 1 mA. This is the same pad as the EVK's user LED, so SDK `led_blinky` works unchanged |
| D502 LED2 (yellow) | GPIO1_IO12 (GPIO_12) | high = on |
| SW301 RESET | POR_B | hard reset (the MCP120 supervisor holds reset below 2.925 V) |
| SW401 BOOT | BOOT_MODE1/0, GPIO2_IO03 | boot mode 01 at reset (§7.1); user button after boot (§7.2) |

Do **not** reuse the EVK's `pin_mux.c` or board files wholesale. Generate the
pin mux with MCUXpresso Config Tools from the table in §4.1. Two differences
matter in particular:

- **MCLK direction.** The EVK's SAI and codec examples call
  `BOARD_EnableSaiMclkOutput(true)`, which sets `GPR1[SAI1_MCLK_DIR]` = 1
  and **drives GPIO_08 as an output**. On this board, GPIO_08 is driven by
  the CDCV304 through 33 Ω, so the two drivers would fight. Always keep
  `SAI1_MCLK_DIR` = 0.
- **User button.** The EVK's user button is GPIO_SD_05 (GPIO2_IO05). Here
  that pad is SPI MISO, and the button is on GPIO_SD_03 (§7.2).

---

## 8. SPI and GPIO port (PMOD JC)

### 8.1 Signal map

JC follows **PMOD Type 2A** (expanded SPI). Every signal has a 33 Ω series
resistor on the board.

| JC pin | Type 2A | Net | RT1010 | Arty FPGA pin | Dir (RT1010 as master) |
|---|---|---|---|---|---|
| 1 | CS | JC_SPI_CS | GPIO_AD_05 LPSPI1_PCS0 | U12 | RT1010 → FPGA |
| 2 | MOSI | JC_SPI_MOSI | GPIO_AD_04 LPSPI1_SDO | V12 | RT1010 → FPGA |
| 3 | MISO | JC_SPI_MISO | GPIO_SD_05 LPSPI1_SDI | V10 | FPGA → RT1010 |
| 4 | SCK | JC_SPI_SCK | GPIO_AD_06 LPSPI1_SCK | V11 | RT1010 → FPGA |
| 5, 11 | GND | | | | |
| 6, 12 | VCC | PMOD_VCC (JP601 open) | | | not connected |
| 7 | INT | JC_INT | GPIO_AD_00 (GPIO1_IO14) | U14 | FPGA → RT1010 |
| 8 | RESET | JC_RST | GPIO_AD_07 (GPIO1_IO21) | V14 | RT1010 → FPGA |
| 9 | GPIO | JC_GPIO0 | GPIO_AD_01 (GPIO1_IO15; LPUART4_RXD; LPI2C2_SDA) | T13 | either |
| 10 | GPIO | JC_GPIO1 | GPIO_AD_02 (GPIO1_IO16; LPUART4_TXD; LPI2C2_SCL) | U13 | either |

JC is bank 14 (pairs L20–L23) and has **no clock-capable pins**, so the FPGA
should treat SCK as data and oversample it.

### 8.2 SPI roles

- **RT1010 as master (recommended).** The firmware owns the control plane:
  it reads and writes FPGA registers and the FPGA raises INT.
  - LPSPI1 master, PCS0.
  - The DS limits LPSPI to 30 MHz absolute.
  - With a 100 MHz FPGA oversampler, run SCK at **≤ 12.5 MHz**. The limit
    is MISO turnaround: the FPGA must present MISO within half an SCK period,
    including its 2–3 cycle synchroniser.
  - Setting `LPSPI_CFGR1[SAMPLE]` = 1 samples MISO on the delayed SCK edge,
    which adds margin.
- **FPGA as master (alternative).** LPSPI1 runs in slave mode with
  `CFGR1[PINCFG]` = 0b11: SDO becomes the input and SDI the output, matching
  the Type 2A pin directions from the FPGA's side. The SCK/SDO select-input
  registers are correct at reset (§4.1).

### 8.3 Suggested register protocol

This is a starting point, not a requirement. Use SPI mode 0 and 8-bit words.

- **Transaction:** `[cmd] [addr] [data...]`.
  - cmd bit 7 = 1 for read, 0 for write; bits 6:0 = burst length − 1.
- **Reads:** the FPGA returns data from the byte after `addr` onward, which
  gives it one byte time to fetch.
- **Interrupts:** INT is active-low level, and is held until the RT1010
  clears the cause by a register write.

### 8.4 Reset and power-up handshake (JC8, JC7)

- **JC8 PMOD_RST.** The RT1010 drives it as an active-low reset for the
  FPGA's application logic. Give the FPGA's JC8 input a **PULLDOWN**:
  - While the bridge is unpowered, booting or held in reset, JC8 reads low
    and the FPGA logic stays in reset.
  - While in reset, the FPGA **tri-states all its outputs toward the
    bridge** (JB4, JC3, JC7, JC9, JC10). That prevents back-powering (§2).
  - Firmware drives JC8 high once its clocks and SAI are running.
- **JC7 PMOD_INT.** The RT1010 enables its pull-up, so an unpowered or
  tri-stated FPGA reads as "no interrupt".

---

## 9. Arty A7 (FPGA) development

### 9.1 Target

- **Boards:** Arty A7-35T (`xc7a35ticsg324-1L`) or Arty A7-100T
  (`xc7a100tcsg324-1`).
- **I/O voltage:** banks 14 (JC) and 15 (JB) run at VCCO = 3.3 V, so use
  `LVCMOS33` everywhere.
- **Port choice:** the bridge plugs into **JB and JC**, the Arty's
  high-speed ports, which have no series resistors. The board side has
  33 Ω.
- **Clocks:** the Arty's own 100 MHz oscillator (E3) stays available as the
  system clock.

### 9.2 Constraints (XDC)

Port names follow the USB direction: `cap_*` is capture (FPGA → host) and
`play_*` is playback (host → FPGA).

```tcl
## ---- PMOD JB: I2S (bridge J601), all clocks are inputs ----
set_property -dict {PACKAGE_PIN E15 IOSTANDARD LVCMOS33} [get_ports i2s_mclk]       ;# JB1  24.576 MHz, SRCC
set_property -dict {PACKAGE_PIN E16 IOSTANDARD LVCMOS33} [get_ports i2s_lrclk]      ;# JB2  LRCLK (both directions in mode S)
set_property -dict {PACKAGE_PIN D15 IOSTANDARD LVCMOS33} [get_ports i2s_bclk]       ;# JB3  BCLK, MRCC
set_property -dict {PACKAGE_PIN C15 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports cap_sdata] ;# JB4  FPGA -> RT1010
set_property -dict {PACKAGE_PIN J17 IOSTANDARD LVCMOS33} [get_ports i2s_mclk_b]     ;# JB7  24.576 MHz (second copy)
set_property -dict {PACKAGE_PIN J18 IOSTANDARD LVCMOS33 PULLDOWN true} [get_ports play_lrclk_b] ;# JB8  mode I only
set_property -dict {PACKAGE_PIN K15 IOSTANDARD LVCMOS33 PULLDOWN true} [get_ports play_bclk_b]  ;# JB9  mode I only
set_property -dict {PACKAGE_PIN J15 IOSTANDARD LVCMOS33} [get_ports play_sdata]     ;# JB10 RT1010 -> FPGA

## ---- PMOD JC: SPI + control (bridge J602) ----
set_property -dict {PACKAGE_PIN U12 IOSTANDARD LVCMOS33 PULLUP true} [get_ports spi_cs_n]  ;# JC1
set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} [get_ports spi_mosi]              ;# JC2
set_property -dict {PACKAGE_PIN V10 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports spi_miso] ;# JC3
set_property -dict {PACKAGE_PIN V11 IOSTANDARD LVCMOS33} [get_ports spi_sck]               ;# JC4
set_property -dict {PACKAGE_PIN U14 IOSTANDARD LVCMOS33 DRIVE 8 SLEW SLOW} [get_ports bridge_int_n] ;# JC7
set_property -dict {PACKAGE_PIN V14 IOSTANDARD LVCMOS33 PULLDOWN true} [get_ports bridge_rst_n] ;# JC8 (see 8.4)
set_property -dict {PACKAGE_PIN T13 IOSTANDARD LVCMOS33} [get_ports bridge_gpio0]          ;# JC9
set_property -dict {PACKAGE_PIN U13 IOSTANDARD LVCMOS33} [get_ports bridge_gpio1]          ;# JC10

## ---- Clocks and I/O timing (mode S, worst case 192 kHz) ----
create_clock -name i2s_mclk -period 40.690 [get_ports i2s_mclk]
create_clock -name i2s_bclk -period 81.380 [get_ports i2s_bclk]   ;# 12.288 MHz; slower rates only add margin
set_clock_groups -asynchronous -group i2s_mclk -group i2s_bclk -group [get_clocks -of_objects [get_ports CLK100MHZ]]
# RT1010 launches LRCLK/data on the BCLK falling edge, valid 0..15 ns later (DS Table 37)
set_input_delay  -clock i2s_bclk -clock_fall -max 15.0 [get_ports {play_sdata i2s_lrclk}]
set_input_delay  -clock i2s_bclk -clock_fall -min  0.0 [get_ports {play_sdata i2s_lrclk}]
# RT1010 samples capture data on the BCLK rising edge: 15 ns setup, 0 ns hold
set_output_delay -clock i2s_bclk -max 15.0 [get_ports cap_sdata]
set_output_delay -clock i2s_bclk -min  0.0 [get_ports cap_sdata]
```

- **Clock groups.** MCLK and BCLK come from the same oscillator but through
  different paths. Treat them as asynchronous to each other unless a design
  deliberately relates them.
- **JC is oversampled** in the 100 MHz domain, so it has no I/O timing
  constraints. Add `set_false_path` from those ports.

### 9.3 Recommended FPGA architecture

- **I2S core (mode S).** Put `i2s_bclk` (JB3) on a BUFG.
  - **play_sdata** (JB10): shift in on the BCLK rising edge.
  - **cap_sdata** (JB4): shift out on the BCLK falling edge.
  - **Frame:** detect left/right from LRCLK, sampled on the rising edge.
    Frames are 64 BCLK long.
  - **Clock crossing:** move samples to the 100 MHz (or MCLK) domain
    through a small async FIFO, or a toggle-handshake register, since one
    sample per channel arrives every 64 BCLK.
- **Audio-locked fast clock.** To get one for DSP, feed `i2s_mclk` (JB1,
  SRCC) into an MMCM, whose 10 MHz minimum input is satisfied. BCLK is too
  slow for an MMCM.
- **SPI slave.** Use the 100 MHz system clock:
  - Run a 2-flop synchroniser on SCK, CS and MOSI.
  - Detect SCK edges and shift on them.
  - Drive MISO from a register updated on the detected falling edge.
- **Start-up.** Hold application logic in reset and tri-state every output
  toward the bridge while `bridge_rst_n` is low (§8.4).

### 9.4 Mode I

If the RT1010 firmware runs mode I instead, treat the bottom row (JB7–10) as
its own I2S bus:
- Sample JB9/JB8/JB10 with the 100 MHz system clock and edge-detect BCLK.
  That is 8 samples per BCLK at 192 kHz, 32 at 48 kHz.
- Or put JB9 on a BUFG with `set_property CLOCK_DEDICATED_ROUTE FALSE` on its
  net, accepting the extra skew.

---

## 10. Bring-up checklist

1. **Power, with no Arty attached.** Check:
   - TP101 ≈ 5 V, TP102 = 3.3 V, TP103 = 3.3 V.
   - VDD_SOC at C201 ≈ 1.15 V at reset.
   - D101 lit.
   - Current from USB.
2. **Audio clock.** 24.576 MHz on JB1 and JB7 (probe at the header), and at
   GPIO_08 (R602).
3. **SWD.** Attach the MCU-Link, read the core ID, halt.
4. **Flash.** Read the JEDEC ID (`EF 40 18`) and SR2 bit 1 (QE). Program a
   blinky (LED1 on GPIO1_IO11) and confirm it boots without the probe.
5. **Console.** The SDK `hello_world` at 115200 on J502.
6. **Recovery.** Hold BOOT, tap RESET: VID 0x1FC9 / PID 0x0145 appears on the
   host.
7. **Core clock.** Raise `DCDC_REG3[TRG]` to 0x13 and run at 500 MHz.
8. **SAI.** Mode S at 48 kHz: BCLK 3.072 MHz on JB3, LRCLK 48 kHz on JB2.
   JB8 and JB9 are held low.
9. **USB.** Enumerates as UAC2 and plays a tone. Watch the feedback value
   converge on 6.0 ± 0.0003.
10. **Arty.** Load an FPGA loopback (JB10 → JB4) and confirm that capture
    returns the playback stream.
11. **JC.** SPI register read/write, INT round trip, and the JC8 reset
    handshake.

---

## 11. Limitations and errata (v1.0)

| # | Item | Impact | Workaround |
|---|---|---|---|
| 1 | GPT2 cannot count the 24.576 MHz MCLK (GPT external clock < PERCLK/4 ≤ 18.75 MHz) | no hardware audio-clock counter | R603 not fitted; feedback from SAI sample counts (§6.3) |
| 2 | 48 kHz family only | no 44.1/88.2/176.4 kHz | none on this board; it would need a 22.5792 MHz oscillator |
| 3 | SAI1 DATA1 (GPIO_05) not routed | one data line per direction: stereo I2S, or TDM if both sides support it | — |
| 4 | Mode S leaves JB8/JB9 undriven by the SAI | they are not a full Pmod I2S2 bottom row | park GPIO_06/07 as low GPIO outputs, or use mode I (§5.2) |
| 5 | 500 MHz needs VDD_SOC ≥ 1.25 V | the default 1.15 V allows only 396 MHz | raise `DCDC_REG3[TRG]` first (§2) |
| 6 | No RTC backup supply | the RTC resets on power loss | — |
| 7 | Unrouted pads: GPIO_00, GPIO_13, GPIO_AD_08, GPIO_AD_14, GPIO_SD_13 | no spare I/O on headers | JC9/JC10 are the spare GPIOs |

---

## 12. Where things live

| What | Where |
|---|---|
| Net and part source of truth | `tools/design.py`; it regenerates the schematic, so never hand-edit `hardware/*.kicad_sch` |
| Schematic PDF | `python3 tools/fab.py` → `hardware/build/fab/*/USBAudioBridge-v1.0-schematic.pdf` |
| Assembly drawings | same folder, `*-assembly-top.pdf` and `*-assembly-bottom.pdf` |
| Fabrication packages | `python3 tools/fab.py` (JLCPCB and PCBWay), or GitHub Actions (`.github/workflows/fab.yml`) |
| NXP documents | `docs/datasheets/` (RM, DS, HDUG, EVK schematic) |
| Digilent documents | `docs/datasheets/` (Arty A7 reference manual and schematic, Pmod I2S2, PMOD spec) |
