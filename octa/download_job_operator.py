import bpy
from dataclasses import dataclass
from traceback import format_exc
from .octa_properties import DownloadJobProperties
from .util import unpack_octa_farm_config
from .transfer_manager import create_download, ensure_running
from typing import Optional


@dataclass
class Download:
    url: str
    local_path: str
    index: int


class DownloadJobOperator(bpy.types.Operator):
    bl_idname = "exporter.download_job"
    bl_label = "Download Job"
    bl_description = "Download Job"
    instance = None

    def __init__(self):
        super().__init__()
        DownloadJobOperator.instance = self

    def validate_properties(self, context) -> Optional[DownloadJobProperties]:
        properties = DownloadJobProperties()
        fail_validation = False

        props = context.scene.octa_properties
        job_id = props.dl_job_id
        if len(job_id) <= 0:
            self.report({"ERROR"}, "Job id is not set")
            fail_validation = True

        output_path = props.dl_output_path
        if len(output_path) <= 0:
            self.report({"ERROR"}, "Output path is not set")
            fail_validation = True

        farm_config = props.octa_farm_config
        #if len(farm_config) <= 0:
        #    self.report({"ERROR"}, "Farm config is not set")
        #    fail_validation = True
        # TODO: confirm its actually valid or something

        properties.job_id = job_id
        properties.output_path = output_path
        properties.octa_farm_config = farm_config

        if fail_validation:
            return None

        return properties

    def execute(self, context):
        try:
            properties: DownloadJobProperties = self.validate_properties(context)
        except:
            print(format_exc())
            return {"CANCELLED"}
        if properties is None:
            return {"CANCELLED"}
        job_id = properties.job_id
        output_path = properties.output_path
        user_data = unpack_octa_farm_config(properties.octa_farm_config)

        ensure_running()
        download_id = create_download(output_path, job_id, user_data)

        # TODO: enable this once frontend caught up
        # webbrowser.open(f"{user_data['farm_host']}/transfers/{download_id}")

        return {'FINISHED'}
