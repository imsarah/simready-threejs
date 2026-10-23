#!/usr/bin/env bash
# Full pipeline: download -> convert -> compress for the web.
#
#   ./tools/build_assets.sh food_produce_banana_m01 kitchenware_pan_n01 ...
#
# Output lands in ./assets as meshopt-compressed GLBs with WebP textures
# (~200-400 KB each instead of several MB).
set -euo pipefail

[ $# -eq 0 ] && { echo "usage: $0 <asset> [asset...]"; exit 1; }

python3 -m pip install --quiet usd-core numpy pygltflib pillow
pip_ok=$?
command -v npx >/dev/null || { echo "npx not found (needed for gltf-transform)"; exit 1; }

python3 tools/fetch_assets.py "$@"

mkdir -p build/glb assets
for asset in "$@"; do
  entry=$(ls data/"$asset"/simready_usd/*.usd | head -1)
  python3 tools/convert_simready.py "$entry" -o "build/glb/$asset.glb"
done

for f in build/glb/*.glb; do
  name=$(basename "$f")
  npx --yes @gltf-transform/cli optimize "$f" "assets/$name" \
      --compress meshopt --texture-compress webp --texture-size 1024
done

echo "done -> ./assets"
