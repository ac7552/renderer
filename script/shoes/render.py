# Renders the meshes in the current scene from a few angles into one sheet (Cycles, CPU).
import bpy, math, mathutils, sys
def render_sheet(out, views=((40,25),(90,8),(0,4),(180,12)), size=420, samples=24):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'; sc.cycles.device='CPU'; sc.cycles.samples=samples
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.film_transparent = False
    world = bpy.data.worlds.new("w") if not sc.world else sc.world; sc.world = world
    world.use_nodes = True; world.node_tree.nodes["Background"].inputs[0].default_value=(0.9,0.9,0.88,1); world.node_tree.nodes["Background"].inputs[1].default_value=0.6
    objs=[o for o in sc.objects if o.type=='MESH']
    pts=[o.matrix_world@mathutils.Vector(c) for o in objs for c in o.bound_box]
    mn=mathutils.Vector([min(p[i] for p in pts) for i in range(3)]); mx=mathutils.Vector([max(p[i] for p in pts) for i in range(3)])
    ctr=(mn+mx)/2; rad=(mx-mn).length*0.5
    if "sun" not in bpy.data.objects:
        l=bpy.data.lights.new("sun","SUN"); l.energy=3.5; so=bpy.data.objects.new("sun",l); sc.collection.objects.link(so); so.rotation_euler=(math.radians(40),math.radians(15),math.radians(30))
    cam=bpy.data.cameras.new("c"); cam.type='ORTHO'; cam.ortho_scale=rad*2; co=bpy.data.objects.new("c",cam); sc.collection.objects.link(co); sc.camera=co
    import os
    files=[]
    for k,(turn,pitch) in enumerate(views):
        t=math.radians(turn); p=math.radians(pitch)
        # turn 0: from the outer side (-y here? scene axes: length along x), 90: from the toe.
        d=mathutils.Vector((math.sin(t)*math.cos(p), -math.cos(t)*math.cos(p), math.sin(p)))
        co.location=ctr+d*rad*3
        co.rotation_euler=(-d).to_track_quat('-Z','Y').to_euler()
        f=f"/tmp/_r{k}.png"; sc.render.filepath=f; bpy.ops.render.render(write_still=True); files.append(f)
    bpy.data.objects.remove(co)
    from PIL import Image
    ims=[Image.open(f) for f in files]; sheet=Image.new("RGB",(size*len(ims),size),"white")
    for i,im in enumerate(ims): sheet.paste(im.convert("RGB"),(i*size,0))
    sheet.save(out)
