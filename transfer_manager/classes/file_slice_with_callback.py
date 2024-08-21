from typing import BinaryIO
import os


class FileSliceWithCallback():
    def __init__(self, file: BinaryIO, offset: int, size: int, callback: callable):
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
