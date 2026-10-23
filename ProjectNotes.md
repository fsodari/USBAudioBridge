# Project Notes

## Project initialization and First Draft

These are my observations about using Claude to vibe-code an entire PCB project.

The project was created using Claude Opus 5.5 on high in a single session. KiCAD 10.0.7 on Ubuntu WSL. Claude Pro subscription. It used about 85% of the 5 hour usage limit within 5 hours. I had to take a break to sleep after 5 hours, then picked it up again. The second vibe-code window took X hours. I had some of my weekly limit used already, but I think it used about X% of my weekly limit for the whole project.

I started with a basic and intentionally vague README.md outlining what I wanted out of this project. The README.md is unchanged since the start of the project. I find that Claude works well when given hard metrics to check against, so I required that all ERC/DRC must pass. All ERC/DRC passing is my usual standard anyways with KiCAD projects.

Accessing datasheets may require a meatbag to create an account and login to download datasheets. Before starting, ask Claude what datasheets/documentation it needs and it will give you a list. If you don't ask, Claude will try its best to figure it out without those datasheets which is probably not the way to go. I opted not to include the downloaded datasheets in this repo, but everything was free to download. NXP requires creating an account to download datasheets.

Claude will try to use tools installed on your system, but typically will opt to make its own tools if the tools it wants are not available. Before starting, ask Claude if there are any tools it would like you to install.

I indicated to Claude that I would like it to handle this project entirely by itself, but I said if there were any missing requirements or if the requirements were too vague, it should ask me for clarification. There were a few features that I left out or forgot that it clarified if I should add. It also made suggestions for "nice-to-have" features that I decided to include.

Once the design requirements were settled, I asked it to complete the schematic, then let me review it when it was done.

Claude will create a Python script to implement the schematic. Visual design aspects tend to be difficult for AI tools. Claude would often create a .png of the schematic sheet, review it, then fix any visual issues like crowded components, wrong rotations of components, misaligned connections, etc.

Once finished with the design, it gave a summary of the design decisions it made. It listed several decisions "worth checking in your review".

## First Draft Design Review

There were no series resistors on the USB data lines. Claude made no mention of this. I reminded Claude that this is a high speed USB 2.0 device and asked about the series resistors.

It said it followed digilent's PMOD I2S layout on pins 1-4 but it did not actually match. I added the PMOD I2S datasheet to the project and requested that it follow this standard. The digilent PMOD I2S module assumes the FPGA is generating the master clock, but in this project, the master clock is generated from this project's board. This didn't really matter, since the Arty A7 is flexible on pin assignment, but I wanted it to match the standard.

The SPI pinout did match digilent's standard.

It caught that digilent's standards for PMOD footprints and KiCADs 2x6 header do not number their pins the same way.

Some part selections were left out and remained in the "Still to do" phase.

It claimed it did not have a final part selected for the oscillator and also claimed that the oscillator did not have a 3D model. It appeared to have chosen an oscillator part number though. This seems to be a placeholder, but I will clarify.

Claude requested clarity on the MCP120 that the -300 grade had a 2.93V trip point. Digikey listed that it was a 2.925V trip point. Close enough?

It asked if I wanted to edit the schematic or keep its design.py script as the source of truth. I let Claude stay as the captain and told it that I would not manually edit the schematic. It will update the design.py script as the schematic changes.

## Post First Draft Design Review

Claude noted that the EVK does not use series resistors. No series resistors is the correct choice since the RT1010 has integrated termination with its PHY.

It updated the I2S PMOD to match digilent's PMOD i2S.

It finalized a part for the oscillator, considering jitter vs accuracy and noting that firmware will handle the accuracy errors with explicit asynchronous feedback.

## Post-Post First Draft Design Review

I asked if it was confident in the design. It ran a couple more checks to confirm symbol/pad parity and that the regulator pinout from the library matches the datasheet.

It asked which PCBA service to target for this design and recommended JLCPCB. I often go with PCBWay but went with its recommendation of JLCPCB here.

It asked how many layers and recommended 4 layers. 4 would have been my choice.

It asked how to route. It recommended scripting for placing parts and routing critical nets + Freerouting. Required Java 21+ and Freeroutin jar. I went with the recommendation.

It asked about mechanical mounting holes. I didn't have mounting holes in mind for this board, but I went with its recommendation. It had the right idea for coplanar installation with USB on the opposite side.

## Initial PCB layout

It asked me to install java openjdk-21-jre-headless while it did other things and said it would attempt to install Freerouting jar itself.

It figured out how to create a footprint for the correct pmod pin header.

It's working out footprint orientations.

It's marking mounting holes and test points as non-bom items.

It is acquiring Freerouting jar from github. It eventually switched to using Freerouting 2.1.0 which is compatible with Java 21 installed on the system.

Like the schematic layout, the pcb placement was done with python scripts.

It chose a stackup from JLCPCB ideal for USB high speed.

It builds python tools to help with layout. Compared to writing code/software, there is much more trial and error, but it is trying its best. Crowded/overlapping components seems to be a frequent pain-point.

Freerouting seemed to time out. Claude is investigating.

There was a lot of bus crossing with the I2S and SPI on JB/JC. Claude recommended swapping I2C to JC and SPI to JB. This requires a change to the schematic. This also required moving a number of parts around to accomodate.

Component rotations on the schematic and PCB are also a frequent pain-point. 90 degree vs 270 degree rotation for example. Claude seems to be able to figure this out on its own by creating .pngs of the layout.

Claude uses terminology like "taller" and "south-half". This is just something I found interesting.

Claude chose to keep silkscreen reference labels only on connectors, ICs, buttons, LEDs, crystals, the inductor, fuse, and test points. Omitting silkscreen labels for passives and only including those references on the fab layer. Not the choice I would make, but Claude has never had to debug or rework a board.

It chose assembling components on top and bottom. I should have required using components on one side only. It's fine. Decoupling caps and qspi flash are on the bottom. We'll review to make sure inductance is minimized.

Freerouting is slow and often leaves things unrouted. It has taken several passes. I wonder how well Claude would do routing things on its own.

Some of the freerouting failures are due to poor component placement. Claude is able to figure out the problems after the fact and make adjustments. Some more components were moved to the bottom.

It is taking several iterations of running Freerouting for about 20 minutes at a time. The issues that come up seem like they would be easy for a human to spot and fix.


