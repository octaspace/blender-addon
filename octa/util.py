import bpy
from typing import TypedDict

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


class RenderPass(TypedDict):
    name: str
    files: dict[str, str]


def get_all_output_file_nodes():
    scenes = bpy.data.scenes
    nodes = []
    for scene in scenes:
        if not scene.use_nodes:
            continue

        for node in scene.node_tree.nodes:
            if node.type == 'OUTPUT_FILE':
                nodes.append(node)

    return nodes


def get_all_render_passes() -> dict[str, RenderPass]:
    nodes = get_all_output_file_nodes()
    render_passes = {}
    for node in nodes:
        name = node.name
        files = {}  # dict of file_name => extension
        node_file_format = node.format.file_format
        for file_slot in node.file_slots:
            if file_slot.use_node_format:
                file_format = node_file_format
            else:
                file_format = file_slot.format.file_format
            file_path = file_slot.path
            files[file_path] = IMAGE_TYPE_TO_EXTENSION.get(file_format, 'unknown')

        render_passes[name] = {
            "name": name,
            "files": files,
        }

    return render_passes
