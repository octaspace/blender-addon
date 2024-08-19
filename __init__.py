# blender addon info
bl_info = {
    "name": "OctaSpace Blender Addon",
    "author": "OctaSpace",
    "version": (1, 0),
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


from .octa.octa_properties import OctaProperties, OctaNodeProperties
from .octa.octa_panel import (
    OctaPanel,
    SelectNodeOperator,
    ToggleSceneNodesOperator,
    ToggleVisibilityOperator,
)

from .octa.submit_job_operator import SubmitJobOperator
from .octa.download_job_operator import DownloadJobOperator

icons_dict = None


class Octa_Addon_Preferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    def draw(self, context):
        layout = self.layout
        layout.operator(
            "preferences.addon_refresh", text="Update Addon", icon="FILE_REFRESH"
        )


# register
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
