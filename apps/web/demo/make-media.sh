#!/usr/bin/env bash
# Turns the demo's recording into the two published files (demo/README.md):
#   plumbline-demo.mp4  the whole walk-through, H.264, for the README and the release
#   plumbline-demo.gif  the first 90 seconds at 10 frames a second and 800 px wide, for the README
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
video="$(ls -t "$here"/../test-results/demo/*/video.webm | head -1)"
out="$here/../test-results/demo-media"
mkdir -p "$out"
ffmpeg -y -loglevel error -i "$video" -c:v libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart "$out/plumbline-demo.mp4"
ffmpeg -y -loglevel error -t 90 -i "$video" -vf "fps=10,scale=800:-1:flags=lanczos,palettegen=stats_mode=diff" "$out/palette.png"
ffmpeg -y -loglevel error -t 90 -i "$video" -i "$out/palette.png" \
  -lavfi "fps=10,scale=800:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4" "$out/plumbline-demo.gif"
rm "$out/palette.png"
ls -l "$out"
