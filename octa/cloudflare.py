import threading
from .web_api_base import WebApiBase, FileWithCallback, FileSliceWithCallback
from .web_ui import WebUi
from traceback import format_exc
from dataclasses import dataclass
from multiprocessing.pool import ThreadPool
import os
import math
import time
import mmap


@dataclass
class Upload:
    url: str
    offset: int
    size: int
    index: int


class FileUpload:
    def __init__(self, local_path, job_id, retries=3, thread_count=10, progress_callback=None):
        self.local_path = local_path
        self.job_id = job_id
        self.retries = retries
        self.thread_count = thread_count  # TODO: for the future, does nothing atm
        self.progress_callback = progress_callback
        # TODO: possibly scale with file size
        self.part_size = 25000000  # 25 MB

        self.mapped_file: mmap.mmap = None
        self.thread = None
        self.success = False
        self.reason = ''

        self.uploads: list[Upload] = []
        self.etags: dict[int, str] = {}

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def join(self):
        self.thread.join()

    def _callback_single(self, offset, total_size):
        progress = offset / total_size
        if self.progress_callback:
            self.progress_callback(progress)

    def run_single_upload(self, url):
        ff = FileWithCallback(self.local_path, 'rb', self._callback_single)
        try:
            response = WebApiBase.request_with_retries('PUT', url, headers={
                'Content-Length': ff.size
            }, body=ff, retries=self.retries)
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

    def upload_task(self, upload):
        try:
            # self.set_progress_name(f"Uploading part {upload.index}/{self.upload_count}")
            ul_start = int(time.time() * 1000)
            response = WebApiBase.request_with_retries('PUT', upload.url, headers={
                'Content-Length': upload.size
            }, body=self.mapped_file[upload.offset:upload.offset + upload.size], retries=self.retries)
            ul_end = int(time.time() * 1000)

            self.progress_callback(upload.index / len(self.uploads))
            self.etags[upload.index + 1] = response.headers['ETag']
            print(f"Uploaded part {upload.index} | UL Time {ul_end - ul_start}ms | Size {upload.size / 1000 / 1000:.2f}MB")
        except:
            print(f"Failed to upload part{upload.index}: {format_exc()}")

    def get_upload_data(self, part_count):
        data = WebUi.get_job_input_multipart_upload_info_full(self.job_id, part_count)
        key = data['key']
        bucket = data['bucket']
        upload_id = data['upload_id']
        links = data['links']

        return key, bucket, upload_id, links

    def run_inner(self):
        self.uploads = []
        self.etags = {}

        with open(self.local_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            f.seek(0)

            self.mapped_file = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

            part_count = math.ceil(file_size / self.part_size)
            print(f"part count: {part_count}, file_size: {file_size}, part_size: {self.part_size}")

            key, bucket, upload_id, links = self.get_upload_data(part_count)

            time.sleep(5)  # give cloudflare time to actually be ready for upload

            if part_count > 1:

                for part_index in range(part_count):
                    offset = self.part_size * part_index
                    size = self.part_size
                    if offset + size > file_size:
                        size = file_size - offset
                    upload = Upload(links[part_index], offset, size, part_index)
                    self.uploads.append(upload)

                print(f"uploading with {self.thread_count} threads")
                pool = ThreadPool(self.thread_count)
                pool.map(self.upload_task, self.uploads)
                pool.close()
            else:
                url = WebUi.get_multipart_signed_url(key, bucket, upload_id, 1)
                etag = self.run_single_upload(url)
                if etag is not None:
                    self.etags[1] = etag

            if part_count == len(self.etags):
                WebUi.complete_job_input_multipart_upload(key, bucket, upload_id, self.etags)
                self.success = True
            else:
                WebUi.abort_job_input_multipart_upload(key, bucket, upload_id)
                self.reason = f"expected etag count to be {part_count} but it was {len(self.etags)}"
                self.success = False
