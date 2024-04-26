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

from .octa.octa_properties import OctaProperties
from .octa.octa_panel import OctaPanel, SelectNodeOperator

from .octa.submit_job_operator import SubmitJobOperator
from .octa.download_job_operator import DownloadJobOperator

class Octa_Addon_Preferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    def draw(self, context):
        layout = self.layout     
        layout.operator("preferences.addon_refresh", text="Update Addon", icon="FILE_REFRESH")

# register
classes = (
    OctaProperties,
    SubmitJobOperator,
    OctaPanel,
    SelectNodeOperator,
    DownloadJobOperator,
    Octa_Addon_Preferences
)


def register():
    for cls in classes:
        print("registerting " + str(cls))
        bpy.utils.register_class(cls)
    bpy.types.Scene.octa_properties = bpy.props.PointerProperty(type=OctaProperties)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.octa_properties


if __name__ == "__main__":
    register()
