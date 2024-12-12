bl_info = {
    "name": "OctaSpace Blender Addon",
    "author": "OctaSpace",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "Properties > Render > Exporter",
    "description": "Export To OctaSpace Render",
    "warning": "",
    "wiki_url": "",
    "category": "Import-Export",
}

import bpy.props
import bpy.utils
import bpy
import os
import bpy.utils.previews

from bpy.types import Operator
from bpy.utils import register_class, unregister_class, previews

from .octa.icon_manager import IconManager

from .octa.transfer_manager import OCTA_OT_TransferManager, OCTA_OT_OpenTransferManager

from .octa.zip_addons import ZIPAddonsOperator


from .octa.octa_properties import OctaProperties, OctaNodeProperties
from .octa.install_dependencies import InstallDependenciesOperator
from .octa.octa_panel import (
    OctaPanel,
    SelectNodeOperator,
    ToggleNodeMuteOperator,
    ToggleSceneNodesOperator,
    ToggleVisibilityOperator,
    ToggleAddonSelectionOperator,
)

from .octa.submit_job_operator import SubmitJobOperator
from .octa.download_job_operator import DownloadJobOperator

from .octa.verify_key import VerifyKeyOperator, LogOutOperator

from .octa.util import section

icons_dict = None


class Octa_Addon_Preferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    debug_options: bpy.props.BoolProperty(name="Debug Options", default=False)

    expand_debug_options: bpy.props.BoolProperty(
        name="Expand Debug Options", default=False
    )

    octa_farm_config: bpy.props.StringProperty(
        name="Octa Farm Config",
        description="The configuration token retrieved from your render farm",
        default="",
    )

    logged_in: bpy.props.BoolProperty(name="Logged In", default=False)

    def draw(self, context):
        layout = self.layout

        row = layout.row()

        if not self.logged_in:
            row.label(text="Octa Farm Config Key:")

            row = layout.row(align=True)
            col = row.column()
            col.scale_x = 4
            col.prop(self, "octa_farm_config", text="")

            # Make the button slimmer
            col = row.column()
            col.scale_x = 2
            col.operator(
                VerifyKeyOperator.bl_idname, icon="KEYINGSET", text="Verify Key"
            )
        else:
            row.operator(LogOutOperator.bl_idname, icon="KEY_DEHLT", text="Logout")

        if not InstallDependenciesOperator.get_installed_packages_initialized():
            InstallDependenciesOperator.set_installed_packages()

        _, missing_packages = InstallDependenciesOperator.check_dependencies_installed()

        is_installing = InstallDependenciesOperator.get_running()

        if is_installing:
            row = layout.row()
            row.label(icon=InstallDependenciesOperator.get_progress_icon(), text="")
            row.progress(
                text=InstallDependenciesOperator.get_progress_name(),
                factor=InstallDependenciesOperator.get_progress(),
            )

        if len(missing_packages) > 0:
            row = layout.row()
            if not is_installing:
                row.label(text="Missing dependencies", icon="ERROR")

            row = layout.row()
            install_op = row.operator(
                InstallDependenciesOperator.bl_idname,
                icon="IMPORT",
                text="Install Dependencies",
            )
            install_op.uninstall = False
            if not is_installing:
                row.enabled = True
        else:
            row = layout.row()
            if not is_installing:
                row.label(text="All dependencies are installed", icon="SOLO_ON")

            row = layout.row()
            uninstall_op = row.operator(
                InstallDependenciesOperator.bl_idname,
                icon="TRASH",
                text="Uninstall Dependencies",
            )
            uninstall_op.uninstall = True

            if not is_installing:
                row.enabled = True

        row = layout.row()

        debug_section = section(row, self, "expand_debug_options", "Advanced Options")

        if debug_section:
            box = debug_section.box()
            box.label(text="Developer Options")
            row = box.row()
            row.prop(self, "debug_options", text="Debug Options")


classes = (
    OctaProperties,
    SubmitJobOperator,
    OctaPanel,
    SelectNodeOperator,
    ToggleSceneNodesOperator,
    DownloadJobOperator,
    Octa_Addon_Preferences,
    OctaNodeProperties,
    ToggleVisibilityOperator,
    ToggleNodeMuteOperator,
    InstallDependenciesOperator,
    OCTA_OT_TransferManager,
    OCTA_OT_OpenTransferManager,
    ZIPAddonsOperator,
    ToggleAddonSelectionOperator,
    VerifyKeyOperator,
    LogOutOperator,
)


def register():
    IconManager()
    for cls in classes:
        register_class(cls)
    bpy.types.Scene.octa_properties = bpy.props.PointerProperty(type=OctaProperties)
    bpy.types.Scene.show_expanded = bpy.props.BoolProperty(
        name="Show Expanded", default=False
    )
    bpy.types.Node.octa_node_properties = bpy.props.PointerProperty(
        type=OctaNodeProperties
    )


def unregister():
    IconManager.unload_icons()
    for cls in classes:
        unregister_class(cls)
    del bpy.types.Scene.octa_properties
    del bpy.types.Scene.show_expanded


if __name__ == "__main__":
    register()
