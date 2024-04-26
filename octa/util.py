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
    scene = bpy.context.scene
    output_nodes = []

    if scene.use_nodes:
        for node in scene.node_tree.nodes:
            if node.type == 'OUTPUT_FILE':
                output_nodes.append(node)

    return output_nodes

def get_all_render_passes() -> dict[str, RenderPass]:
    output_nodes = get_all_output_file_nodes()
    render_passes = {}

    for node in output_nodes:
        name = node.name
        files = {}

        default_format = node.format.file_format

        for slot in node.file_slots:
            format_to_use = default_format if slot.use_node_format else slot.format.file_format
            path = slot.path
            extension = IMAGE_TYPE_TO_EXTENSION.get(format_to_use, 'unknown')
            files[path] = extension

        render_passes[name] = {
            "name": name,
            "files": files
        }

    return render_passes
