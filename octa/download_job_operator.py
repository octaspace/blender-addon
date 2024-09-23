import bpy
import os
import requests
from multiprocessing.pool import ThreadPool
from dataclasses import dataclass
from traceback import format_exc
from .octa_properties import DownloadJobProperties
from .modal_operator import ModalOperator
from .util import get_all_render_passes, IMAGE_TYPE_TO_EXTENSION, unpack_octa_farm_config
from .web_api_base import WebApiBase
from .transfer_manager import create_download
import time
import threading


@dataclass
class Download:
    url: str
    local_path: str
    index: int


class DownloadJobOperator(ModalOperator):
    bl_idname = "exporter.download_job"
    bl_label = "Download Job"
    bl_description = "Download Job"
    instance = None

    def __init__(self):
        super().__init__()
        DownloadJobOperator.instance = self
        self.download_count = 0
        self.completed_downloads = 0
        self.lock = threading.Lock()

    def validate_properties(self, context):
        properties = DownloadJobProperties()
        fail_validation = False

        props = context.scene.octa_properties
        job_id = props.dl_job_id
        if len(job_id) <= 0:
            self.report({"ERROR"}, "Job id is not set")
            fail_validation = True

        properties.job_id = str(job_id)
        properties.output_path = props.dl_output_path
        properties.octa_farm_config = props.octa_farm_config

        if fail_validation:
            return None

        return properties

    def run(self, properties: DownloadJobProperties):
        job_id = properties.job_id
        output_path = properties.output_path
        user_data = unpack_octa_farm_config(properties.octa_farm_config)

        download_id = create_download(output_path, job_id, user_data)

        # TODO: enable this once frontend caught up
        # webbrowser.open(f"{user_data['farm_host']}/transfers/{download_id}")
        self.set_progress_name("Download Submitted")
        self.set_progress(1.0)
