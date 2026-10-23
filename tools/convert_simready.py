"""Convert NVIDIA SimReady USD assets to web-ready glTF (.glb).

SimReady assets are layered USD: a thin entry stage payloads geometry, materials
and per-physics-engine instances from payloads/, using native instancing
(geometry lives inside prototypes, not at the traversed paths). Textures are
separate PNG files referenced relative to the authoring layer.

This converter walks the composed stage (prototypes included), bakes world
transforms, converts Z-up metres to Y-up glTF, and writes one .glb with albedo,
normal and ORM (metallic-roughness) textures embedded.

Usage:
    python convert_simready.py data/<asset>/simready_usd/<asset>.usd -o out/asset.glb
    python convert_simready.py data/*/simready_usd/*.usd --outdir out

Requires: usd-core numpy pygltflib pillow
"""
"""Convert SimReady USD assets to GLB — custom writer (PBR + textures + UVs)."""
import os, sys, json, glob, io
import numpy as np
import pygltflib
from pxr import Usd, UsdGeom, UsdShade, Gf

T = Usd.TimeCode.Default()
ALB_KEYS = ('diffuseColor', 'baseColor')

def localize(v, base_dir):
    if not v:
        return None
    v = str(v).strip().replace('@', '')
    if v.startswith('file://'):
        v = v[7:]
    return v if os.path.isabs(v) else os.path.normpath(os.path.join(base_dir, v))

def resolve_asset(layer, asset_path, base_dir):
    """Resolve an authored asset path relative to the layer that declares it."""
    a = str(asset_path).strip().replace('@', '')
    if not a:
        return None
    if a.startswith('file://'):
        a = a[7:]
    if os.path.isabs(a):
        return a
    if layer is not None:
        try:
            real = layer.realPath or layer.identifier
            return os.path.normpath(os.path.join(os.path.dirname(real), a))
        except Exception:
            pass
    return localize(a, base_dir)

def shader_of(mat_prim):
    if not mat_prim:
        return None
    sh, _, _ = UsdShade.Material(mat_prim).ComputeSurfaceSource()
    if sh and sh.GetPrim().IsValid():
        return UsdShade.Shader(sh.GetPrim())
    return None

def tex_path(sh, names, base_dir):
    for n in names:
        inp = sh.GetInput(n)
        if not inp:
            continue
        srcs = inp.GetConnectedSources()[0]
        if not srcs:
            continue
        node = srcs[0].source.GetPrim()
        if node.GetTypeName() != 'Shader':
            continue
        s = UsdShade.Shader(node)
        f = s.GetInput('file')
        if f and f.Get():
            stack = node.GetPrimStack()
            layer = stack[0].layer if stack else None
            return resolve_asset(layer, f.Get(), base_dir)
    return None

def scalar(sh, name, default):
    """Factor for a UsdPreviewSurface input, as glTF expects it.

    glTF multiplies metallicFactor/roughnessFactor with the metallicRoughness
    texture, so a texture-driven input must yield 1.0. Reading the connected
    node's `fallback` here would be wrong: it describes the texture, not the
    multiplier, and a 0.0 fallback erases the metal channel entirely.
    """
    inp = sh.GetInput(name)
    if not inp:
        return default
    if inp.GetConnectedSources()[0]:
        return 1.0
    v = inp.Get()
    return float(v) if v is not None and not hasattr(v, '__len__') else default

def material_info(mat_prim, base_dir):
    info = dict(albedo=None, normal=None, orm=None, metallic=0.0, roughness=0.5,
                color=[1.0, 1.0, 1.0, 1.0])
    sh = shader_of(mat_prim)
    if not sh:
        return info
    info['albedo'] = tex_path(sh, ALB_KEYS, base_dir)
    info['normal'] = tex_path(sh, ('normal',), base_dir)
    info['orm'] = tex_path(sh, ('roughness', 'metallic'), base_dir)
    info['metallic'] = min(1.0, max(0.0, scalar(sh, 'metallic', 0.0)))
    info['roughness'] = min(1.0, max(0.0, scalar(sh, 'roughness', 0.5)))
    dc = sh.GetInput('diffuseColor')
    if dc is not None:
        v = dc.Get()
        if isinstance(v, Gf.Vec3f) and not dc.GetConnectedSources()[0]:
            info['color'] = [float(v[0]), float(v[1]), float(v[2]), 1.0]
    return info

def collect(stage):
    for prim in stage.Traverse():
        if prim.IsInstance():
            proto = prim.GetPrototype()
            M = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(T)
            for p in Usd.PrimRange(proto):
                if p.IsA(UsdGeom.Mesh):
                    yield p, M, UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()[0]
        elif prim.IsA(UsdGeom.Mesh) and not prim.IsInstanceProxy():
            M = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(T)
            yield prim, M, UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]

