#!/usr/bin/env python3
"""Hive Breach — original stylized sci-fi models built in Blender, exported as GLB."""
import bpy, bmesh, math, os, json
from pathlib import Path
from mathutils import Vector, Euler, Matrix, Quaternion

ROOT = Path("/workspace/hive-breach")
OUT = ROOT / "assets/models"
TEX = ROOT / "assets/textures"
SHOTS = ROOT / "shots/models"
OUT.mkdir(parents=True, exist_ok=True)
SHOTS.mkdir(parents=True, exist_ok=True)

# X right, Y forward (north / hive), Z up.
WAYPOINTS = [
    (0.0, 16.4, 0.16), (0.0, 12.2, 0.16), (5.6, 9.6, 0.16), (5.6, 5.2, 0.16),
    (-5.6, 2.4, 0.16), (-5.6, -1.6, 0.16), (5.6, -4.6, 0.16), (5.6, -8.8, 0.16),
    (0.0, -11.6, 0.16), (0.0, -15.6, 0.16),
]
PADS = [
    (-2.7, 13.4), (2.7, 13.4), (3.0, 10.6), (8.2, 7.4), (8.2, 5.0), (3.0, 4.6),
    (-3.0, 3.0), (-8.2, 2.4), (-8.2, -0.6), (-3.0, -2.2),
    (3.0, -3.8), (8.2, -4.6), (8.2, -8.8), (3.0, -9.6),
    (-2.7, -12.8), (2.7, -12.8),
]

def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 960
    scene.render.resolution_y = 1200
    scene.render.image_settings.file_format = "PNG"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.04, 0.05, 0.07, 1)
        bg.inputs[1].default_value = 1.0
    try:
        scene.eevee.taa_render_samples = 16
    except Exception:
        pass
    return scene

def active(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj

def apply_transforms(obj, loc=True, rot=True, scale=True):
    active(obj)
    bpy.ops.object.transform_apply(location=loc, rotation=rot, scale=scale)

def shade_auto(obj, angle=35):
    active(obj)
    for p in obj.data.polygons:
        p.use_smooth = True
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle), keep_sharp_edges=True)
    except Exception:
        try:
            bpy.ops.object.shade_smooth()
        except Exception:
            pass

def apply_mods(obj):
    active(obj)
    for mod in list(obj.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=mod.name)
        except Exception as e:
            print("WARN apply", obj.name, mod.name, e)

def add_bevel(obj, width=0.012, segments=3, angle=30):
    m = obj.modifiers.new("Bevel", "BEVEL")
    m.width = width
    m.segments = segments
    m.limit_method = "ANGLE"
    m.angle_limit = math.radians(angle)
    try:
        m.miter_outer = "MITER_ARC"
    except Exception:
        pass
    return m

def add_subsurf(obj, levels=2):
    m = obj.modifiers.new("Subsurf", "SUBSURF")
    m.levels = levels
    m.render_levels = levels
    return m

def join_objs(objs, name):
    objs = [o for o in objs if o is not None]
    if len(objs) == 1:
        objs[0].name = name
        return objs[0]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    objs[0].name = name
    return objs[0]

def set_origin(obj, loc):
    bpy.context.scene.cursor.location = Vector(loc)
    active(obj)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")

def parent_keep(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()

def princ_mat(name, color, rough=0.45, metal=0.0, emit=None, emit_str=0.0,
              coat=0.0, coat_rough=0.15, sss=0.0, sss_r=(0.6, 0.3, 0.2), alpha=1.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    p.location = (0, 0)
    col = list(color)
    if len(col) == 3:
        col.append(alpha)
    def sock(n, v):
        s = p.inputs.get(n)
        if s is None:
            return
        try:
            s.default_value = v
        except Exception:
            pass
    sock("Base Color", col)
    sock("Metallic", metal)
    sock("Roughness", rough)
    sock("Alpha", alpha)
    sock("Coat Weight", coat)
    sock("Coat Roughness", coat_rough)
    sock("Subsurface Weight", sss)
    if sss:
        sock("Subsurface Radius", list(sss_r))
        sock("Subsurface Scale", 0.15)
    if emit is not None:
        ec = list(emit) + [1] if len(emit) == 3 else list(emit)
        sock("Emission Color", ec)
        sock("Emission Strength", emit_str)
    nt.links.new(p.outputs[0], out.inputs[0])
    if alpha < 1:
        try:
            mat.blend_method = "BLEND"
        except Exception:
            pass
    return mat

def tex_mat(name, img_path, rough=0.7, metal=0.05, rough_path=None, scale=8.0):
    mat = princ_mat(name, (1, 1, 1), rough=rough, metal=metal)
    nt = mat.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(img_path))
    tex.location = (-500, 0)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapn = nt.nodes.new("ShaderNodeMapping")
    mapn.inputs["Scale"].default_value = (scale, scale, scale)
    nt.links.new(coord.outputs["UV"], mapn.inputs["Vector"])
    nt.links.new(mapn.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], p.inputs["Base Color"])
    if rough_path and Path(rough_path).exists():
        rtex = nt.nodes.new("ShaderNodeTexImage")
        rtex.image = bpy.data.images.load(str(rough_path))
        rtex.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mapn.outputs["Vector"], rtex.inputs["Vector"])
        nt.links.new(rtex.outputs["Color"], p.inputs["Roughness"])
    return mat

