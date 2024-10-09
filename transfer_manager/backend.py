import time, os
import httpx
import asyncio
import aiofiles


class Sessions():
    uploads = {}
    downloads = {}

    @classmethod
    def toJSON(cls):
        return {
            "uploads": [upload.toJSON() for upload in cls.uploads.values()],
            "downloads": [download.toJSON() for download in cls.uploads.values()]
        }


class Upload():
    def __init__(self, directory) -> None:
        self.session_id = int(time.time())
        self.progress = 0
        self.input_path = directory
        self.files = {}
        self.file_count = 0
        self.file_size = 0
        self.root_path = None
        self.get_files()
        self.client = httpx.AsyncClient()
        self.running_uploads = 0
        self.upload_errors = 0

    
    def toJSON(self):
        return {
                "session_id": self.session_id,
                "progress": self.progress,
                "input_path": self.input_path,
                "files": self.files,
                "file_count": self.file_count,
                "file_size": self.file_size,
                "root_path": self.root_path
                }

    
    async def worker(self, file_path):
        self.running_uploads += 1
        try:
            await self.client.post('http://127.0.0.1:9999/upload', content=self.read_chunks(file_path))
        except:
            self.upload_errors += 1
        self.running_uploads -= 1


    async def start(self):
        iteration = 0
        file = self.next_file()
        while True:
            
            if self.running_uploads < 4:
                _f = next(file)
                print(self.running_uploads, iteration, _f)
                asyncio.create_task(self.worker(_f))
                iteration += 1
                if iteration == self.file_count:
                    break
            await asyncio.sleep(0.01)

        
    def next_file(self):
        for file in self.files:
            yield file

    def get_files(self):
        if self.input_path:

            if os.path.isfile(self.input_path):
                path = os.path.abspath(self.input_path)
                self.files[path] = {"progress": 0, "size": os.path.getsize(path)}
                self.root_path = os.path.dirname(os.path.abspath(self.input_path))

            else:
                for root, _, files in os.walk(self.input_path):
                    for file in files:
                        path = os.path.abspath(os.path.join(root, file))
                        self.files[path] = {"progress": 0, "size": os.path.getsize(path)}

                self.root_path = os.path.abspath(self.input_path)

            self.file_count = len(self.files)
            self.file_size = sum([file['size'] for file in self.files.values()])


    async def read_chunks(self, file_path, chunk_size=1000*1000*2):
        async with aiofiles.open(file_path, 'rb') as file_object:
            while True:
                data = await file_object.read(chunk_size)
                if not data:
                    break
                self.files[file_path]['progress'] += len(data)
                self.progress += len(data)
                yield data
    


class Download():
    """
    This is VERY WIP, do not use
    """
    def __init__(self, directory) -> None:
        self.session_id = int(time.time())
        self.progress = 0
        self.input_path = directory
        self.files = {}
        self.file_count = 0
        self.file_size = 0
        self.root_path = None
        self.get_files()
        self.client = httpx.AsyncClient()
        self.running_uploads = 0
        self.upload_errors = 0

    
    def toJSON(self):
        return {
                "session_id": self.session_id,
                "progress": self.progress,
                "input_path": self.input_path,
                "files": self.files,
                "file_count": self.file_count,
                "file_size": self.file_size,
                "root_path": self.root_path
                }

    
    async def worker(self, file_path):
        self.running_uploads += 1
        try:
            await self.client.get('http://127.0.0.1:9999/upload', content=self.read_chunks(file_path))
        except:
            self.upload_errors += 1
        self.running_uploads -= 1


    async def start(self):
        iteration = 0
        file = self.next_file()
        while True:
            
            if self.running_uploads < 4:
                _f = next(file)
                print(self.running_uploads, iteration, _f)
                asyncio.create_task(self.worker(_f))
                iteration += 1
                if iteration == self.file_count:
                    break
            await asyncio.sleep(0.01)

        
    def next_file(self):
        for file in self.files:
            yield file

    async def get_files(self):
        response = await self.client.get('http://farm_url/user_id/job_id')
        if response.status_code == 200:
            data = response.json()




    

if __name__ == "__main__":
    upload = Upload(r"/tmp/")
    upload.start()
    print(upload.file_size)
