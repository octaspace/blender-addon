import bpy
import os
from bpy.types import Panel
from .submit_job_operator import SubmitJobOperator
from .download_job_operator import DownloadJobOperator
from .util import get_all_render_passes, IMAGE_TYPE_TO_EXTENSION


def get_all_render_output_paths(context):
    scene = context.scene

    render_outputs = []

    default_output = '/'

    if not scene.use_nodes:
        render_outputs.append([default_output, None])
    else:
        composite_added = False
        for node in scene.node_tree.nodes:
            if node.type == 'COMPOSITE' and not composite_added:
                render_outputs.append([default_output, node])
                composite_added = True
            if node.type == 'OUTPUT_FILE':
                for file_slot in node.file_slots:
                    file_path = ['/' + file_slot.path, node]
                    render_outputs.append(file_path)

    return render_outputs


class SelectNodeOperator(bpy.types.Operator):
    bl_idname = "scene.select_node"
    bl_label = "Select Node"
    node_name: bpy.props.StringProperty()

    def execute(self, context):
        node = context.scene.node_tree.nodes.get(self.node_name)
        for n in context.scene.node_tree.nodes:
            n.select = True if n == node else False
        return {'FINISHED'}


def section(layout, properties, toggle_name, title):
    box = layout.box()
    visible = getattr(properties, toggle_name)
    box.prop(properties, toggle_name, text=title, icon="TRIA_DOWN" if visible else "TRIA_RIGHT", emboss=False)
    if visible:
        return box
    return None


# exporter panel
class OctaPanel(Panel):
    bl_idname = "SCENE_PT_octa_panel"
    bl_label = "Octa Render"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        properties = context.scene.octa_properties

        layout = self.layout

        # render stuff
        box = layout.box()
        box.prop(properties, "job_name")
        box.prop(properties, "render_format")

        box = layout.box()
        row = box.row()
        row.prop(properties, "match_scene", text="Match Scene Range")
        row = box.row(align=True)
        if properties.match_scene:
            row.prop(context.scene, "frame_start")
            row.prop(context.scene, "frame_end")
            row.enabled = False
        else:
            row.prop(properties, "frame_start")
            row.prop(properties, "frame_end")
            row.enabled = True

        box = layout.box()
        row = box.row()
        row.prop(properties, "octa_host")
        # row = box.row()
        # row.prop(properties, "upload_threads")
        row = box.row()
        row.prop(properties, "batch_size")

        row = box.row()
        row.operator(SubmitJobOperator.bl_idname)
        if SubmitJobOperator.get_running():
            row = layout.row()
            row.progress(text=SubmitJobOperator.get_progress_name(), factor=SubmitJobOperator.get_progress())

        box = section(layout, properties, "advanced_section_visible", "Advanced Options")
        if box is not None:
            row = box.row()
            row.prop(properties, "generate_video")
            row = box.row()
            row.prop(properties, "max_thumbnail_size")

        box = section(layout, properties, "render_output_path_visible", "Render Output")
        if box is not None:
            render_passes = get_all_render_passes()
            for render_pass_name, render_pass in render_passes.items():
                for file_name, file_ext in render_pass["files"].items():
                    file_full_name = f'{file_name}/{str(0).zfill(4)}.{file_ext}'
                    row = box.row()
                    row.label(text=file_full_name)
                    row.label(text=render_pass_name, icon="NODE")
                    row.operator(SelectNodeOperator.bl_idname, text="", icon="RESTRICT_SELECT_OFF").node_name = render_pass_name

            file_ext = IMAGE_TYPE_TO_EXTENSION.get(bpy.context.scene.render.image_settings.file_format, 'unknown')
            row = box.row()
            row.label(text=f'{str(0).zfill(4)}.{file_ext}')

            """
            render_outputs = get_all_render_output_paths(context)
            for path, node in render_outputs:
                row = box.row()
                row.label(text=path)
                if node:
                    row.label(text=node.name, icon="NODE")
                    row.operator(SelectNodeOperator.bl_idname, text="", icon="RESTRICT_SELECT_OFF").node_name = node.name
                    """

        # download stuff
        box = section(layout, properties, 'download_section_visible', "Download")
        if box is not None:
            box.prop(properties, "dl_job_id")

            row = box.row()
            row.prop(properties, "dl_output_path")

            row = box.row()
            row.prop(properties, "dl_threads")

            row = box.row()
            row.operator(DownloadJobOperator.bl_idname)

            if DownloadJobOperator.get_running():
                row = layout.row()
                row.progress(text=DownloadJobOperator.instance.get_progress_name(), factor=DownloadJobOperator.instance.get_progress())
