import bpy
from bpy.types import PropertyGroup


# class to be passed into thread
class DownloadJobProperties:
    job_id: str
    output_path: str
    octa_host: str
    download_threads: int


# class to be passed into thread
class SubmitJobProperties:
    temp_blend_name: str

    job_name: str
    frame_start: int
    frame_end: int
    match_scene: bool
    batch_size: int
    render_output_path: str
    octa_host: str
    upload_threads: int
    render_format: str
    max_thumbnail_size: int
    generate_video: bool
    advanced_section_visible: bool
    blender_version: str


def get_section_toggle_type(name):
    return bpy.props.BoolProperty(name=name, description=name, default=False)


# scene properties
class OctaProperties(PropertyGroup):
    job_name: bpy.props.StringProperty(name="Job Name", description="Job Name", default="")
    frame_start: bpy.props.IntProperty(name="Start Frame", description="Frame Start", default=1, min=1, max=100000)
    frame_end: bpy.props.IntProperty(name="End Frame", description="Frame End", default=1, min=1, max=100000)
    match_scene: bpy.props.BoolProperty(name="Match Scene", description="Match Scene", default=True)
    batch_size: bpy.props.IntProperty(name="Batch Size", description="Batch Size", default=1, min=1, max=100)
    render_output_path: bpy.props.StringProperty(name="Render Output Path", description="Render Output Path", default="")
    octa_host: bpy.props.StringProperty(name="Octa Host", description="The Host of the Web UI (e.g. http://127.0.0.1:51800)", default="http://34.147.146.4/")
    upload_threads: bpy.props.IntProperty(name="Upload Threads", description="How many threads to use when uploading.", default=1, min=1, max=1)

    render_format: bpy.props.EnumProperty(name="Render Format", description="Render Format", items=[
        ("PNG", "PNG", "PNG"),
        ("JPEG", "JPEG", "JPEG"),
        ("OPEN_EXR", "OPEN_EXR", "OPEN_EXR"),
        # ("TIFF", "TIFF", "TIFF"),
        # ("OPEN_EXR_MULTILAYER", "OpenEXR MultiLayer", "OpenEXR MultiLayer"),
        # ("BMP", "BMP", "BMP"),
    ], default="PNG", )

    blender_version: bpy.props.EnumProperty(name="Blender Version", description="Blender Version", items=[("blender41", "4.1", "4.1"),("blender42", "4.2", "4.2")], default="blender41")

    max_thumbnail_size: bpy.props.IntProperty(name="Max Thumbnail Size", description="Max Thumbnail Size", default=1024, min=512, max=4096, subtype="PIXEL")
    generate_video: bpy.props.BoolProperty(name="Generate Video", description="Generate Video", default=False)

    # download properties
    dl_job_id: bpy.props.StringProperty(name="Job Id", description="Job Id", default="")
    dl_output_path: bpy.props.StringProperty(name="Download Output Path", description="Download Output Path", default="", subtype="DIR_PATH")
    dl_threads: bpy.props.IntProperty(name="Download Threads", description="How many threads to use when downloading", default=10, min=1, max=32)

    # section toggles
    advanced_section_visible: get_section_toggle_type(name="Advanced Section Visible")
    render_output_path_visible: get_section_toggle_type(name="Render Output Section Visible")
    download_section_visible: get_section_toggle_type(name="Download Section Visible")
    suggestions_section_visible: get_section_toggle_type(name="Suggestions Section Visible")
    scene_visibility_visible: get_section_toggle_type(name="Scene Visibility Section Visible")