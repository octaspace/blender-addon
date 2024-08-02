import bpy
import sys

save_path = sys.argv[sys.argv.index("-save_path") + 1]

bpy.ops.file.make_paths_absolute()
bpy.ops.wm.save_as_mainfile(filepath=save_path)
bpy.ops.file.pack_all()
bpy.ops.file.unpack_all(method="USE_LOCAL")
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
