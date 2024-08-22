import uuid
import hashlib


def get_next_id() -> str:
    return str(uuid.uuid4())  # TODO: replace with uuid7 once it is added to python because they are sortable by timestamp


def get_file_md5(path: str) -> str:
    hasher = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


IMAGE_TYPE_TO_EXTENSION = {
    'BMP': 'bmp',
    'IRIS': 'iris',
    'PNG': 'png',
    'JPEG': 'jpg',
    'JPEG2000': 'jp2',
    'TARGA': 'tga',
    'TARGA_RAW': 'tga',
    'CINEON': 'cin',
    'DPX': 'dpx',
    'OPEN_EXR': 'exr',
    'OPEN_EXR_MULTILAYER': 'exr',
    'HDR': 'hdr',
    'TIFF': 'tif',
    'WEBP': 'webp',
}
