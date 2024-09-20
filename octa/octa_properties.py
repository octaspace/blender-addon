import bpy
from bpy.types import PropertyGroup


# class to be passed into thread
class DownloadJobProperties:
    job_id: str
    output_path: str
    octa_farm_config: str
    download_threads: int


# class to be passed into thread
class SubmitJobProperties:
    temp_blend_name: str
    temp_work_folder: str
    job_name: str
    frame_start: int
    frame_end: int
    frame_step: int
    match_scene: bool
    batch_size: int
    render_output_path: str
    octa_farm_config: str
    upload_threads: int
    render_format: str
    max_thumbnail_size: int
    generate_video: bool
    advanced_section_visible: bool
    blender_version: str


def get_section_toggle_type(name):
    return bpy.props.BoolProperty(name=name, description=name, default=False)


class OctaNodeProperties(PropertyGroup):
    def update_multilayer_directory(self):
        self.multilayer_directory = (
            self.multilayer_directory
            if self.multilayer_directory != ""
            else "MultiLayer"
        )

    multilayer_directory: bpy.props.StringProperty(
        name="Multilayer Directory",
        description="Multilayer Directory",
        default="MultiLayer",
        update=lambda self, context: self.update_multilayer_directory(),
    )


# scene properties
class OctaProperties(PropertyGroup):
    job_name: bpy.props.StringProperty(
        name="Job Name", description="Job Name", default=""
    )
    frame_start: bpy.props.IntProperty(
        name="Start Frame",
        description="Frame Start",
        default=1,
        min=1,
        max=100000,
    )
    frame_end: bpy.props.IntProperty(
        name="End Frame", description="Frame End", default=1, min=1, max=100000
    )
    frame_step: bpy.props.IntProperty(
        name="Frame Step", description="Frame Step", default=1, min=1
    )
    frame_current: bpy.props.IntProperty(
        name="Current Frame", description="Current Frame", default=1, min=1
    )
    match_scene: bpy.props.BoolProperty(
        name="Match Scene", description="Match Scene", default=True
    )
    batch_size: bpy.props.IntProperty(
        name="Batch Size", description="Batch Size", default=1, min=1, max=100
    )
    batch_size_tmp: bpy.props.IntProperty(
        name="Batch Size",
        description="Variable batch size isn't currently supported for frame step sizes greater than 1.",
        default=1,
        min=1,
        max=1,
    )
    batch_size_warning: bpy.props.BoolProperty(
        name="Batch Size Warning",
        description="Variable batch size isn't currently supported for frame step sizes greater than 1.",
        default=False,
    )
    render_output_path: bpy.props.StringProperty(
        name="Render Output Path", description="Render Output Path", default=""
    )

    octa_farm_config: bpy.props.StringProperty(
        name="Octa Farm Config",
        description="The configuration token retrieved from your render farm",
        default="",
    )
    upload_threads: bpy.props.IntProperty(
        name="Upload Threads",
        description="How many threads to use when uploading.",
        default=1,
        min=1,
        max=1,
    )

    render_type: bpy.props.EnumProperty(
        name="Render Type",
        description="Choose the render type",
        items=[
            ("IMAGE", "Image", "Render a single image", "RENDER_STILL", 0),
            (
                "ANIMATION",
                "Animation",
                "Render an animation sequence",
                "RENDER_ANIMATION",
                1,
            ),
        ],
        default="ANIMATION",
    )

    render_format: bpy.props.EnumProperty(
        name="Render Format",
        description="Render Format",
        items=[
            ("PNG", "PNG", "PNG"),
            ("JPEG", "JPEG", "JPEG"),
            ("OPEN_EXR", "OpenEXR", "OpenEXR"),
            # ("TIFF", "TIFF", "TIFF"),
            # ("OPEN_EXR_MULTILAYER", "OpenEXR MultiLayer", "OpenEXR MultiLayer"),
            # ("BMP", "BMP", "BMP"),
        ],
        default="PNG",
    )

    blender_version: bpy.props.EnumProperty(
        name="Blender Version",
        description="Blender Version",
        items=[("blender41", "4.1", "4.1"), ("blender42", "4.2", "4.2")],
        default="blender41",
    )

    max_thumbnail_size: bpy.props.EnumProperty(
        name="Max Thumbnail Size",
        description="Max Thumbnail Size",
        items=[
            ("256", "256 px", "256 px"),
            ("512", "512 px", "512 px"),
            ("1024", "1024 px", "1024 px"),
            ("2048", "2048 px", "2048 px"),
        ],
        default="1024",
    )

    generate_video: bpy.props.BoolProperty(
        name="Generate Video", description="Generate Video", default=False
    )

    # download properties
    dl_job_id: bpy.props.StringProperty(name="Job Id", description="Job Id", default="")
    dl_output_path: bpy.props.StringProperty(
        name="Download Output Path",
        description="Download Output Path",
        default="",
        subtype="DIR_PATH",
        update=lambda self, context: self.update_dl_output_path(),
    )
    dl_threads: bpy.props.IntProperty(
        name="Download Threads",
        description="How many threads to use when downloading",
        default=8,
        min=1,
        max=8,
    )

    # section toggles
    advanced_section_visible: get_section_toggle_type(name="Advanced Section Visible")
    render_output_path_visible: get_section_toggle_type(
        name="Render Output Section Visible"
    )
    download_section_visible: get_section_toggle_type(name="Download Section Visible")
    suggestions_section_visible: get_section_toggle_type(
        name="Suggestions Section Visible"
    )
    scene_visibility_visible: get_section_toggle_type(
        name="Scene Visibility Section Visible"
    )

    content_manager_visible: get_section_toggle_type(
        name="Content Manager Section Visible"
    )

    debug_zip: bpy.props.BoolProperty(
        name="Debug ZIP",
        description="Enable debug ZIP for additional logging",
        default=False,
    )

    def update_dl_output_path(self):
        self.dl_output_path = bpy.path.abspath(self.dl_output_path)
