#!/bin/sh
# Render the PCB to a PNG for visual review: render_pcb.sh OUT.png [LAYERS] [DPI]
set -e
HW="$(dirname "$0")/../hardware"
OUT="$1"
LAYERS="${2:-F.Cu,F.Fab,F.CrtYd,Edge.Cuts}"
DPI="${3:-600}"
TMP="$HW/build/render.pdf"
kicad-cli pcb export pdf --mode-single -l "$LAYERS" -o "$TMP" "$HW/USBAudioBridge.kicad_pcb" >/dev/null
# board occupies x 100..143.18, y 100..158 mm on the page; add 3 mm margins
px() { python3 -c "print(int(round($1 / 25.4 * $DPI)))"; }
pdftoppm -r "$DPI" -x "$(px 97)" -y "$(px 97)" -W "$(px 49.2)" -H "$(px 68)" -png -singlefile "$TMP" "${OUT%.png}"
