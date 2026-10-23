/**
 * simready-threejs
 *
 * NVIDIA SimReady assets as web-ready glTF, at true metric scale.
 * 1 unit = 1 metre, Y-up, meshopt-compressed geometry, WebP textures.
 *
 * The point of this module is small and specific: SimReady USD can't be loaded
 * in a browser, and the pre-converted GLBs need two things the stock loader
 * doesn't do for you — a meshopt decoder, and the assumption that one world
 * unit is one metre (which is what lets you drop assets into a real-scale
 * scene without rescaling by eye).
 */

export const METERS_PER_UNIT = 1;

/** Base for the hosted assets (jsDelivr serves straight from the GitHub repo). */
export const CDN_BASE =
  'https://cdn.jsdelivr.net/gh/imsarah/simready-threejs@main/';

/**
 * Where `assetUrl()` resolves relative ids. Defaults to the public CDN; call
 * setBase('./') to load same-origin instead (faster, and what the demo pages do).
 */
let base = CDN_BASE;

export function setBase(next) {
  base = next.endsWith('/') ? next : next + '/';
}

export function getBase() {
  return base;
}

export const MANIFEST_URL = CDN_BASE + 'manifest.json';

/**
 * Asset catalogue, inlined so consumers don't need a fetch before using it.
 * Regenerate from manifest.json via `node tools/sync-manifest.mjs`.
 */
export const ASSETS = {
  'cart_mobile_e01': { name: 'mobile cart', sortOrder: 0, size: { x: 0.401, y: 1.579, z: 0.838 }, triangles: 298146, bytes: 1187792 },
  'box_corrugated_brown_b08': { name: 'corrugated carton', sortOrder: 1, size: { x: 0.297, y: 0.304, z: 0.304 }, triangles: 15999, bytes: 376024 },
  'kitchenware_pan_n01': { name: 'frying pan', sortOrder: 2, size: { x: 0.204, y: 0.053, z: 0.36 }, triangles: 15392, bytes: 175220 },
  'food_prepared_cake_a01': { name: 'cake slice', sortOrder: 3, size: { x: 0.086, y: 0.07, z: 0.104 }, triangles: 6990, bytes: 216004 },
  'food_produce_banana_m01': { name: 'banana', sortOrder: 4, size: { x: 0.09, y: 0.028, z: 0.148 }, triangles: 7148, bytes: 91556 },
  'food_produce_tomato_a01': { name: 'tomato', sortOrder: 5, size: { x: 0.065, y: 0.057, z: 0.062 }, triangles: 9996, bytes: 87700 },
  'ppe_gloves_cloth_a01': { name: 'PPE gloves', sortOrder: 6, size: { x: 0.233, y: 0.053, z: 0.252 }, triangles: 202266, bytes: 1329376 },
};

/**
 * Absolute URL for one asset.
 *
 *   'cart_mobile_e01'                    → base + assets/cart_mobile_e01.glb
 *   'assets/cart_mobile_e01.glb'         → base + assets/cart_mobile_e01.glb
 *   './assets/cart_mobile_e01.glb'       → left alone (explicit path)
 *   'https://elsewhere/x.glb'            → left alone (absolute URL)
 */
export function assetUrl(id) {
  if (/^[a-z][a-z0-9+.-]*:/i.test(id)) return id;            // absolute URL
  if (id.startsWith('.') || id.startsWith('/')) return id;   // explicit path
  const bare = id.replace(/^assets\//, '').replace(/\.glb$/i, '');
  return base + 'assets/' + bare + '.glb';
}

/**
 * A GLTFLoader wired for these assets.
 * Import three and the addons from the same version you already use:
 *
 *   import { createLoader } from 'simready-threejs'
 *   const loader = createLoader()
 */
export function createLoader({ loaderClass, meshoptDecoder, manager } = {}) {
  if (!loaderClass) {
    throw new Error(
      'createLoader needs a GLTFLoader class: createLoader({ loaderClass: GLTFLoader, meshoptDecoder: MeshoptDecoder })'
    );
  }
  const loader = new loaderClass(manager);
  // Meshopt is not optional for these files — geometry is compressed with
  // EXT_meshopt_compression, so a loader without the decoder yields nothing.
  if (meshoptDecoder) loader.setMeshoptDecoder(meshoptDecoder);
  return loader;
}

/** Snap an object so its lowest point sits on y = 0 (true scale, no rescaling). */
export function snapToFloor(object3D, THREE) {
  object3D.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(object3D);
  if (!Number.isFinite(box.min.y)) return object3D;
  object3D.position.y -= box.min.y;
  return object3D;
}

/** Measure an object in metres, as loaded. */
export function measure(object3D, THREE) {
  object3D.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(object3D);
  const size = box.getSize(new THREE.Vector3());
  return {
    size: { x: +size.x.toFixed(3), y: +size.y.toFixed(3), z: +size.z.toFixed(3) },
    min: { x: +box.min.x.toFixed(3), y: +box.min.y.toFixed(3), z: +box.min.z.toFixed(3) },
    max: { x: +box.max.x.toFixed(3), y: +box.max.y.toFixed(3), z: +box.max.z.toFixed(3) },
  };
}

/**
 * Load one asset and return a group ready to drop into a metric scene.
 *
 *   const { object, meta } = await loadAsset('cart_mobile_e01', {
 *     loader, THREE, floor: true, shadows: true,
 *   })
 *   scene.add(object)
 *
 * Options:
 *   floor    – snap the lowest point to y = 0
 *   shadows  – castShadow/receiveShadow on every mesh
 *   envMapIntensity – override material env response (defaults to 1)
 */
export async function loadAsset(id, { loader, THREE, floor = false, shadows = true, envMapIntensity = 1 } = {}) {
  if (!loader) throw new Error('loadAsset needs a loader: pass createLoader() output as { loader }');
  const gltf = await loader.loadAsync(assetUrl(id));
  const object = gltf.scene;
  object.traverse((o) => {
    if (!o.isMesh) return;
    if (shadows) {
      o.castShadow = true;
      o.receiveShadow = true;
    }
    for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
      if (m && 'envMapIntensity' in m) m.envMapIntensity = envMapIntensity;
    }
  });
  const entry = ASSETS[id];
  const meta = {
    id,
    name: entry ? entry.name : id,
    declaredSize: entry ? entry.size : null,
    measured: THREE ? measure(object, THREE) : null,
  };
  if (floor && THREE) snapToFloor(object, THREE);
  return { object, meta };
}

/** Load several at once; resolves to [{ id, object, meta }] in the order given. */
export async function loadAssets(ids, opts = {}) {
  const out = [];
  for (const id of ids) out.push({ id, ...(await loadAsset(id, opts)) });
  return out;
}

/**
 * A labelled 1-metre reference cube — the cheapest way to sanity-check that a
 * SimReady asset really is at metric scale in your scene.
 */
export function metreReference(THREE, { colour = 0x7fc4ff, opacity = 0.18 } = {}) {
  const geo = new THREE.BoxGeometry(1, 1, 1);
  const mat = new THREE.MeshBasicMaterial({ color: colour, wireframe: true, transparent: true, opacity });
  const cube = new THREE.Mesh(geo, mat);
  cube.position.y = 0.5;
  cube.name = 'metre-reference';
  return cube;
}
