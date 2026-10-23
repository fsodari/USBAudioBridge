# Project Notes

These are my observations about using Claude to vibe-code an entire PCB project.

The project was created using Claude Opus 5.5 on high.

I started with a basic and vague README.md outlining what I wanted out of this project. The README.md is unchanged since the start of the project.

Downloading datasheets may require a meatbag to login and download datasheets. Before starting, ask Claude what datasheets/documentation it needs and it will give you a list.

Claude will try to use tools installed on your system, but typically will usually default to making its own tools if the tools it wants are not available. Before starting, ask Claude if there are any tools it would like you to install.

I indicated to Claude that I would like it to handle this project entirely by itself, but I said if there were any missing requirements or if the requirements were too vague, it should ask me for clarification. There were a few features that I left out or forgot that it clarified if I should add. It also made suggestions for "nice-to-have" features that I decided to include.

Once the design requirements were settled, I asked it to complete the schematic, then let me review it when it was done.

Claude will create Python tools to do much of the design. Visual design aspects tend to be difficult for AI tools. Claude would often create a .png of the schematic sheet, review it, then fix any visual issues like crowded components, wrong rotations of components, misaligned connections, etc.