def extract_mesh(prim, M, zup, mpu):
    m = UsdGeom.Mesh(prim)
    pts = m.GetPointsAttr().Get(T)
    if not pts:
        return None
    V = np.array([[p[0], p[2] * 0 + p[1], p[2]] for p in pts], dtype=np.float64)  # Z-up
    counts = np.array(m.GetFaceVertexCountsAttr().Get(T), dtype=np.int64)
    idx = np.array(m.GetFaceVertexIndicesAttr().Get(T), dtype=np.int64)
    # triangulate
    loops = []
    off = 0
    for c in counts:
        for k in range(1, c - 1):
            loops.append((idx[off], idx[off + k], idx[off + k + 1]))
        off += c
    tri = np.array(loops, dtype=np.int64)
    nloop = len(idx)                      # number of face-vertex loops
    nrm = m.GetNormalsAttr().Get(T)
    ninterp = m.GetNormalsInterpolation()
    nv = np.array([[p[0], p[1], p[2]] for p in nrm], dtype=np.float64) if nrm else None
    uvattr = prim.GetAttribute('primvars:st')
    st = np.array([[p[0], p[1]] for p in uvattr.Get(T)], dtype=np.float64) if uvattr and uvattr.Get(T) else None
    sti = prim.GetAttribute('primvars:st:indices')
    st_idx = np.array(sti.Get(T), dtype=np.int64) if sti and sti.Get(T) else None
    st_interp = uvattr.GetMetadata('interpolation') if uvattr else None

    # per-loop normals -> per triangulated corner
    if nv is not None and len(nv) == nloop:
        Nloop = nv
    elif nv is not None and len(nv) == len(V):
        Nloop = nv[idx]
    else:
        Nloop = None
    if st is not None:
        if st_idx is not None and len(st_idx) == nloop:
            UVloop = st[st_idx]
        elif len(st) == nloop:
            UVloop = st
        elif len(st) == len(V):
            UVloop = st[idx]
        else:
            UVloop = None
    else:
        UVloop = None

    # corner -> loop index mapping from triangulation
    corner_loop = []
    off = 0
    for c in counts:
        for k in range(1, c - 1):
            corner_loop.extend((off, off + k, off + k + 1))
        off += c
    cl = np.array(corner_loop, dtype=np.int64)

    corners = tri.reshape(-1)
    N = Nloop[cl] if Nloop is not None else None
    UV = UVloop[cl] if UVloop is not None else None
    if UV is not None:
        # USD texture coordinates have (0,0) at the lower-left of the image;
        # glTF/three.js sample with (0,0) at the upper-left. Without this flip,
        # atlased assets (e.g. the pan) map onto the wrong islands entirely.
        UV = np.column_stack([UV[:, 0], 1.0 - UV[:, 1]])
    P = V[corners]
    # Z-up -> Y-up (x, z, -y); apply prim world transform in USD space first
    Mm = np.array(M, dtype=np.float64).T
    P = (np.hstack([P, np.ones((len(P), 1))]) @ Mm.T)[:, :3]
    if N is not None:
        N = N @ Mm[:3, :3].T
    if zup:
        rot = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=np.float64)  # Z-up -> Y-up
        P = P @ rot.T
        if N is not None:
            N = N @ rot.T
    if mpu != 1.0:
        P = P * mpu
    if N is not None:
        ln = np.linalg.norm(N, axis=1, keepdims=True)
        ln[ln == 0] = 1
        N = N / ln
    return P.astype(np.float32), (N.astype(np.float32) if N is not None else None), \
        (UV.astype(np.float32) if UV is not None else None)

