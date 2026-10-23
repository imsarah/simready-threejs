# simready-threejs

**NVIDIA SimReady assets that load in three.js.** True metric scale (1 unit = 1 m),
meshopt-compressed geometry, WebP textures — seven assets, 3.4 MB total.

SimReady ships as layered USD, which no browser can read. These are converted:
`UsdPreviewSurface` networks become glTF PBR materials, native-instance prototypes
are baked into real geometry, and the whole set is compressed for the web.

**Live demo & docs:** https://imsarah.github.io/simready-threejs/

```js
import { createLoader, loadAsset } from 'https://cdn.jsdelivr.net/gh/imsarah/simready-threejs@v0.1.1/src/simready-threejs.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js'

const loader = createLoader({ loaderClass: GLTFLoader, meshoptDecoder: MeshoptDecoder })
const { object, meta } = await loadAsset('cart_mobile_e01', { loader, THREE, floor: true })

scene.add(object)
meta.measured.size // → { x: 0.401, y: 1.579, z: 0.838 } metres
```

No library needed if you already have a loader — every file is a plain GLB:

```js
loader.load('https://cdn.jsdelivr.net/gh/imsarah/simready-threejs@v0.1.1/assets/box_corrugated_brown_b08.glb',
  (gltf) => scene.add(gltf.scene))
```

## What's in the box

| Asset | Size (m) | Triangles | GLB |
| --- | --- | --- | --- |
| `cart_mobile_e01` | 0.401 × 1.579 × 0.838 | 298,146 | 1.16 MB |
| `box_corrugated_brown_b08` | 0.297 × 0.304 × 0.304 | 15,999 | 367 KB |
| `kitchenware_pan_n01` | 0.204 × 0.053 × 0.360 | 15,392 | 171 KB |
| `food_prepared_cake_a01` | 0.086 × 0.070 × 0.104 | 6,990 | 211 KB |
| `food_produce_banana_m01` | 0.090 × 0.028 × 0.148 | 7,148 | 89 KB |
| `food_produce_tomato_a01` | 0.065 × 0.057 × 0.062 | 9,996 | 86 KB |
| `ppe_gloves_cloth_a01` | 0.233 × 0.053 × 0.252 | 202,266 | 1.30 MB |

Sizes are measured from the loaded geometry, not copied from docs.
`manifest.json` carries the same numbers plus source links and attribution.

Files are encoded with `EXT_meshopt_compression` (needs `MeshoptDecoder`) and
`EXT_texture_webp` (WebP, 1024 px max). Y-up, metres, no physics colliders.

## API

| Export | What it does |
| --- | --- |
| `createLoader({ loaderClass, meshoptDecoder })` | A `GLTFLoader` wired with the meshopt decoder these files require |
| `loadAsset(id, { loader, THREE, floor, shadows })` | Load one asset → `{ object, meta }`, optionally snapped to the floor |
| `loadAssets(ids, opts)` | Several at once, in order |
| `assetUrl(id)` | Absolute URL for an asset id |
| `setBase(url)` / `getBase()` | Switch resolution between the CDN (default) and same-origin (`setBase('./')`) |
| `snapToFloor(object, THREE)` | Move an object so its lowest point sits at y = 0 |
| `measure(object, THREE)` | Size and bounds in metres |
| `metreReference(THREE)` | A 1 m wireframe cube for scale sanity checks |
| `ASSETS` | The catalogue, inlined — no fetch needed |

## Examples in this repo

* `index.html` — docs page with a live real-scale viewer and the asset table
* `storeroom.html` — a full storeroom interior built at 1:1 from these assets
* `gallery.html` — turntable of the six small assets

## Where this came from

The interesting work is `tools/convert_simready.py`, which handles the three
things that break naive conversion of SimReady USD:

1. **Geometry hides in native-instance prototypes** — a plain prim traversal finds
   zero meshes; the meshes live under `__Prototype_*`, referenced by instances.
   Blender's stock exporter mishandles this in the other direction: it emits the
   prototypes *and* the instances, doubling triangle counts.
2. **UVs are indexed** (`primvars:st:indices`) and must be expanded to per-corner
   attributes, or textures come out scrambled.
3. **Texture paths resolve per authoring layer** — relative to
   `payloads/materials.usda`, not the entry stage.

```bash
python3 -m pip install usd-core numpy pygltflib pillow
python3 tools/fetch_assets.py food_produce_banana_m01        # download from HF
python3 tools/convert_simready.py data/…/*.usd -o out.glb    # USD → GLB
npx @gltf-transform/cli optimize out.glb assets/x.glb \
    --compress meshopt --texture-compress webp --texture-size 1024
# or just: tools/build_assets.sh <asset> ...
```

## Is this good enough for my project?

**Verified.** Eight assets converted correctly; one (eyeglasses, 82 MB of USD →
384 KB) was checked blind against published ground truth and matched exactly —
4 meshes, 42,168 triangles, 0.145 × 0.174 × 0.057 m.

**Limitations — read before relying on it:**

* **`UsdPreviewSurface` only.** MDL-only assets give wrong or missing textures,
  *silently*. Always eyeball output.
* **Default variant only.** SimReady physics variants (rigid/deformable) aren't
  selectable yet.
* **Props, not scenes.** Single assets up to ~300K triangles; assembly-level USD
  with nested references is untested.
* **No physics.** Colliders and mass stay in the SimReady USD.
* **WebP textures.** Perfect for browsers; Unity/Godot/native want
  `--texture-compress false` or PNG.
* **No decimation.** Triangle counts match the source; add `--simplify` if needed.

## Layout

```
index.html              docs + live real-scale demo (the site)
storeroom.html          example scene: a storeroom built at 1:1
gallery.html            turntable of the six small assets
src/simready-threejs.js the ESM module
manifest.json           catalogue: sizes, triangles, source links, licence
assets/*.glb            the converted assets
tools/                  fetch → convert → compress pipeline
```

## Run locally

Any static server works — ES modules and `.glb` fetches need HTTP, not `file://`.

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

## Deploy

Pure static files — no build, no bundler, no server code — hosted on **GitHub
Pages** straight from `main`:

```bash
gh api -X POST /repos/<owner>/<repo>/pages -f "source[branch]=main" -f "source[path]=/"
```

`vercel.json` is included if you prefer Vercel (`vercel deploy`); it only adds
long-lived cache headers for `assets/`.

## Licensing

* Assets: **CC BY 4.0** — NVIDIA SimReady, from
  [`nvidia/simready-assets`](https://huggingface.co/datasets/nvidia/simready-assets).
  Attribution required; see [LICENSE-assets.txt](LICENSE-assets.txt).
* Code (`src/`, `tools/`, HTML): **MIT**, see [LICENSE](LICENSE).

Not affiliated with or endorsed by NVIDIA.
