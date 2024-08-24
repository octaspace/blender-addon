import time, os
import httpx
import asyncio
import aiofiles
from octa.util import get_file_md5_async, spawn_and_wait, worker
from octa.web_ui import WebUi
import uuid
import math


class Sessions:
    uploads = {}
    downloads = {}

    @classmethod
    def toJSON(cls):
        return {
            "uploads": [upload.toJSON() for upload in cls.uploads.values()],
            "downloads": [download.toJSON() for download in cls.uploads.values()],
        }


class File:
    def __init__(self, path, chunk_size=25000000) -> None:
        self.path = os.path.abspath(path)
        self.size = os.path.getsize(path)
        self.signed_urls = []
        self.progress = 0
        self.key = None
        self.bucket = None
        self.upload_id = None
        self.hash = None
        self.chunk_count = self.calculate_chunk_count(chunk_size)

    async def calculate_hash(self):
        self.hash = await get_file_md5_async(self.path)

    def calculate_chunk_count(self, chunk_size):
        return math.ceil(self.size / chunk_size)

    def toJSON(self):
        return {"path": self.path, "size": self.size, "hash": self.hash, "chunk_count": self.chunk_count, "progress": self.progress, "signed_urls": self.signed_urls}


class Upload:
    def __init__(self, directory) -> None:
        self.job_id = uuid.uuid4()
        print(self.job_id)
        self.session_id = int(time.time())
        self.chunk_size = 25000000
        self.progress = 0
        self.input_path = directory
        self.files = {}
        self.file_count = 0
        self.file_size = 0
        self.root_path = None
        self.client = httpx.AsyncClient(timeout=3600)
        self.workers = {}
        self.errors = {}
        asyncio.run(self.get_files())

    async def run(self):
        await spawn_and_wait(self.workers, self.upload_worker, "upload", self.files.keys(), workers=4)
        await self.client.aclose()

    def toJSON(self):
        return {
            "session_id": self.session_id,
            "progress": self.progress,
            "input_path": self.input_path,
            "files": self.files,
            "file_count": self.file_count,
            "file_size": self.file_size,
            "root_path": self.root_path,
        }

    @worker("upload")
    async def upload_worker(self, iteration):
        print("iteration:", iteration)
        file_path = list(self.files.keys())[iteration]
        signed_urls = self.files[file_path].signed_urls
        file_chunks = self.read_chunks(file_path)
        idx = 0
        total_size = 0
        etags = {}
        async for chunk in file_chunks:
            if idx < len(signed_urls):
                url = signed_urls[idx]
                print(url)
                print("idx:", idx)
                print(file_path)
                response = await self.client.put(url, content=chunk, headers={"Content-Length": str(len(chunk))})
                etags[idx + 1] = response.headers.get("ETag")
                total_size += len(chunk)
                print("total_size:", total_size)
                idx += 1

        file = self.files[file_path]
        if file.chunk_count == len(etags):
            await WebUi.complete_job_input_multipart_upload(file.key, file.bucket, file.upload_id, etags)
        else:
            await WebUi.abort_job_input_multipart_upload(file.key, file.bucket, file.upload_id)

    @worker("get_job_input_multipart_upload_info_full")
    async def url_signer_worker(self, iteration):
        file_path = list(self.files.keys())[iteration]
        chunk_count = self.files[file_path].chunk_count
        WebUi.host = "http://34.147.146.4"
        response = await WebUi.get_job_input_multipart_upload_info_full(self.job_id, chunk_count)
        self.files[file_path].signed_urls = response.get("links")
        self.files[file_path].key = response.get("key")
        self.files[file_path].bucket = response.get("bucket")
        self.files[file_path].upload_id = response.get("upload_id")

    async def process_file(self, file_path):
        if os.path.isfile(file_path):
            file = File(file_path)
            await file.calculate_hash()
            self.files[file.path] = file
        else:
            raise ValueError(f"File path {file_path} is not a valid file")

    async def get_files(self):
        if self.input_path:
            if os.path.isfile(self.input_path):
                await self.process_file(self.input_path)
                self.root_path = os.path.dirname(os.path.abspath(self.input_path))
            else:
                for root, _, files in os.walk(self.input_path):
                    for file in files:
                        path = os.path.join(root, file)
                        if os.path.isfile(path):
                            await self.process_file(path)
                self.root_path = os.path.abspath(self.input_path)

            self.file_count = len(self.files)
            self.file_size = sum(file.size for file in self.files.values())

            await spawn_and_wait(self.workers, self.url_signer_worker, "get_job_input_multipart_upload_info_full", self.files.keys(), workers=4)

    async def read_chunks(self, file_path):
        async with aiofiles.open(file_path, "rb") as file_object:
            while True:
                data = await file_object.read(self.chunk_size)
                if not data:
                    break
                self.files[file_path].progress += len(data)
                self.progress += len(data)
                yield data


if __name__ == "__main__":
    upload = Upload(r"/home/jonas/Desktop/package2.zip")
    asyncio.run(upload.run())
    print(upload.file_size)
