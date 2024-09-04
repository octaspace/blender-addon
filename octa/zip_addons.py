import os
import zipfile
from pathlib import Path

import bpy
import addon_utils

DEFAULT_ADDONS = [
    "io_anim_bvh",
    "bl_pkg",
    "copy_global_transform",
    "cycles",
    "io_scene_fbx",
    "io_scene_gltf2",
    "hydra_storm",
    "ui_translate",
    "node_wrangler",
    "pose_library",
    "rigify",
    "io_curve_svg",
    "io_mesh_uv_layout",
    "viewport_vr_preview",
]


class ZIPAddonsOperator(bpy.types.Operator):
    """Zip all enabled addon directories"""

    bl_idname = "wm.zip_addons"
    bl_label = "Zip Enabled Addons"

    zip_path: bpy.props.StringProperty(
        name="Target Path",
        default="//bat.zip/addons",
        subtype="FILE_PATH",
        description="Path to save the zip file",
    )

    installed_addons = []

    addons_to_send: bpy.props.StringProperty(
        name="Addons to Send",
        default="",
        description="Comma separated list of addons to send",
    )

    @classmethod
    def set_installed_addons(cls):
        cls.installed_addons = [
            mod
            for mod in addon_utils.modules()
            if addon_utils.check(mod.__name__)[1] and mod.__name__ not in DEFAULT_ADDONS
        ]

    def execute(self, context):
        addons_to_send = self.addons_to_send.split(",")
        print(addons_to_send)
        addons_to_send = [
            mod for mod in self.installed_addons if mod.__name__ in addons_to_send
        ]

        with zipfile.ZipFile(
            bpy.path.abspath(self.zip_path), "w", zipfile.ZIP_DEFLATED
        ) as zipf:
            for addon in addons_to_send:
                addon_path = Path(addon.__file__).parent
                addon_name = addon.__name__

                for root, _, files in os.walk(addon_path):
                    archive_root = os.path.relpath(root, addon_path)
                    for file in files:
                        file_path = os.path.join(root, file)
                        zipf.write(
                            file_path, os.path.join(addon_name, archive_root, file)
                        )

        self.report(
            {"INFO"},
            f"Addons zipped successfully at: {bpy.path.abspath(self.zip_path)}",
        )

        enabled_addons = [
            mod.bl_info["name"]
            for mod in addon_utils.modules()
            if addon_utils.check(mod.__name__)[1]
        ]
        print(enabled_addons)
        return {"FINISHED"}
