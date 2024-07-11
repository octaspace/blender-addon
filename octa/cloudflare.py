import threading
from .web_api_base import WebApiBase, FileWithCallback, FileSliceWithCallback
from .web_ui import WebUi
from traceback import format_exc
import os
import math
import time


class FileUpload:
    def __init__(self, local_path, job_id, retries=3, thread_count=10, progress_callback=None):
        self.local_path = local_path
        self.job_id = job_id
        self.retries = retries
        self.thread_count = thread_count  # TODO: for the future, does nothing atm
        # TODO: possibly scale with file size
        self.part_size = 25000000  # 25 MB

        self.progress = 0
        self.finished = False
        self.progress_callback = progress_callback

        self.thread = None
        self.success = False
        self.reason = ''

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def join(self):
        self.thread.join()

    def _callback_single(self, offset, total_size):
        progress = offset / total_size
        self.progress = progress
        if self.progress_callback:
            self.progress_callback(progress)

    def run_single_upload(self, url):
        ff = FileWithCallback(self.local_path, 'rb', self._callback_single)
        try:
            response = WebApiBase.request_with_retries('PUT', url, headers={
                'Content-Length': ff.size
            }, data=ff, retries=self.retries)
            self.success = True
            return response.headers['ETag']
        except:
            return None
        finally:
            ff.close()

    def run(self):
        try:
            self.run_inner()
        except:
            self.success = False
            self.reason = format_exc()

    def run_inner(self):
        with open(self.local_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()

        part_count = math.ceil(file_size / self.part_size)
        print(f"part count: {part_count}, file_size: {file_size}, part_size: {self.part_size}")
        etags = {}

        data = WebUi.get_job_input_multipart_upload_info_full(self.job_id, part_count)
        key = data['key']
        bucket = data['bucket']
        upload_id = data['upload_id']
        links = data['links']

        if part_count > 1:
            with open(self.local_path, 'rb') as f:
                part_number = 1
                running = True
                while running:
                    offset = f.tell()
                    part_size = self.part_size
                    if offset + self.part_size > file_size:
                        part_size = file_size - offset
                        running = False

                    print(f"part {part_number} with offset {offset} and size {part_size}")

                    def _callback(fake_offset, fake_size):
                        progress = (offset + fake_offset) / file_size
                        self.progress = progress
                        if self.progress_callback:
                            self.progress_callback(progress)

                    file_slice = FileSliceWithCallback(f, offset, part_size, _callback)
                    url = links[part_number - 1]  # WebUi.get_multipart_signed_url(key, bucket, upload_id, part_number)
                    response = WebApiBase.request_with_retries('PUT', url, headers={
                        'Content-Length': part_size
                    }, data=file_slice, retries=self.retries)

                    etags[part_number] = response.headers['ETag']

                    part_number += 1
        else:
            url = WebUi.get_multipart_signed_url(key, bucket, upload_id, 1)
            etag = self.run_single_upload(url)
            if etag is not None:
                etags[1] = etag

        if part_count == len(etags):
            WebUi.complete_job_input_multipart_upload(key, bucket, upload_id, etags)
            self.success = True
        else:
            WebUi.abort_job_input_multipart_upload(key, bucket, upload_id)
            self.reason = f"expected etag count to be {part_count} but it was {len(etags)}"
            self.success = False