def assign(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    return obj

def set_vcol(obj, color):
    mesh = obj.data
    attr = mesh.color_attributes.get("Color")
    if attr is None:
        attr = mesh.color_attributes.new(name="Color", type="FLOAT_COLOR", domain="CORNER")
    r, g, b = color
    for i in range(len(attr.data)):
        attr.data[i].color = (r, g, b, 1.0)

def mesh_obj(name, loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    obj = bpy.context.object
    obj.name = name
    obj.location = Vector(loc)
    obj.rotation_euler = Euler(rot)
    if scale is not None:
        obj.scale = Vector(scale)
        apply_transforms(obj)
    return obj

def ico(name, r=1, subdiv=2, loc=(0, 0, 0), scale=None, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_ico_sphere_add(radius=r, subdivisions=subdiv, location=loc, rotation=rot)
    return mesh_obj(name, loc, rot, scale)

def uvsphere(name, r=1, seg=32, rings=16, loc=(0, 0, 0), scale=None, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, segments=seg, ring_count=rings, location=loc, rotation=rot)
    return mesh_obj(name, loc, rot, scale)

def cyl(name, r=1, d=1, seg=24, loc=(0, 0, 0), rot=(0, 0, 0), scale=None, caps=True):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=d, vertices=seg, location=loc, rotation=rot,
        end_fill_type="NGON" if caps else "NOTHING")
    return mesh_obj(name, loc, rot, scale)

def cube(name, size=1, loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    bpy.ops.mesh.primitive_cube_add(size=size, location=loc, rotation=rot)
    return mesh_obj(name, loc, rot, scale)

def cone(name, r1=1, r2=0, d=1, seg=24, loc=(0, 0, 0), rot=(0, 0, 0), scale=None):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=d, vertices=seg, location=loc, rotation=rot)
    return mesh_obj(name, loc, rot, scale)

def torus(name, major=1, minor=0.1, maj_seg=32, min_seg=16, loc=(0, 0, 0), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
        major_segments=maj_seg, minor_segments=min_seg, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    return obj

def curve_tube(name, points, radius=0.05, res=6, bev_res=4):
    data = bpy.data.curves.new(name, "CURVE")
    data.dimensions = "3D"
    data.resolution_u = res
    data.bevel_depth = radius
    data.bevel_resolution = bev_res
    data.use_fill_caps = True
    spline = data.splines.new("BEZIER")
    pts, rads = [], []
    for p in points:
        if isinstance(p, (tuple, list)) and len(p) == 2 and not isinstance(p[0], (int, float)):
            pts.append(Vector(p[0])); rads.append(p[1])
        else:
            pts.append(Vector(p)); rads.append(1.0)
    spline.bezier_points.add(len(pts) - 1)
    for i, (co, rad) in enumerate(zip(pts, rads)):
        bp = spline.bezier_points[i]
        bp.co = co
        bp.radius = rad
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    return obj

def to_mesh(obj):
    active(obj)
    bpy.ops.object.convert(target="MESH")
    return bpy.context.object

def hard(obj, bevel=0.02, seg=3, ang=32):
    add_bevel(obj, bevel, seg, ang)
    apply_mods(obj)
    shade_auto(obj, ang)
    return obj

def export_glb(objects, path, apply=True):
    path = Path(path)
    bpy.ops.object.select_all(action="DESELECT")
    roots = objects if isinstance(objects, (list, tuple)) else [objects]
    for r in roots:
        r.select_set(True)
        for c in r.children_recursive:
            c.select_set(True)
    bpy.context.view_layer.objects.active = roots[0]
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_apply=apply, export_extras=True, export_yup=True,
        export_cameras=False, export_lights=False, export_animations=False,
        export_skins=False, export_materials="EXPORT",
        export_texcoords=True, export_normals=True, export_attributes=True,
    )
    print("exported", path, "bytes", path.stat().st_size)

def hide_all():
    for o in bpy.data.objects:
        o.hide_render = True
        o.hide_viewport = True

def show_tree(obj):
    obj.hide_render = False
    obj.hide_viewport = False
    for c in obj.children_recursive:
        c.hide_render = False
        c.hide_viewport = False

def preview(obj, name, dist=4.0, height=1.4, look_z=0.8, front=False):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.get("PreviewCam") or bpy.data.cameras.new("PreviewCam")
    cam = bpy.data.objects.get("PreviewCam")
    if cam is None:
        cam = bpy.data.objects.new("PreviewCam", cam_data)
        bpy.context.collection.objects.link(cam)
    cam_data.lens = 85
    cam.location = (0.0, -dist, height) if front else (dist * 0.55, -dist * 0.85, height)
    loc = Vector((0, 0, look_z))
    cam.rotation_euler = (loc - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    def ensure_light(n, typ, loc, energy, color, size=2):
        obj = bpy.data.objects.get(n)
        if obj is None:
            data = bpy.data.lights.new(n, typ)
            obj = bpy.data.objects.new(n, data)
            bpy.context.collection.objects.link(obj)
        obj.location = loc
        obj.data.energy = energy
        obj.data.color = color
        if typ == "AREA":
            obj.data.size = size
        return obj
    ensure_light("Key", "AREA", (3.5, -3.0, 5.0), 250, (1.0, 0.96, 0.9), 4)
    ensure_light("Fill", "AREA", (-4.0, -1.5, 2.4), 80, (0.55, 0.7, 1.0), 5)
    ensure_light("Rim", "AREA", (0.5, 4.0, 3.0), 180, (1.0, 0.55, 0.85), 3)
    ensure_light("GroundBounce", "AREA", (0, 0, 0.1), 40, (0.4, 0.5, 0.45), 8)
    hide_all()
    show_tree(obj)
    cam.hide_render = True
    for ln in ("Key", "Fill", "Rim", "GroundBounce", "PreviewCam"):
        o = bpy.data.objects.get(ln)
        if o:
            o.hide_viewport = False
            if o.type == "LIGHT":
                o.hide_render = False
    fl = bpy.data.objects.get("StudioFloor")
    if fl is None:
        bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, -0.001))
        fl = bpy.context.object
        fl.name = "StudioFloor"
        assign(fl, princ_mat("StudioFloor", (0.06, 0.07, 0.08), rough=0.85))
    fl.hide_render = False
    fl.hide_viewport = False
    scene.render.filepath = str(SHOTS / f"{name}.png")
    bpy.ops.render.render(write_still=True)
    print("preview", scene.render.filepath)

def make_leg_set(prefix, hips, radius=0.038, up=0.14, out=0.28, foot_in=0.08):
    legs = []
    for i, (hx, hy, hz) in enumerate(hips):
        side = 1 if hx >= 0 else -1
        mid = (hx + side * out * 0.55, hy + 0.02, hz + up)
        knee = (hx + side * out, hy - 0.01, hz - up * 0.15)
        foot = (hx + side * (out - foot_in), hy + 0.04, 0.02)
        c = curve_tube(f"{prefix}_leg{i}", [
            ((hx, hy, hz), 1.15), (mid, 0.95), (knee, 0.75), (foot, 0.45),
        ], radius=radius, res=8, bev_res=3)
        legs.append(to_mesh(c))
        pad = uvsphere(f"{prefix}_foot{i}", r=radius * 1.5, seg=12, rings=8,
                       loc=(foot[0], foot[1], 0.025), scale=(1.3, 1.0, 0.55))
        legs.append(pad)
    return legs

def make_grunt():
    parts_body = []
    body = ico("GruntBody", r=0.22, subdiv=3, loc=(0, 0.04, 0.34), scale=(1.18, 1.42, 1.0))
    add_subsurf(body, 1); apply_mods(body); parts_body.append(body)
    abd = ico("GruntAbd", r=0.18, subdiv=3, loc=(0, -0.22, 0.30), scale=(1.15, 1.28, 0.95))
    add_subsurf(abd, 1); apply_mods(abd); parts_body.append(abd)
    head = ico("GruntHead", r=0.135, subdiv=3, loc=(0, 0.30, 0.40), scale=(1.12, 1.18, 1.0))
    add_subsurf(head, 1); apply_mods(head); parts_body.append(head)
    shell = ico("GruntShell", r=0.20, subdiv=3, loc=(0, 0.00, 0.42), scale=(1.05, 1.55, 0.55))
    add_subsurf(shell, 1); apply_mods(shell); parts_body.append(shell)
    ridge = cube("GruntRidge", size=0.12, loc=(0, 0.02, 0.52), scale=(0.28, 2.4, 0.35))
    add_subsurf(ridge, 2); apply_mods(ridge); parts_body.append(ridge)
    visor = cube("GruntVisor", size=0.14, loc=(0, 0.44, 0.42), scale=(1.85, 0.42, 0.7))
    add_subsurf(visor, 2); apply_mods(visor)
    assign(visor, princ_mat("GruntVisor", (0.7, 1.0, 0.15), rough=0.12, metal=0.05,
                            emit=(0.75, 1.0, 0.1), emit_str=8.0, coat=0.4))
    parts_body.append(visor)
    for sx in (-1, 1):
        eye = uvsphere(f"GruntEye{sx}", r=0.048, seg=16, rings=10, loc=(sx * 0.10, 0.46, 0.42))
        assign(eye, princ_mat("GruntEye", (0.85, 1.0, 0.2), rough=0.1, emit=(0.85, 1.0, 0.15), emit_str=12))
        parts_body.append(eye)
        m = curve_tube(f"GruntMand{sx}", [
            ((sx * 0.05, 0.40, 0.30), 1.0), ((sx * 0.10, 0.50, 0.26), 0.8), ((sx * 0.06, 0.58, 0.22), 0.45),
        ], radius=0.022, res=6, bev_res=3)
        parts_body.append(to_mesh(m))
        a = curve_tube(f"GruntAnt{sx}", [
            ((sx * 0.06, 0.32, 0.50), 1.0), ((sx * 0.10, 0.38, 0.68), 0.7), ((sx * 0.14, 0.30, 0.80), 0.4),
        ], radius=0.012, res=6, bev_res=2)
        parts_body.append(to_mesh(a))
        tip = uvsphere(f"GruntAntTip{sx}", r=0.018, seg=10, rings=8, loc=(sx * 0.14, 0.30, 0.80))
        assign(tip, princ_mat("GruntTip", (1, 0.3, 0.55), rough=0.2, emit=(1, 0.2, 0.5), emit_str=6))
        parts_body.append(tip)
    sac = ico("GruntSac", r=0.11, subdiv=2, loc=(0, -0.28, 0.22), scale=(0.9, 1.1, 0.7))
    assign(sac, princ_mat("GruntSac", (0.9, 0.15, 0.4), rough=0.25, sss=0.4, sss_r=(0.8, 0.2, 0.4),
                          emit=(1.0, 0.15, 0.45), emit_str=4.0, coat=0.3))
    parts_body.append(sac)
    hips = []
    for sy, yo in ((1, 0.16), (1, 0.00), (1, -0.16), (-1, 0.16), (-1, 0.00), (-1, -0.16)):
        hips.append((sy * 0.16, yo, 0.28))
    legs = make_leg_set("Grunt", hips, radius=0.032, up=0.16, out=0.30, foot_in=0.10)
    skin = princ_mat("GruntSkin", (0.14, 0.20, 0.16), rough=0.42, sss=0.18, sss_r=(0.4, 0.6, 0.3), coat=0.08)
    shell_m = princ_mat("GruntCarapace", (0.18, 0.28, 0.16), rough=0.28, metal=0.12, coat=0.35, coat_rough=0.12)
    assign(body, skin); assign(abd, skin); assign(head, skin); assign(shell, shell_m); assign(ridge, shell_m)
    keratin = princ_mat("GruntKeratin", (0.22, 0.18, 0.12), rough=0.3, metal=0.05)
    for o in parts_body:
        if not o.data.materials:
            assign(o, keratin)
        set_vcol(o, (0, 0, 0))
        shade_auto(o, 40)
    for o in legs:
        assign(o, princ_mat("GruntLeg", (0.12, 0.16, 0.13), rough=0.4, metal=0.08))
        set_vcol(o, (1, 0, 0))
        shade_auto(o, 40)
    grunt = join_objs(parts_body + legs, "AlienGrunt")
    set_origin(grunt, (0, 0, 0))
    grunt.rotation_euler[2] = math.pi
    apply_transforms(grunt)
    shade_auto(grunt, 40)
    return grunt

def make_tank():
    parts_body = []
    body = ico("TankBody", r=0.38, subdiv=3, loc=(0, 0.0, 0.52), scale=(1.25, 1.35, 0.95))
    add_subsurf(body, 1); apply_mods(body); parts_body.append(body)
    abd = ico("TankAbd", r=0.30, subdiv=3, loc=(0, -0.38, 0.48), scale=(1.2, 1.2, 0.9))
    add_subsurf(abd, 1); apply_mods(abd); parts_body.append(abd)
    head = ico("TankHead", r=0.22, subdiv=3, loc=(0, 0.42, 0.62), scale=(1.2, 1.15, 1.0))
    add_subsurf(head, 1); apply_mods(head); parts_body.append(head)
    for i, yo in enumerate((-0.15, 0.12, 0.35)):
        pl = cube(f"TankPlate{i}", size=0.3, loc=(0, yo, 0.72), scale=(1.15, 0.55, 0.22))
        add_bevel(pl, 0.04, 3); add_subsurf(pl, 1); apply_mods(pl); parts_body.append(pl)
    for sx in (-1, 1):
        sh = ico(f"TankShoulder{sx}", r=0.16, subdiv=2, loc=(sx * 0.38, 0.1, 0.58), scale=(1.1, 0.9, 0.8))
        parts_body.append(sh)
        h = curve_tube(f"TankHorn{sx}", [
            ((sx * 0.14, 0.48, 0.78), 1.0), ((sx * 0.22, 0.52, 1.02), 0.7), ((sx * 0.18, 0.40, 1.16), 0.3),
        ], radius=0.04, res=6, bev_res=3)
        parts_body.append(to_mesh(h))
    visor = cube("TankVisor", size=0.20, loc=(0, 0.64, 0.64), scale=(1.75, 0.40, 0.62))
    add_subsurf(visor, 2); apply_mods(visor)
    assign(visor, princ_mat("TankVisor", (1.0, 0.45, 0.12), rough=0.12, emit=(1.0, 0.4, 0.05), emit_str=8, coat=0.3))
    parts_body.append(visor)
    maw = ico("TankMaw", r=0.12, subdiv=2, loc=(0, 0.28, 0.42), scale=(0.9, 0.7, 0.6))
    assign(maw, princ_mat("TankMaw", (1.0, 0.2, 0.35), rough=0.2, emit=(1.0, 0.15, 0.3), emit_str=5, sss=0.3))
    parts_body.append(maw)
    hips = []
    for sx in (-1, 1):
        for yo in (0.22, -0.05, -0.32):
            hips.append((sx * 0.28, yo, 0.42))
    legs = make_leg_set("Tank", hips, radius=0.055, up=0.20, out=0.42, foot_in=0.12)
    skin = princ_mat("TankSkin", (0.16, 0.18, 0.14), rough=0.4, sss=0.12, coat=0.05)
    armor = princ_mat("TankArmor", (0.22, 0.26, 0.16), rough=0.25, metal=0.22, coat=0.4)
    horn_m = princ_mat("TankHorn", (0.28, 0.22, 0.12), rough=0.3, metal=0.1)
    assign(body, skin); assign(abd, skin); assign(head, skin)
    for o in parts_body:
        if not o.data.materials:
            assign(o, armor if ("Plate" in o.name or "Shoulder" in o.name) else horn_m)
        set_vcol(o, (0, 0, 0)); shade_auto(o, 40)
    for o in legs:
        assign(o, princ_mat("TankLeg", (0.13, 0.15, 0.12), rough=0.4, metal=0.1))
        set_vcol(o, (1, 0, 0)); shade_auto(o, 40)
    tank = join_objs(parts_body + legs, "AlienTank")
    set_origin(tank, (0, 0, 0))
    tank.rotation_euler[2] = math.pi
    apply_transforms(tank)
    shade_auto(tank, 40)
    return tank

def make_boss():
    parts_body = []
    body = ico("BossBody", r=0.70, subdiv=3, loc=(0, 0.0, 1.05), scale=(1.15, 1.25, 1.05))
    add_subsurf(body, 1); apply_mods(body); parts_body.append(body)
    abd = ico("BossAbd", r=0.55, subdiv=3, loc=(0, -0.7, 0.85), scale=(1.2, 1.35, 0.95))
    add_subsurf(abd, 1); apply_mods(abd); parts_body.append(abd)
    head = ico("BossHead", r=0.38, subdiv=3, loc=(0, 0.72, 1.35), scale=(1.15, 1.1, 1.0))
    add_subsurf(head, 1); apply_mods(head); parts_body.append(head)
    for i, sx in enumerate((-0.22, -0.08, 0.08, 0.22, 0.0)):
        yo = 0.70 if abs(sx) > 0.1 else 0.78
        h = 1.85 + (0.15 if sx == 0 else 0)
        sp = curve_tube(f"BossSpine{i}", [
            ((sx, yo, 1.6), 1.0), ((sx * 1.3, yo + 0.05, (1.6 + h) / 2), 0.6), ((sx * 1.5, yo - 0.05, h), 0.25),
        ], radius=0.055, res=6, bev_res=3)
        parts_body.append(to_mesh(sp))
    for i, (yo, zo, sx) in enumerate([(-0.2, 1.45, 1.3), (0.25, 1.55, 1.15), (-0.55, 1.15, 1.2)]):
        pl = cube(f"BossPlate{i}", size=0.5, loc=(0, yo, zo), scale=(sx, 0.5, 0.22))
        add_bevel(pl, 0.06, 3); add_subsurf(pl, 1); apply_mods(pl); parts_body.append(pl)
    visor = cube("BossVisor", size=0.32, loc=(0, 1.08, 1.36), scale=(1.85, 0.40, 0.7))
    add_subsurf(visor, 2); apply_mods(visor)
    assign(visor, princ_mat("BossVisor", (1.0, 0.25, 0.45), rough=0.1, emit=(1.0, 0.15, 0.35), emit_str=10, coat=0.4))
    parts_body.append(visor)
    for sx in (-1, 1):
        e = uvsphere(f"BossEye{sx}", r=0.08, seg=16, rings=10, loc=(sx * 0.22, 0.98, 1.35))
        assign(e, princ_mat("BossEye", (1, 0.4, 0.2), rough=0.1, emit=(1, 0.3, 0.05), emit_str=14))
        parts_body.append(e)
        m = curve_tube(f"BossMand{sx}", [
            ((sx * 0.16, 0.85, 1.05), 1.2), ((sx * 0.32, 1.15, 0.9), 0.9), ((sx * 0.22, 1.40, 0.7), 0.5),
        ], radius=0.06, res=8, bev_res=3)
        parts_body.append(to_mesh(m))
        arm = curve_tube(f"BossScythe{sx}", [
            ((sx * 0.55, 0.25, 1.15), 1.3), ((sx * 0.95, 0.45, 1.35), 1.0),
            ((sx * 1.15, 0.85, 1.05), 0.7), ((sx * 0.95, 1.25, 0.55), 0.35),
        ], radius=0.07, res=8, bev_res=3)
        parts_body.append(to_mesh(arm))
    for i, (yo, zo, sc) in enumerate([(-0.85, 0.55, 0.28), (-0.55, 0.45, 0.2), (0.15, 0.70, 0.16)]):
        s = ico(f"BossSac{i}", r=sc, subdiv=2, loc=(0, yo, zo), scale=(1.1, 1.2, 0.8))
        assign(s, princ_mat("BossSac", (1.0, 0.12, 0.4), rough=0.22, emit=(1.0, 0.1, 0.35), emit_str=6, sss=0.5, coat=0.25))
        parts_body.append(s)
    hips = []
    for sx in (-1, 1):
        for yo in (0.35, 0.05, -0.30, -0.62):
            hips.append((sx * 0.48, yo, 0.70))
    legs = make_leg_set("Boss", hips, radius=0.08, up=0.32, out=0.70, foot_in=0.18)
    skin = princ_mat("BossSkin", (0.12, 0.14, 0.12), rough=0.38, sss=0.15, coat=0.06)
    armor = princ_mat("BossArmor", (0.20, 0.16, 0.14), rough=0.22, metal=0.28, coat=0.45)
    assign(body, skin); assign(abd, skin); assign(head, skin)
    for o in parts_body:
        if not o.data.materials:
            assign(o, armor if "Plate" in o.name else princ_mat("BossKeratin", (0.25, 0.18, 0.14), rough=0.3, metal=0.1))
        set_vcol(o, (0, 0, 0)); shade_auto(o, 40)
    for o in legs:
        assign(o, princ_mat("BossLeg", (0.12, 0.13, 0.11), rough=0.4, metal=0.12))
        set_vcol(o, (1, 0, 0)); shade_auto(o, 40)
    boss = join_objs(parts_body + legs, "AlienBoss")
    set_origin(boss, (0, 0, 0))
    boss.rotation_euler[2] = math.pi
    apply_transforms(boss)
    shade_auto(boss, 40)
    return boss

def make_laser_turret():
    metal = princ_mat("LaserMetal", (0.18, 0.20, 0.24), rough=0.32, metal=0.75, coat=0.15)
    dark = princ_mat("LaserDark", (0.06, 0.07, 0.08), rough=0.4, metal=0.6)
    accent = princ_mat("LaserAccent", (0.05, 0.7, 0.9), rough=0.15, metal=0.3, emit=(0.2, 0.9, 1.0), emit_str=4)
    glow = princ_mat("LaserGlow", (0.3, 0.95, 1.0), rough=0.1, emit=(0.3, 0.95, 1.0), emit_str=12)
    root = bpy.data.objects.new("TurretLaser", None)
    bpy.context.collection.objects.link(root)
    base = cyl("Laser_Base", r=0.42, d=0.16, seg=16, loc=(0, 0, 0.08))
    hard(base, 0.02, 3); assign(base, metal); set_origin(base, (0, 0, 0)); parent_keep(base, root)
    for i in range(3):
        a = i * (2 * math.pi / 3) + math.pi / 6
        fx, fy = math.cos(a) * 0.48, math.sin(a) * 0.48
        foot = cube(f"Laser_Foot{i}", size=0.2, loc=(fx, fy, 0.06), rot=(0, 0, a), scale=(1.6, 0.7, 0.5))
        hard(foot, 0.02, 2); assign(foot, dark); parent_keep(foot, base)
    ped = cyl("Laser_Pedestal", r=0.16, d=0.28, seg=16, loc=(0, 0, 0.28))
    hard(ped, 0.015, 2); assign(ped, metal); parent_keep(ped, base)
    yaw = cyl("Turret_Yaw", r=0.22, d=0.10, seg=20, loc=(0, 0, 0.46))
    hard(yaw, 0.015, 3); assign(yaw, dark); set_origin(yaw, (0, 0, 0.46)); parent_keep(yaw, base)
    pitch = cube("Turret_Pitch", size=0.3, loc=(0, 0, 0.68), scale=(0.85, 1.35, 0.7))
    hard(pitch, 0.03, 3); assign(pitch, metal); set_origin(pitch, (0, 0, 0.68)); parent_keep(pitch, yaw)
    for sx in (-1, 1):
        v = cube(f"Laser_Vent{sx}", size=0.16, loc=(sx * 0.18, -0.02, 0.68), scale=(0.35, 1.0, 0.55))
        hard(v, 0.015, 2); assign(v, dark); parent_keep(v, pitch)
        s = cube(f"Laser_Strip{sx}", size=0.06, loc=(sx * 0.22, 0.0, 0.68), scale=(0.15, 1.6, 0.2))
        assign(s, accent); parent_keep(s, pitch)
    barrel = cyl("Turret_Barrel", r=0.08, d=0.55, seg=16, loc=(0, 0.42, 0.68), rot=(math.pi / 2, 0, 0))
    hard(barrel, 0.008, 2); assign(barrel, dark); set_origin(barrel, (0, 0.18, 0.68)); parent_keep(barrel, pitch)
    shroud = cyl("Laser_Shroud", r=0.12, d=0.18, seg=16, loc=(0, 0.28, 0.68), rot=(math.pi / 2, 0, 0))
    hard(shroud, 0.01, 2); assign(shroud, metal); parent_keep(shroud, pitch)
    muzzle = cyl("Turret_Muzzle", r=0.055, d=0.06, seg=16, loc=(0, 0.70, 0.68), rot=(math.pi / 2, 0, 0))
    assign(muzzle, glow); parent_keep(muzzle, barrel)
    ant = cyl("Laser_Ant", r=0.015, d=0.28, seg=8, loc=(0.08, -0.1, 0.90))
    assign(ant, dark); parent_keep(ant, pitch)
    tip = uvsphere("Laser_AntTip", r=0.025, seg=10, rings=8, loc=(0.08, -0.1, 1.05))
    assign(tip, accent); parent_keep(tip, pitch)
    return root

def make_tesla_turret():
    metal = princ_mat("TeslaMetal", (0.16, 0.16, 0.2), rough=0.3, metal=0.8, coat=0.1)
    dark = princ_mat("TeslaDark", (0.05, 0.05, 0.07), rough=0.38, metal=0.55)
    glow = princ_mat("TeslaGlow", (0.7, 0.35, 1.0), rough=0.08, emit=(0.7, 0.3, 1.0), emit_str=10)
    ring_m = princ_mat("TeslaRing", (0.5, 0.25, 0.95), rough=0.15, metal=0.4, emit=(0.6, 0.3, 1.0), emit_str=6)
    root = bpy.data.objects.new("TurretTesla", None)
    bpy.context.collection.objects.link(root)
    base = cyl("Tesla_Base", r=0.40, d=0.16, seg=16, loc=(0, 0, 0.08))
    hard(base, 0.02, 3); assign(base, metal); set_origin(base, (0, 0, 0)); parent_keep(base, root)
    for i in range(3):
        a = i * (2 * math.pi / 3)
        fx, fy = math.cos(a) * 0.48, math.sin(a) * 0.48
        foot = cube(f"Tesla_Foot{i}", size=0.2, loc=(fx, fy, 0.06), rot=(0, 0, a), scale=(1.5, 0.65, 0.5))
        hard(foot, 0.02, 2); assign(foot, dark); parent_keep(foot, base)
    col = cyl("Tesla_Column", r=0.10, d=1.15, seg=16, loc=(0, 0, 0.72))
    hard(col, 0.01, 2); assign(col, dark); parent_keep(col, base)
    for i, (z, maj, minor) in enumerate([(0.45, 0.28, 0.03), (0.72, 0.34, 0.035), (1.00, 0.26, 0.03), (1.22, 0.20, 0.025)]):
        r = torus(f"Tesla_Ring{i}", major=maj, minor=minor, maj_seg=28, min_seg=10, loc=(0, 0, z))
        shade_auto(r, 30); assign(r, ring_m); parent_keep(r, base)
    core = uvsphere("Tesla_Core", r=0.16, seg=24, rings=16, loc=(0, 0, 1.48))
    shade_auto(core, 40); assign(core, glow); parent_keep(core, base)
    shell = uvsphere("Tesla_Shell", r=0.20, seg=24, rings=16, loc=(0, 0, 1.48))
    shade_auto(shell, 40)
    assign(shell, princ_mat("TeslaGlass", (0.4, 0.2, 0.7, 0.25), rough=0.08, coat=0.6, alpha=0.35,
                            emit=(0.5, 0.2, 0.9), emit_str=1.5))
    parent_keep(shell, base)
    for i in range(4):
        a = i * math.pi / 2 + math.pi / 4
        rx, ry = math.cos(a) * 0.16, math.sin(a) * 0.16
        rod = cone(f"Tesla_Rod{i}", r1=0.025, r2=0.008, d=0.32, seg=8, loc=(rx, ry, 1.72))
        assign(rod, metal); parent_keep(rod, base)
    yaw = bpy.data.objects.new("Turret_Yaw", None)
    bpy.context.collection.objects.link(yaw)
    yaw.location = (0, 0, 0.2); parent_keep(yaw, base)
    pitch = bpy.data.objects.new("Turret_Pitch", None)
    bpy.context.collection.objects.link(pitch)
    pitch.location = (0, 0, 1.48); parent_keep(pitch, yaw)
    return root

def make_rocket_turret():
    metal = princ_mat("RktMetal", (0.20, 0.20, 0.22), rough=0.35, metal=0.7, coat=0.1)
    dark = princ_mat("RktDark", (0.07, 0.07, 0.08), rough=0.4, metal=0.5)
    stripe = princ_mat("RktStripe", (0.95, 0.35, 0.08), rough=0.35, metal=0.1, emit=(1.0, 0.35, 0.05), emit_str=1.5)
    glow = princ_mat("RktGlow", (1.0, 0.5, 0.1), rough=0.15, emit=(1.0, 0.45, 0.05), emit_str=8)
    root = bpy.data.objects.new("TurretRocket", None)
    bpy.context.collection.objects.link(root)
    base = cyl("Rkt_Base", r=0.44, d=0.16, seg=16, loc=(0, 0, 0.08))
    hard(base, 0.02, 3); assign(base, metal); set_origin(base, (0, 0, 0)); parent_keep(base, root)
    for i in range(3):
        a = i * (2 * math.pi / 3) + 0.4
        fx, fy = math.cos(a) * 0.50, math.sin(a) * 0.50
        foot = cube(f"Rkt_Foot{i}", size=0.2, loc=(fx, fy, 0.06), rot=(0, 0, a), scale=(1.55, 0.7, 0.5))
        hard(foot, 0.02, 2); assign(foot, dark); parent_keep(foot, base)
    ped = cyl("Rkt_Ped", r=0.18, d=0.22, seg=16, loc=(0, 0, 0.24))
    hard(ped, 0.015, 2); assign(ped, dark); parent_keep(ped, base)
    yaw = cyl("Turret_Yaw", r=0.24, d=0.10, seg=18, loc=(0, 0, 0.38))
    hard(yaw, 0.015, 3); assign(yaw, metal); set_origin(yaw, (0, 0, 0.38)); parent_keep(yaw, base)
    pitch = cube("Turret_Pitch", size=0.4, loc=(0, 0.05, 0.62), scale=(1.15, 1.0, 0.7))
    hard(pitch, 0.04, 4); assign(pitch, metal); set_origin(pitch, (0, 0, 0.62)); parent_keep(pitch, yaw)
    for sx in (-1, 1):
        s = cube(f"Rkt_Stripe{sx}", size=0.1, loc=(sx * 0.24, 0.05, 0.62), scale=(0.12, 1.6, 0.35))
        assign(s, stripe); parent_keep(s, pitch)
    tubes = [(-0.1, 0.12), (0.1, 0.12), (-0.1, -0.08), (0.1, -0.08)]
    nose_m = princ_mat("RktNose", (0.7, 0.72, 0.75), rough=0.25, metal=0.6)
    for i, (x, zoff) in enumerate(tubes):
        t = cyl(f"Rkt_Tube{i}", r=0.075, d=0.55, seg=14, loc=(x, 0.18, 0.62 + zoff), rot=(math.pi / 2, 0, 0))
        hard(t, 0.008, 2); assign(t, dark); parent_keep(t, pitch)
        lip = cyl(f"Rkt_Lip{i}", r=0.085, d=0.05, seg=14, loc=(x, 0.46, 0.62 + zoff), rot=(math.pi / 2, 0, 0))
        assign(lip, metal); parent_keep(lip, pitch)
        nose = cone(f"Rkt_Nose{i}", r1=0.05, r2=0.0, d=0.12, seg=12, loc=(x, 0.50, 0.62 + zoff), rot=(math.pi / 2, 0, 0))
        assign(nose, nose_m); parent_keep(nose, pitch)
    vent = cube("Rkt_Vent", size=0.16, loc=(0, -0.22, 0.62), scale=(1.2, 0.3, 0.5))
    hard(vent, 0.02, 2); assign(vent, glow); parent_keep(vent, pitch)
    dish = cyl("Rkt_Dish", r=0.10, d=0.04, seg=16, loc=(0, -0.05, 0.86))
    assign(dish, dark); parent_keep(dish, pitch)
    return root

def make_mech():
    """Hero mech, faces -Y (Blender front). Connected helmet, visor slit, chest reactor."""
    white = princ_mat("MechArmor", (0.90, 0.87, 0.80), rough=0.26, metal=0.12, coat=0.5, coat_rough=0.1)
    slate = princ_mat("MechSlate", (0.16, 0.18, 0.21), rough=0.32, metal=0.6, coat=0.12)
    orange = princ_mat("MechOrange", (0.98, 0.38, 0.08), rough=0.28, metal=0.04, emit=(1.0, 0.35, 0.05), emit_str=1.4)
    visor_m = princ_mat("MechVisor", (0.25, 0.95, 1.0), rough=0.06, metal=0.05, emit=(0.25, 0.9, 1.0), emit_str=10, coat=0.7)
    core_m = princ_mat("MechCore", (0.35, 0.95, 1.0), rough=0.08, emit=(0.3, 0.95, 1.0), emit_str=12, coat=0.5)

    root = bpy.data.objects.new("Mech_Root", None)
    bpy.context.collection.objects.link(root)

    def make_foot(name, sx):
        # Big weighty feet pointing toward -Y (toes at negative Y)
        foot = cube(name, size=0.42, loc=(sx * 0.42, -0.08, 0.13), scale=(1.05, 1.7, 0.52))
        hard(foot, 0.04, 3); assign(foot, white)
        set_origin(foot, (sx * 0.42, 0.0, 0.24))
        toe = cube(name + "_Toe", size=0.22, loc=(sx * 0.42, -0.38, 0.11), scale=(1.45, 0.7, 0.55))
        hard(toe, 0.03, 3); assign(toe, slate); parent_keep(toe, foot)
        stripe = cube(name + "_Stripe", size=0.09, loc=(sx * 0.42, -0.08, 0.25), scale=(1.5, 2.4, 0.16))
        assign(stripe, orange); parent_keep(stripe, foot)
        return foot

    def make_leg(side):
        sx = 1 if side == "R" else -1
        thigh = cyl(f"Mech_{side}Thigh", r=0.17, d=0.68, seg=16, loc=(sx * 0.42, 0.02, 0.92))
        hard(thigh, 0.03, 3); assign(thigh, white)
        set_origin(thigh, (sx * 0.42, 0.02, 1.24))
        shin = cyl(f"Mech_{side}Shin", r=0.16, d=0.60, seg=16, loc=(sx * 0.42, 0.0, 0.50))
        shin.scale = (1.2, 1.25, 1.0)
        apply_transforms(shin, loc=False, rot=False, scale=True)
        hard(shin, 0.03, 3); assign(shin, white)
        set_origin(shin, (sx * 0.42, 0.0, 0.74))
        knee = uvsphere(f"Mech_{side}Knee", r=0.14, seg=16, rings=10, loc=(sx * 0.42, -0.04, 0.74))
        shade_auto(knee, 40); assign(knee, slate); parent_keep(knee, shin)
        calf = cube(f"Mech_{side}Calf", size=0.30, loc=(sx * 0.42, -0.08, 0.44), scale=(1.05, 0.75, 1.15))
        hard(calf, 0.03, 3); assign(calf, white); parent_keep(calf, shin)
        stripe = cube(f"Mech_{side}CalfStripe", size=0.08, loc=(sx * 0.42, -0.20, 0.44), scale=(1.0, 0.2, 1.6))
        assign(stripe, orange); parent_keep(stripe, shin)
        foot = make_foot(f"Mech_{side}Foot", sx)
        parent_keep(foot, shin); parent_keep(shin, thigh)
        return thigh

    lthigh = make_leg("L"); rthigh = make_leg("R")
    pelvis = cube("Mech_Pelvis", size=0.52, loc=(0, 0.0, 1.32), scale=(1.65, 0.9, 0.55))
    hard(pelvis, 0.05, 3); assign(pelvis, slate)
    set_origin(pelvis, (0, 0, 1.32))
    parent_keep(pelvis, root); parent_keep(lthigh, pelvis); parent_keep(rthigh, pelvis)

    # Torso — slightly tapered heroic chest, facing -Y
    torso = cube("Mech_Torso", size=0.72, loc=(0, -0.04, 1.88), scale=(1.2, 0.82, 1.12))
    hard(torso, 0.06, 4); assign(torso, white)
    set_origin(torso, (0, 0, 1.55))
    parent_keep(torso, pelvis)
    # Collar that the head sits in (closes the neck gap)
    collar = cube("Mech_Collar", size=0.36, loc=(0, -0.02, 2.28), scale=(1.15, 1.0, 0.45))
    hard(collar, 0.04, 3); assign(collar, slate); parent_keep(collar, torso)
    # Chest plate + reactor on the FRONT (-Y)
    chest = cube("Mech_Chest", size=0.52, loc=(0, -0.22, 1.90), scale=(1.15, 0.32, 1.05))
    hard(chest, 0.04, 3); assign(chest, white); parent_keep(chest, torso)
    core = uvsphere("Mech_Core", r=0.15, seg=20, rings=12, loc=(0, -0.36, 1.86), scale=(1.15, 0.45, 1.15))
    shade_auto(core, 40); assign(core, core_m); parent_keep(core, torso)
    # Orange chevron above the reactor
    ch = cube("Mech_Chevron", size=0.18, loc=(0, -0.36, 2.12), scale=(1.5, 0.18, 0.32))
    assign(ch, orange); parent_keep(ch, torso)
    # Back vents (+Y)
    for sx in (-1, 1):
        v = cyl(f"Mech_Vent{sx}", r=0.09, d=0.16, seg=12, loc=(sx * 0.18, 0.32, 1.98), rot=(math.pi / 2, 0, 0))
        hard(v, 0.01, 2); assign(v, slate); parent_keep(v, torso)
        g = cyl(f"Mech_VentGlow{sx}", r=0.06, d=0.04, seg=12, loc=(sx * 0.18, 0.40, 1.98), rot=(math.pi / 2, 0, 0))
        assign(g, core_m); parent_keep(g, torso)

    def make_arm(side):
        sx = 1 if side == "R" else -1
        pauldron = ico(f"Mech_{side}Pauldron", r=0.24, subdiv=2, loc=(sx * 0.58, 0.0, 2.20), scale=(1.2, 1.05, 0.85))
        add_subsurf(pauldron, 1); apply_mods(pauldron); shade_auto(pauldron, 40)
        assign(pauldron, white); parent_keep(pauldron, torso)
        stripe = cube(f"Mech_{side}PStripe", size=0.12, loc=(sx * 0.66, -0.04, 2.24), scale=(0.28, 1.3, 0.55))
        assign(stripe, orange); parent_keep(stripe, pauldron)
        arm = cyl(f"Mech_{side}Arm", r=0.12, d=0.48, seg=14, loc=(sx * 0.68, 0.0, 1.86))
        hard(arm, 0.02, 3); assign(arm, white)
        set_origin(arm, (sx * 0.68, 0.0, 2.08)); parent_keep(arm, torso)
        fore = cyl(f"Mech_{side}Fore", r=0.14, d=0.46, seg=14, loc=(sx * 0.68, -0.02, 1.42))
        hard(fore, 0.025, 3); assign(fore, slate)
        set_origin(fore, (sx * 0.68, 0.0, 1.62)); parent_keep(fore, arm)
        fist = cube(f"Mech_{side}Fist", size=0.26, loc=(sx * 0.68, -0.12, 1.14), scale=(1.0, 1.25, 0.85))
        hard(fist, 0.03, 3); assign(fist, white); parent_keep(fist, fore)
        # Forearm cannon pointing -Y (forward)
        can = cyl(f"Mech_{side}Cannon", r=0.07, d=0.38, seg=12, loc=(sx * 0.68, -0.28, 1.20), rot=(math.pi / 2, 0, 0))
        hard(can, 0.01, 2); assign(can, slate); parent_keep(can, fore)
        muz = cyl(f"Mech_{side}Muzzle", r=0.045, d=0.05, seg=12, loc=(sx * 0.68, -0.48, 1.20), rot=(math.pi / 2, 0, 0))
        assign(muz, core_m); parent_keep(muz, fore)
        return arm

    make_arm("L"); make_arm("R")

    # Head — larger helmet sitting IN the collar, visor on the front
    head = cube("Mech_Head", size=0.46, loc=(0, -0.04, 2.48), scale=(1.05, 0.95, 0.9))
    hard(head, 0.045, 4); assign(head, white)
    set_origin(head, (0, 0, 2.32))
    parent_keep(head, torso)
    # Wide visor slit on the front face
    vis = cube("Mech_Visor", size=0.18, loc=(0, -0.24, 2.50), scale=(1.9, 0.18, 0.7))
    add_subsurf(vis, 2); apply_mods(vis); shade_auto(vis, 40)
    assign(vis, visor_m); parent_keep(vis, head)
    # Brow ridge
    brow = cube("Mech_Brow", size=0.12, loc=(0, -0.22, 2.62), scale=(2.4, 0.35, 0.35))
    hard(brow, 0.015, 2); assign(brow, slate); parent_keep(brow, head)
    crest = cube("Mech_Crest", size=0.14, loc=(0, 0.02, 2.72), scale=(0.32, 1.15, 0.45))
    hard(crest, 0.02, 2); assign(crest, orange); parent_keep(crest, head)
    for sx in (-1, 1):
        ant = cyl(f"Mech_Ant{sx}", r=0.018, d=0.18, seg=8, loc=(sx * 0.16, 0.06, 2.72))
        assign(ant, slate); parent_keep(ant, head)
    return root
def make_hive():
    """Crashed organic hive ship — ribs, glowing maw, landing spines sit OUTSIDE the hull."""
    chitin = princ_mat("HiveChitin", (0.16, 0.09, 0.11), rough=0.42, metal=0.06, coat=0.18)
    inner = princ_mat("HiveInner", (1.0, 0.12, 0.38), rough=0.18, emit=(1.0, 0.08, 0.32), emit_str=9, sss=0.45, sss_r=(0.9, 0.2, 0.4))
    vein = princ_mat("HiveVein", (0.95, 0.12, 0.4), rough=0.22, emit=(1.0, 0.1, 0.35), emit_str=6)
    dark = princ_mat("HiveDark", (0.05, 0.03, 0.04), rough=0.55, metal=0.1)
    plate_m = princ_mat("HivePlate", (0.20, 0.10, 0.13), rough=0.3, metal=0.12, coat=0.2)
    root = bpy.data.objects.new("HiveShip", None)
    bpy.context.collection.objects.link(root)

    # Hull slightly slimmer so surface details read
    hull = ico("HiveHull", r=1.45, subdiv=3, loc=(0, 0.2, 0.15), scale=(1.0, 2.2, 0.82))
    add_subsurf(hull, 1); apply_mods(hull); shade_auto(hull, 40); assign(hull, chitin); parent_keep(hull, root)
    rear = ico("HiveRear", r=1.05, subdiv=3, loc=(0, -2.4, 0.25), scale=(1.2, 1.15, 1.0))
    add_subsurf(rear, 1); apply_mods(rear); shade_auto(rear, 40); assign(rear, chitin); parent_keep(rear, root)

    # Exterior ribs — major radius larger than hull X (1.45)
    for i, yo in enumerate((-1.8, -0.8, 0.3, 1.3)):
        rib = torus(f"HiveRib{i}", major=1.50, minor=0.13, maj_seg=28, min_seg=10,
                    loc=(0, yo, 0.15), rot=(math.pi / 2, 0, 0))
        rib.scale = (1.0, 0.72, 1.0); apply_transforms(rib)
        shade_auto(rib, 40); assign(rib, plate_m); parent_keep(rib, root)

    # Open maw at +Y (will be rotated 180 to face down the path / -Y)
    # Dark lip + glowing interior shell that clearly protrudes
    lip = torus("HiveLip", major=0.95, minor=0.16, maj_seg=24, min_seg=10,
                loc=(0, 3.15, 0.05), rot=(math.pi / 2, 0, 0))
    lip.scale = (1.0, 0.8, 1.0); apply_transforms(lip)
    shade_auto(lip, 40); assign(lip, plate_m); parent_keep(lip, root)
    cavity = ico("HiveCavity", r=0.95, subdiv=2, loc=(0, 2.7, 0.05), scale=(0.95, 0.7, 0.8))
    shade_auto(cavity, 40); assign(cavity, dark); parent_keep(cavity, root)
    glow = ico("HiveMawGlow", r=0.70, subdiv=2, loc=(0, 2.85, 0.05), scale=(0.9, 0.55, 0.75))
    shade_auto(glow, 40); assign(glow, inner); parent_keep(glow, root)
    fang_m = princ_mat("HiveFang", (0.25, 0.1, 0.12), rough=0.25, metal=0.08)
    for sx in (-0.4, -0.15, 0.15, 0.4):
        f = cone(f"HiveFang{sx}", r1=0.09, r2=0.0, d=0.7, seg=8, loc=(sx, 3.45, -0.05), rot=(math.pi / 2.3, 0, 0))
        assign(f, fang_m); parent_keep(f, root)

    # Surface vents (outside the hull)
    for sx in (-1, 1):
        for i, yo in enumerate((-1.6, -0.4, 0.8, 1.8)):
            v = ico(f"HiveVent{sx}_{i}", r=0.18, subdiv=2, loc=(sx * 1.40, yo, 0.2), scale=(0.45, 1.15, 0.55))
            assign(v, vein); parent_keep(v, root)

    # Dorsal spines
    for i, yo in enumerate((-1.4, -0.4, 0.6, 1.5)):
        sp = cone(f"HiveDorsal{i}", r1=0.16, r2=0.02, d=0.7 + i * 0.08, seg=8,
                  loc=(0, yo, 1.15), rot=(0.25, 0, 0))
        hard(sp, 0.02, 2); assign(sp, plate_m); parent_keep(sp, root)

    # Landing spines / legs
    for i, (sx, yo, stretch) in enumerate([
        (-1.4, -1.6, 1.5), (1.4, -1.6, 1.5), (-1.7, 0.1, 1.3), (1.7, 0.1, 1.3),
        (-1.2, 1.8, 1.0), (1.2, 1.8, 1.0),
    ]):
        sp = curve_tube(f"HiveLeg{i}", [
            ((sx * 0.5, yo, 0.0), 1.3), ((sx * 1.0, yo + 0.15, -0.5), 0.9), ((sx * stretch, yo + 0.25, -1.35), 0.45),
        ], radius=0.13, res=6, bev_res=3)
        m = to_mesh(sp); shade_auto(m, 40); assign(m, chitin); parent_keep(m, root)

    for i, (x, y, z) in enumerate([(-1.6, -2.2, 0.7), (1.7, -1.0, 0.95), (-0.9, 1.5, 0.9)]):
        p = cube(f"HiveDebris{i}", size=0.7, loc=(x, y, z), rot=(0.4 * i, 0.3, 0.5 * i), scale=(1.2, 0.16, 0.8))
        hard(p, 0.03, 2); assign(p, plate_m); parent_keep(p, root)

    # Maw originally at +Y; rotate 180 so it faces -Y (down the path), then tilt nose down.
    root.rotation_euler = Euler((math.radians(18), 0, math.radians(180)))
    return root
def make_base():
    cream = princ_mat("BaseCream", (0.95, 0.88, 0.72), rough=0.28, metal=0.04, coat=0.4, coat_rough=0.16)
    metal = princ_mat("BaseMetal", (0.18, 0.20, 0.24), rough=0.32, metal=0.72)
    gold = princ_mat("BaseGold", (0.92, 0.68, 0.22), rough=0.22, metal=0.65, emit=(1.0, 0.75, 0.2), emit_str=1.6)
    glass = princ_mat("BaseGlass", (0.45, 0.85, 1.0, 0.55), rough=0.06, coat=0.55, alpha=0.5, emit=(0.45, 0.85, 1.0), emit_str=2.5)
    warm = princ_mat("BaseWarm", (1.0, 0.78, 0.4), rough=0.18, emit=(1.0, 0.72, 0.28), emit_str=8)
    root = bpy.data.objects.new("ColonyBase", None)
    bpy.context.collection.objects.link(root)

    plat = cyl("BasePlat", r=2.5, d=0.24, seg=32, loc=(0, 0, 0.12))
    hard(plat, 0.03, 3); assign(plat, metal); parent_keep(plat, root)
    ring = torus("BaseRing", major=2.25, minor=0.08, maj_seg=40, min_seg=12, loc=(0, 0, 0.26))
    shade_auto(ring, 30); assign(ring, gold); parent_keep(ring, root)

    # Dome
    dome = ico("BaseDome", r=1.55, subdiv=3, loc=(0, 0, 0.55), scale=(1.0, 1.0, 0.78))
    add_subsurf(dome, 1); apply_mods(dome); shade_auto(dome, 40); assign(dome, cream); parent_keep(dome, root)

    # Window bands sitting ON the dome surface.
    # Dome is an ellipsoid r=1.55, z-scale 0.78, centered at z=0.55.
    # At height z, local z from center is (z-0.55), radius_xy = 1.55 * sqrt(1 - ((z-0.55)/(1.55*0.78))**2)
    for i, z in enumerate((0.95, 1.35)):
        lz = z - 0.55
        rz = 1.55 * 0.78
        inside = 1 - (lz / rz) ** 2
        if inside < 0.05:
            continue
        rad = 1.55 * math.sqrt(inside) + 0.02
        w = torus(f"BaseWindow{i}", major=rad, minor=0.07, maj_seg=32, min_seg=10, loc=(0, 0, z))
        shade_auto(w, 30); assign(w, warm); parent_keep(w, root)

    spire = cyl("BaseSpire", r=0.13, d=1.15, seg=16, loc=(0, 0, 2.05))
    hard(spire, 0.02, 2); assign(spire, metal); parent_keep(spire, root)
    dish = cone("BaseDish", r1=0.62, r2=0.08, d=0.16, seg=24, loc=(0, 0, 2.58), rot=(math.radians(16), 0, 0))
    hard(dish, 0.02, 2); assign(dish, metal); parent_keep(dish, root)
    tip = uvsphere("BaseTip", r=0.09, seg=16, rings=10, loc=(0, 0, 2.74))
    assign(tip, warm); parent_keep(tip, root)

    for i in range(4):
        a = i * math.pi / 2 + math.pi / 4
        x, y = math.cos(a) * 1.95, math.sin(a) * 1.95
        p = cube(f"BasePylon{i}", size=0.32, loc=(x, y, 0.58), rot=(0, 0, a), scale=(0.7, 0.7, 3.1))
        hard(p, 0.03, 3); assign(p, cream); parent_keep(p, root)
        cap = cyl(f"BasePylonCap{i}", r=0.13, d=0.08, seg=10, loc=(x, y, 1.12))
        assign(cap, gold); parent_keep(cap, root)
        light = uvsphere(f"BasePylonLight{i}", r=0.08, seg=12, rings=8, loc=(x, y, 1.22))
        assign(light, warm); parent_keep(light, root)

    sg = princ_mat("BaseShieldGlow", (0.3, 0.9, 1.0), rough=0.1, emit=(0.3, 0.9, 1.0), emit_str=6)
    for i in range(6):
        a = i * math.pi / 3
        x, y = math.cos(a) * 2.25, math.sin(a) * 2.25
        s = cone(f"BaseShield{i}", r1=0.13, r2=0.05, d=0.24, seg=8, loc=(x, y, 0.38))
        assign(s, metal); parent_keep(s, root)
        g = uvsphere(f"BaseShieldG{i}", r=0.05, seg=10, rings=8, loc=(x, y, 0.52))
        assign(g, sg); parent_keep(g, root)

    # Hangar door on the FRONT (-Y) so the game camera (from the south) sees it
    # Dome surface at z=0.7, y negative: radius ~1.5
    frame = cube("BaseDoorFrame", size=0.7, loc=(0, -1.48, 0.72), scale=(1.35, 0.22, 1.5))
    hard(frame, 0.03, 3); assign(frame, metal); parent_keep(frame, root)
    door = cube("BaseDoor", size=0.6, loc=(0, -1.58, 0.72), scale=(1.15, 0.16, 1.3))
    hard(door, 0.03, 3); assign(door, glass); parent_keep(door, root)
    # Over-door light bar
    bar = cube("BaseDoorBar", size=0.12, loc=(0, -1.62, 1.18), scale=(4.0, 0.3, 0.35))
    assign(bar, warm); parent_keep(bar, root)
    return root
def make_rock(name, loc, rot, scale, mat):
    r = ico(name, r=1.0, subdiv=2, loc=loc, rot=rot, scale=scale)
    mesh = r.data
    rng = (hash(name) & 0xFFFF) / 65535.0
    for i, v in enumerate(mesh.vertices):
        k = 0.08 * math.sin(i * 1.7 + rng * 6)
        n = v.co.normalized()
        v.co += n * k
    add_bevel(r, 0.06, 2, 40)
    apply_mods(r); shade_auto(r, 28); assign(r, mat)
    return r

def make_crystal(name, loc, rot, h, r, mat, glow):
    c = cone(name, r1=r, r2=r * 0.08, d=h, seg=6, loc=loc, rot=rot)
    c.location.z = loc[2] + h * 0.5
    hard(c, 0.015, 2, 40); assign(c, mat)
    tip = cone(name + "_Tip", r1=r * 0.18, r2=0.0, d=h * 0.25, seg=6,
               loc=(loc[0], loc[1], loc[2] + h * 0.88), rot=rot)
    assign(tip, glow)
    return [c, tip]

def make_arena():
    root = bpy.data.objects.new("Arena", None)
    bpy.context.collection.objects.link(root)
    ground_m = tex_mat("Ground", TEX / "ground_albedo.png", rough=0.78, metal=0.02,
                       rough_path=TEX / "ground_rough.png", scale=6.0)
    path_m = tex_mat("Path", TEX / "path_albedo.png", rough=0.45, metal=0.35, scale=4.0)
    edge_m = princ_mat("PathEdge", (0.3, 0.85, 1.0), rough=0.2, emit=(0.3, 0.8, 1.0), emit_str=3.5)
    pad_m = princ_mat("PadMetal", (0.16, 0.20, 0.26), rough=0.3, metal=0.65, coat=0.2)
    pad_ring = princ_mat("PadRing", (0.35, 0.85, 1.0), rough=0.15, emit=(0.3, 0.85, 1.0), emit_str=4)
    rock_m = princ_mat("Rock", (0.16, 0.17, 0.19), rough=0.72, metal=0.04)
    rock_m2 = princ_mat("Rock2", (0.14, 0.16, 0.18), rough=0.68, metal=0.05)
    xtal = princ_mat("Crystal", (0.15, 0.4, 0.45), rough=0.12, metal=0.05, coat=0.5, emit=(0.1, 0.45, 0.5), emit_str=1.2)
    xtal_g = princ_mat("CrystalGlow", (0.3, 0.95, 1.0), rough=0.08, emit=(0.3, 0.95, 1.0), emit_str=6)

    bpy.ops.mesh.primitive_grid_add(x_subdivisions=48, y_subdivisions=56, size=1, location=(0, 0, 0))
    ground = bpy.context.object
    ground.name = "Ground"
    ground.scale = (22, 28, 1)
    apply_transforms(ground)
    for v in ground.data.vertices:
        x, y, z = v.co
        dish = -0.08 * ((x / 22) ** 2 + (y / 28) ** 2)
        dx, dy = x - 0.0, y - 17.5
        cr = math.exp(-(dx * dx + dy * dy) / 18.0)
        crater = -0.55 * cr
        berm = 0.28 * math.exp(-(math.sqrt(dx * dx + dy * dy) - 4.2) ** 2 / 1.8)
        v.co.z = dish + crater + berm
    active(ground)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.001)
    bpy.ops.object.mode_set(mode="OBJECT")
    uv = ground.data.uv_layers.active
    for loop in uv.data:
        loop.uv *= 4.0
    shade_auto(ground, 50); assign(ground, ground_m); parent_keep(ground, root)

    pts = [Vector((x, y, z)) for x, y, z in WAYPOINTS]
    data = bpy.data.curves.new("PathCurve", "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 12
    prof = bpy.data.curves.new("PathProf", "CURVE")
    prof.dimensions = "2D"
    ps = prof.splines.new("POLY")
    w, h = 1.1, 0.07
    coords = [(-w, 0, 0), (-w, h, 0), (w, h, 0), (w, 0, 0), (-w, 0, 0)]
    ps.points.add(len(coords) - 1)
    for i, c in enumerate(coords):
        ps.points[i].co = (c[0], c[1], c[2], 1)
    ps.use_cyclic_u = True
    prof_obj = bpy.data.objects.new("PathProf", prof)
    bpy.context.collection.objects.link(prof_obj)
    spl = data.splines.new("BEZIER")
    spl.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = spl.bezier_points[i]
        bp.co = p
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    data.bevel_mode = "OBJECT"
    data.bevel_object = prof_obj
    data.use_fill_caps = True
    path_obj = bpy.data.objects.new("Path", data)
    bpy.context.collection.objects.link(path_obj)
    path_mesh = to_mesh(path_obj)
    bpy.data.objects.remove(prof_obj, do_unlink=True)
    active(path_mesh)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.uv.cylinder_project(correct_aspect=True)
    except Exception:
        bpy.ops.uv.smart_project(island_margin=0.01)
    bpy.ops.object.mode_set(mode="OBJECT")
    shade_auto(path_mesh, 40); assign(path_mesh, path_m); parent_keep(path_mesh, root)

    def edge_curve(name, offset):
        ed = bpy.data.curves.new(name, "CURVE")
        ed.dimensions = "3D"
        ed.resolution_u = 10
        ed.bevel_depth = 0.035
        ed.bevel_resolution = 3
        ed.use_fill_caps = True
        es = ed.splines.new("BEZIER")
        es.bezier_points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            tang = (pts[i + 1] - p).normalized() if i < len(pts) - 1 else (p - pts[i - 1]).normalized()
            side = Vector((-tang.y, tang.x, 0)).normalized() * offset
            bp = es.bezier_points[i]
            bp.co = p + side + Vector((0, 0, 0.02))
            bp.handle_left_type = "AUTO"
            bp.handle_right_type = "AUTO"
        obj = bpy.data.objects.new(name, ed)
        bpy.context.collection.objects.link(obj)
        m = to_mesh(obj); shade_auto(m, 40); assign(m, edge_m); parent_keep(m, root)
        return m
    edge_curve("PathEdgeL", 1.12)
    edge_curve("PathEdgeR", -1.12)

    for i, p in enumerate(WAYPOINTS):
        empty = bpy.data.objects.new(f"Waypoint_{i:02d}", None)
        empty.empty_display_size = 0.3
        empty.empty_display_type = "SPHERE"
        empty.location = p
        bpy.context.collection.objects.link(empty)
        parent_keep(empty, root)

    for i, (x, y) in enumerate(PADS):
        z = 0.08
        pad = cyl(f"Pad_{i:02d}", r=0.95, d=0.14, seg=20, loc=(x, y, z))
        hard(pad, 0.03, 3); assign(pad, pad_m); parent_keep(pad, root)
        ring = torus(f"PadRing_{i:02d}", major=0.88, minor=0.035, maj_seg=28, min_seg=10, loc=(x, y, z + 0.08))
        shade_auto(ring, 30); assign(ring, pad_ring); parent_keep(ring, root)
        dia = cube(f"PadMark_{i:02d}", size=0.22, loc=(x, y, z + 0.09), rot=(0, 0, math.pi / 4), scale=(1, 1, 0.12))
        assign(dia, pad_ring); parent_keep(dia, root)

    rock_spots = [
        ((-8.5, 14.0, 0.15), (0.2, 0.1, 0.8), (1.6, 1.2, 1.0)),
        ((8.8, 13.5, 0.1), (0.4, -0.2, 0.3), (1.3, 1.8, 0.9)),
        ((-10.2, 8.0, 0.1), (0.1, 0.3, 1.2), (2.0, 1.4, 1.2)),
        ((10.5, 8.5, 0.15), (0.5, 0.0, 0.4), (1.5, 1.1, 1.4)),
        ((-10.0, -6.5, 0.1), (0.2, 0.4, 0.7), (1.8, 1.5, 1.1)),
        ((10.2, -7.0, 0.12), (0.0, 0.2, 1.5), (1.4, 1.9, 1.0)),
        ((-7.5, -14.5, 0.1), (0.3, 0.1, 0.5), (1.7, 1.2, 0.9)),
        ((7.8, -14.8, 0.1), (0.1, 0.3, 0.9), (1.3, 1.6, 1.1)),
        ((-11.5, 0.5, 0.15), (0.4, 0.2, 0.2), (2.2, 1.3, 1.3)),
        ((11.8, -1.0, 0.1), (0.2, 0.5, 0.6), (1.6, 1.4, 1.2)),
        ((-3.8, 17.2, 0.0), (0.3, 0.1, 0.4), (1.4, 1.0, 0.8)),
        ((4.0, 17.0, 0.05), (0.2, 0.3, 0.8), (1.2, 1.5, 0.7)),
        ((-6.0, 15.5, 0.0), (0.1, 0.4, 0.2), (1.0, 1.2, 0.6)),
        ((6.2, 15.8, 0.0), (0.5, 0.1, 0.5), (1.1, 0.9, 0.7)),
    ]
    for i, (loc, rot, sc) in enumerate(rock_spots):
        rk = make_rock(f"Rock_{i}", loc, rot, sc, rock_m if i % 2 == 0 else rock_m2)
        parent_keep(rk, root)

    xtal_spots = [
        ((-9.2, 11.5, 0.0), 1.4, 0.22), ((-8.6, 11.0, 0.0), 0.8, 0.14),
        ((9.6, 10.2, 0.0), 1.6, 0.2), ((9.1, 9.6, 0.0), 0.7, 0.12),
        ((-9.8, -9.0, 0.0), 1.2, 0.18), ((10.0, -11.2, 0.0), 1.5, 0.2),
        ((-4.6, 16.4, 0.0), 0.9, 0.14), ((5.0, 16.6, 0.0), 1.1, 0.16),
        ((-10.5, -2.5, 0.0), 1.0, 0.15),
    ]
    for i, (loc, h, r) in enumerate(xtal_spots):
        for piece in make_crystal(f"Crystal_{i}", loc, (0, 0, i * 0.4), h, r, xtal, xtal_g):
            parent_keep(piece, root)

    debris_m = princ_mat("Debris", (0.25, 0.22, 0.2), rough=0.4, metal=0.65)
    for i, (loc, rot, sc) in enumerate([
        ((-2.2, 14.8, 0.2), (0.6, 0.2, 0.4), (1.2, 0.15, 0.5)),
        ((1.8, 15.2, 0.15), (0.3, 0.8, 0.2), (0.8, 0.12, 0.4)),
        ((0.6, 14.2, 0.12), (1.0, 0.3, 0.7), (0.5, 0.1, 0.3)),
    ]):
        d = cube(f"Debris_{i}", size=1.0, loc=loc, rot=rot, scale=sc)
        hard(d, 0.03, 2); assign(d, debris_m); parent_keep(d, root)
    return root

def place_landmarks(arena, hive, base):
    hive.parent = None
    hive.location = (0.0, 19.2, 1.15)
    base.location = (0.0, -17.4, 0.0)
    parent_keep(hive, arena)
    parent_keep(base, arena)
    spawn = bpy.data.objects.new("Hive_Mouth", None)
    spawn.empty_display_size = 0.5
    spawn.location = WAYPOINTS[0]
    bpy.context.collection.objects.link(spawn)
    parent_keep(spawn, arena)
    core = bpy.data.objects.new("Base_Core", None)
    core.empty_display_size = 0.5
    core.location = (0.0, -17.4, 1.2)
    bpy.context.collection.objects.link(core)
    parent_keep(core, arena)

def write_layout():
    data = {
        "waypoints_blender": [{"x": x, "y": y, "z": z} for (x, y, z) in WAYPOINTS],
        "pads_blender": [{"x": x, "y": y, "z": 0.15} for (x, y) in PADS],
    }
    p = OUT / "layout.json"
    p.write_text(json.dumps(data, indent=2))
    print("layout", p)

def run():
    reset_scene()
    print("=== GRUNT ===")
    grunt = make_grunt()
    export_glb(grunt, OUT / "alien_grunt.glb")
    preview(grunt, "grunt_34", dist=2.4, height=1.3, look_z=0.45)
    preview(grunt, "grunt_front", dist=2.2, height=1.0, look_z=0.4, front=True)

    print("=== TANK ===")
    tank = make_tank()
    export_glb(tank, OUT / "alien_tank.glb")
    preview(tank, "tank_34", dist=3.6, height=1.8, look_z=0.7)
    preview(tank, "tank_front", dist=3.4, height=1.5, look_z=0.7, front=True)

    print("=== BOSS ===")
    boss = make_boss()
    export_glb(boss, OUT / "alien_boss.glb")
    preview(boss, "boss_34", dist=7.0, height=3.2, look_z=1.4)
    preview(boss, "boss_front", dist=6.5, height=2.6, look_z=1.3, front=True)

    print("=== LASER ===")
    laser = make_laser_turret()
    export_glb(laser, OUT / "turret_laser.glb")
    preview(laser, "laser_34", dist=4.2, height=2.2, look_z=0.7)

    print("=== TESLA ===")
    tesla = make_tesla_turret()
    export_glb(tesla, OUT / "turret_tesla.glb")
    preview(tesla, "tesla_34", dist=5.0, height=2.6, look_z=1.0)

    print("=== ROCKET ===")
    rocket = make_rocket_turret()
    export_glb(rocket, OUT / "turret_rocket.glb")
    preview(rocket, "rocket_34", dist=4.4, height=2.2, look_z=0.7)

    print("=== MECH ===")
    mech = make_mech()
    export_glb(mech, OUT / "mech.glb")
    preview(mech, "mech_34", dist=8.0, height=3.6, look_z=1.5)
    preview(mech, "mech_front", dist=7.8, height=2.8, look_z=1.5, front=True)

    print("=== HIVE ===")
    hive = make_hive()
    export_glb(hive, OUT / "hive_ship.glb")
    preview(hive, "hive_34", dist=14, height=5.5, look_z=0.4)

    print("=== BASE ===")
    base = make_base()
    export_glb(base, OUT / "colony_base.glb")
    preview(base, "base_34", dist=9, height=4.0, look_z=1.2)
    preview(base, "base_front", dist=8.5, height=3.2, look_z=1.1, front=True)

    print("=== ARENA ===")
    arena = make_arena()
    place_landmarks(arena, hive, base)
    export_glb(arena, OUT / "arena.glb")
    write_layout()
    blend = Path("/tmp/hive-breach/hive.blend")
    blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    print("DONE")

if __name__ == "__main__":
    run()
