import bpy
from .transfer_manager import verify_key
from .util import get_preferences, unpack_octa_farm_config


class VerifyKeyOperator(bpy.types.Operator):
    bl_idname = "exporter.verify_key"
    bl_label = "Verify Key"
    bl_description = "Verify Key"

    def execute(self, context):
        prefs = get_preferences()
        farm_config = prefs.octa_farm_config
        if len(farm_config) <= 0:
            self.report({"ERROR"}, "Farm config is not set")
            return {"CANCELLED"}

        user_data = unpack_octa_farm_config(farm_config)
        if not verify_key(user_data):
            self.report({"ERROR"}, "Invalid key")
            return {"CANCELLED"}
        else:
            self.report({"INFO"}, "Key verified")
            prefs.logged_in = True
            return {"FINISHED"}
