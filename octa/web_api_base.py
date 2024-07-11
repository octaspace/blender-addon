import time
import random
import os
import requests


class WebApiBase:
    requests_session: requests.Session = None

    @classmethod
    def get_session(cls) -> requests.Session:
        if cls.requests_session is None:
            cls.requests_session = requests.Session()
        return cls.requests_session

    @classmethod
    def request_with_retries(cls, method, url, *, retries=3, **kwargs) -> requests.Response:
        session = cls.get_session()
        tries = 0
        while True:
            tries += 1
            try:
                if 'data' in kwargs:
                    if hasattr(kwargs['data'], 'seek'):
                        kwargs['data'].seek(0)
                if 'timeout' not in kwargs:
                    kwargs['timeout'] = (15, 15)
                response = session.request(method, url, **kwargs)
                # response = pool.request(method, url, fields, headers, **kwargs)
                if 200 <= response.status_code <= 299:
                    return response
                elif 400 <= response.status_code <= 499:
                    # no retries on err 4xx
                    tries = 100000
                    err = f"{method} to {url} failed with status {response.status_code}, content: {response.content[:1000]}"
                    print(err)
                    raise Exception(err)
                else:
                    err = f"{method} to {url} failed with status {response.status_code}, content: {response.content[:1000]}"
                    print(err)
                    if tries >= retries:
                        raise Exception(err)
                    time.sleep(tries + random.random())
            except:
                if tries >= retries:
                    raise
                time.sleep(tries + random.random())

    @classmethod
    def _sanitize_path(cls, path):
        if path is None or path == '' or path == '/':
            return '/'
        else:
            path = path.replace('\\', '/')
            return '/'.join([p for p in path.split('/') if p])

    @classmethod
    def _sanitize_path_join(cls, *args):
        paths = []
        for path in args:
            paths.append(cls._sanitize_path(path))
        return '/'.join(paths)


class FileWithCallback():
    def __init__(self, path, mode, callback):
        self.file = open(path, mode)
        self.file.seek(0, os.SEEK_END)
        self.size = self.file.tell()
        self.file.seek(0)
        self.callback = callback

    def read(self, size):
        data = self.file.read(size)
        offset = self.file.tell()
        if self.callback:
            self.callback(offset, self.size)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        return self.file.seek(offset, whence)

    def close(self):
        self.file.close()


class FileSliceWithCallback():
    def __init__(self, file, offset, size, callback):
        self.file = file
        self.callback = callback
        self.fake_offset = offset
        self.fake_size = size
        self.end = self.fake_offset + self.fake_size

    def get_fake_pos(self):
        return self.file.tell() - self.fake_offset

    def read(self, size):
        over = self.file.tell() - self.end + size
        if over > 0:  # make sure we dont read out over our fake file end
            size -= over

        data = self.file.read(size)

        if self.callback:
            self.callback(self.get_fake_pos(), self.fake_size)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == os.SEEK_SET:
            return self.file.seek(self.fake_offset + offset, whence)
        elif whence == os.SEEK_END:
            return self.file.seek(self.end + offset, os.SEEK_SET)
        raise Exception("just dont")
