# Project Notes

## Project initialization and First Draft
These are my observations about using Claude to vibe-code an entire PCB project.

The project was created using Claude Opus 5.5 on high.

I started with a basic and vague README.md outlining what I wanted out of this project. The README.md is unchanged since the start of the project.

Downloading datasheets may require a meatbag to login and download datasheets. Before starting, ask Claude what datasheets/documentation it needs and it will give you a list.

Claude will try to use tools installed on your system, but typically will usually default to making its own tools if the tools it wants are not available. Before starting, ask Claude if there are any tools it would like you to install.

I indicated to Claude that I would like it to handle this project entirely by itself, but I said if there were any missing requirements or if the requirements were too vague, it should ask me for clarification. There were a few features that I left out or forgot that it clarified if I should add. It also made suggestions for "nice-to-have" features that I decided to include.

Once the design requirements were settled, I asked it to complete the schematic, then let me review it when it was done.

Claude will create Python tools to do much of the design. Visual design aspects tend to be difficult for AI tools. Claude would often create a .png of the schematic sheet, review it, then fix any visual issues like crowded components, wrong rotations of components, misaligned connections, etc.

Once finished with the design, it gave a summary of the design decisions it made. It listed several decisions "worth checking in your review".

## First Draft Design Review

There were no series resistors on the USB data lines. Claude made no mention of this. I reminded Claude that this is a high speed USB 2.0 device and asked about the series resistors.

It said it followed digilent's PMOD I2S layout on pins 1-4 but it did not actually match. I added the PMOD I2S datasheet to the project and requested that it follow this standard.

The SPI pinout did match digilent's standard.

It caught that digilent's standards for PMOD footprints and KiCADs 2x6 header do not number their pins the same.

Some part selections were left out and remained in the "Still to do" phase.

It claimed it did not have a final part selected for the oscillator and also claimed that the oscillator did not have a 3D model. It appeared to have chosen an oscillator part number though.

It requested clarity on the MCP120 that the -300 grade had a 2.93V trip point. Digikey listed that it was a 2.925V trip point. Close enough?

It asked if I wanted to edit the design or keep its design.py script. I let Claude stay as the captain and did not manually edit the schematic.

## Post First Draft Design Review

Claude noted that the EVK does not use series resistors.

It updated the I2S PMOD to match digilent's PMOD i2S.

It finalized a part for the oscillator.

## Post-Post First Draft Design Review

I asked if it was confident in the design. It ran a couple more checks to confirm symbol/pad parity and that the regulator pinout from the library matches the datasheet.

It asked which PCBA service to target for this design and recommended JLCPCB. I often go with PCBWay but went with JLCPCB here.

It asked how many layers and recommended 4 layers. 4 would have been my choice.

It asked how to route. It recommended scripting for placing parts and routing critical nets + Freerouting. Required Java 21+ and freerouting.jar. I went with the recommendation.

It asked about mechanical mounting holes. I didn't have mounting holes in mind for this board, but I went with its recommendation. It had the right idea for coplanar installation with USB on the opposite side.