def build_glb(usd_path, out_glb, max_texture=1024):
    stage = Usd.Stage.Open(usd_path)
    base_dir = os.path.dirname(usd_path)
    zup = UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    mpu = UsdGeom.GetStageMetersPerUnit(stage) or 1.0

    gltf = pygltflib.GLTF2()
    gltf.scenes = [pygltflib.Scene(nodes=[])]
    gltf.scene = 0
    blobs = []          # bufferViews payload bytes
    views, accessors, meshes, mats, images, textures, nodes, samplers = [], [], [], [], [], [], [], []
    samplers.append(pygltflib.Sampler(magFilter=9729, minFilter=9987, wrapS=10497, wrapT=10497))
    img_cache = {}

    def add_view(data, target=None):
        bv = pygltflib.BufferView(buffer=0, byteOffset=None, byteLength=len(data), target=target)
        views.append(bv)
        blobs.append(data)
        return len(views) - 1

    def add_accessor(data, comp_type, type_, minv=None, maxv=None, target=None):
        bv = add_view(np.ascontiguousarray(data).tobytes(), target)
        acc = pygltflib.Accessor(bufferView=bv, componentType=comp_type,
                                 count=int(len(data)), type=type_)
        if minv is not None:
            acc.min = [float(x) for x in minv]
            acc.max = [float(x) for x in maxv]
        accessors.append(acc)
        return len(accessors) - 1

    def add_image(path):
        max_size = max_texture
        if path in img_cache:
            return img_cache[path]
        if not path or not os.path.exists(path):
            return None
        data = None
        try:
            from PIL import Image as _Im
            im = _Im.open(path)
            if max(im.size) > max_size:
                im = im.resize((max_size, max_size) if im.size[0] == im.size[1]
                               else (max_size, int(im.size[1] * max_size / im.size[0])), _Im.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, format='PNG', optimize=True)
                data = buf.getvalue()
        except Exception:
            data = None
        if data is None:
            with open(path, 'rb') as f:
                data = f.read()
        bv = add_view(data)
        images.append(pygltflib.Image(bufferView=bv, mimeType='image/png'))
        textures.append(pygltflib.Texture(sampler=0, source=len(images) - 1))
        img_cache[path] = len(textures) - 1
        return img_cache[path]

    n = 0
    for prim, M, mat_prim in collect(stage):
        res = extract_mesh(prim, M, zup, mpu)
        if res is None:
            continue
        P, N, UV = res
        if len(P) == 0:
            continue
        attrs = {}
        attrs['POSITION'] = add_accessor(P, 5126, 'VEC3', P.min(0), P.max(0), 34962)
        if N is not None:
            attrs['NORMAL'] = add_accessor(N, 5126, 'VEC3', target=34962)
        if UV is not None:
            attrs['TEXCOORD_0'] = add_accessor(UV, 5126, 'VEC2', target=34962)
        info = material_info(mat_prim, base_dir)
        alb = add_image(info['albedo'])
        nor = add_image(info['normal'])
        orm = add_image(info['orm'])
        pbr = pygltflib.PbrMetallicRoughness(
            baseColorFactor=info['color'],
            metallicFactor=info['metallic'],
            roughnessFactor=info['roughness'])
        if alb is not None:
            pbr.baseColorTexture = pygltflib.TextureInfo(index=alb)
        if orm is not None:
            pbr.metallicRoughnessTexture = pygltflib.TextureInfo(index=orm)
        mat = pygltflib.Material(name=f"mat{n}", pbrMetallicRoughness=pbr, doubleSided=True)
        if nor is not None:
            mat.normalTexture = pygltflib.NormalMaterialTexture(index=nor)
        mats.append(mat)
        meshes.append(pygltflib.Mesh(
            name=prim.GetName() + f"_{n}",
            primitives=[pygltflib.Primitive(attributes=attrs, material=len(mats) - 1)]))
        nodes.append(pygltflib.Node(name=prim.GetName() + f"_{n}", mesh=len(meshes) - 1))
        gltf.scenes[0].nodes.append(len(nodes) - 1)
        n += 1

    # assemble buffer
    offset = 0
    for bv, data in zip(views, blobs):
        bv.byteOffset = offset
        offset += len(data)
        offset += (-offset) % 4
    buf = bytearray(offset)
    for bv, data in zip(views, blobs):
        buf[bv.byteOffset:bv.byteOffset + len(data)] = data

    gltf.bufferViews = views
    gltf.accessors = accessors
    gltf.meshes = meshes
    gltf.materials = mats
    gltf.images = images
    gltf.textures = textures
    gltf.samplers = samplers
    gltf.nodes = nodes
    gltf.buffers = [pygltflib.Buffer(byteLength=len(buf))]
    gltf.set_binary_blob(bytes(buf))
    os.makedirs(os.path.dirname(out_glb), exist_ok=True)
    gltf.save(out_glb)
    return out_glb, n

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description="SimReady USD -> GLB converter")
    ap.add_argument("usd", nargs="+", help="entry .usd stage(s)")
    ap.add_argument("-o", "--out", help="output .glb (single input only)")
    ap.add_argument("--outdir", default="out", help="output directory (multi input)")
    ap.add_argument("--max-texture", type=int, default=1024, help="downscale textures above this size")
    args = ap.parse_args()
    for usd in args.usd:
        name = os.path.splitext(os.path.basename(usd))[0]
        out = args.out if args.out else os.path.join(args.outdir, name + ".glb")
        print(name, build_glb(usd, out, max_texture=args.max_texture))
