# USB Audio Bridge

KiCAD Project for a USB Audio Bridge based on an NXP RT1010

## Requirements

- NXP RT1010
- High Speed USB C connector
- MCU Link compatible SWD header
- 2 PMOD pin headers designed to mate with an Arty A7 development board
    - Route 2 I2S busses through one PMOD. One for input, one for output
    - Route SPI and GPIO through the second PMOD.
- Should be designed for a USB asynchronous audio class device.
- Should use a stable, accurate, 24.576Mhz oscillator for the Audio master clock

## KiCAD Project Requirements
- All erc/drc should pass
- Include 3D models for all parts
- Set up pipelines to generate design files that can be delivered to a PCBA manufacturer
