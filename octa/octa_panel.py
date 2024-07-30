import bpy
import os
from pathlib import Path
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
        context.scene.node_tree.nodes.active = node
        return {'FINISHED'}

class ToggleSceneNodesOperator(bpy.types.Operator):
    bl_idname = "scene.select_node"
    bl_label = "Select Node"
    scene_name: bpy.props.StringProperty()
    new_state: bpy.props.BoolProperty()

    def execute(self, context):
        scene = context.scene
        for node in scene.node_tree.nodes:
            if node.type == 'R_LAYERS':
                if node.scene.name == self.scene_name:
                    node.mute = self.new_state
        
        return {'FINISHED'}


def section(layout, properties, toggle_name, title):
    box = layout.box()
    visible = getattr(properties, toggle_name)
    box.prop(properties, toggle_name, text=title, icon="TRIA_DOWN" if visible else "TRIA_RIGHT", emboss=False)
    if visible:
        return box
    return None

def scene_panel(layout):
    current_scene = bpy.context.scene
    if current_scene.node_tree is None:
        row = layout.row()
        row.label(text=current_scene.name, icon="SCENE_DATA")
        row.operator(ToggleSceneNodesOperator.bl_idname, text="Enable Nodes", icon="NODETREE").scene_name = current_scene.name
        row.enabled = False
        row = layout.row()
        row.label(text="Compositing Disabled, only using current scene.")
        return
        
    render_layer_nodes_scenes = set([node.scene for node in current_scene.node_tree.nodes if node.type == 'R_LAYERS'])

    layout.label(text="Used Scenes in compositor nodes:")

    for scene in render_layer_nodes_scenes:
        col = layout.column(align=True)

        sub_box = col.box()
        row = sub_box.row()

        row.prop(scene, "show_expanded", text="", icon="TRIA_RIGHT" if not scene.show_expanded else "TRIA_DOWN", emboss=False)

        row.label(text=scene.name, icon="SCENE_DATA")
        
        all_nodes = [node for node in current_scene.node_tree.nodes if node.type == 'R_LAYERS' and node.scene == scene]
        majority_state = all([node.mute for node in all_nodes])
        
        toggle_op = row.operator(ToggleSceneNodesOperator.bl_idname, text="", icon="HIDE_ON" if majority_state else "HIDE_OFF")
        toggle_op.scene_name = scene.name
        toggle_op.new_state = not majority_state

        if scene.show_expanded:
            for rl_node in all_nodes:
                sub_row = sub_box.row()
                sub_row.label(text=rl_node.name, icon="NODE")
                sub_row.prop(rl_node, "mute", text="", icon='HIDE_OFF' if not rl_node.mute else 'HIDE_ON', emboss=False)



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
        scene = context.scene
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

        box = section(layout, properties, "scene_visibility_visible", "Scene Visibility")
        if box is not None:
            scene_panel(box)

        box = section(layout, properties, "render_output_path_visible", "Render Output")
        if box is not None:
            all_paths = []
            if scene.use_nodes and scene.render.use_compositing and scene.node_tree is not None:
                node_box = box.box()
                row = node_box.row()
                row.label(text="File Output:", icon="FORWARD")

                if scene.use_nodes:
                    row.label(text="Composite", icon="NODE_COMPOSITING")
                else:
                    row.label(text="Output", icon="OUTPUT")

                composite_nodes = [node for node in scene.node_tree.nodes if node.type == 'COMPOSITE']
                if len(composite_nodes) > 0:
                    row.operator(SelectNodeOperator.bl_idname, text="", icon="RESTRICT_SELECT_OFF").node_name = composite_nodes[0].name

                file_ext = IMAGE_TYPE_TO_EXTENSION.get(scene.render.image_settings.file_format, 'unknown')
                row = node_box.row(align=True)
                frame_suffix = f'/{str(scene.frame_current).zfill(4)}.{file_ext}'
                row.label(text=frame_suffix, icon="URL")

                for node in scene.node_tree.nodes:
                    if node.type == 'OUTPUT_FILE':
                        node_box = box.box()
                        row = node_box.row()
                        row.label(text="File Output Node:", icon="FORWARD")
                        row.label(text=node.name, icon="NODE")
                        row.operator(SelectNodeOperator.bl_idname, text="", icon="RESTRICT_SELECT_OFF").node_name = node.name
                        # row.prop(node, "base_path", text="")

                        bp = node.base_path
                        formatted_base_path = bp.rstrip('/\\') + ('\\' if bp.count('\\') > bp.count('/') else '/')

                        for slot in node.file_slots:
                            row = node_box.row(align=True)
                            # row.label(text=formatted_base_path)
                            file_ext = IMAGE_TYPE_TO_EXTENSION.get(node.format.file_format, 'unknown')
                            row.label(text="", icon="URL")
                            row.label(text=f'/{slot.path}/{str(scene.frame_current).zfill(4)}.{file_ext}')

                            row.prop(slot, "path", text="")

                            full_path = slot.path
                            if full_path in all_paths:
                                row = node_box.row()
                                row.label(text=f'Output Path "{str(full_path)}" already in use!', icon="ERROR")
                            all_paths.append(full_path)
                            # row.operator(SelectNodeOperator.bl_idname, text="", icon="FILE_FOLDER").node_name = node.name
            else:
                if not scene.use_nodes:
                    row = box.row()
                    row.label(text="Use Nodes must be enabled:", icon="ERROR")
                    row.prop(scene, "use_nodes", text="Use Nodes")

                if not scene.render.use_compositing:
                    row = box.row()
                    row.label(text="Use Compositing must be enabled:", icon="ERROR")
                    row.prop(scene.render, "use_compositing", text="Use Compositing")

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

        def denoise_suggestion(layout, denoise_nodes):
            sug_box = layout.box()
            row = sug_box.row()
            row.label(text="Denoise Node Found!", icon="SORTTIME")
            row.operator(SelectNodeOperator.bl_idname, text="", icon="RESTRICT_SELECT_OFF").node_name = denoise_nodes[0].name
            row = sug_box.row()
            row.label(text="The Denoising Node may be slow and incompatible with multilayer EXR files.")

        def use_nodes_suggestion(layout):
            sug_box = layout.box()
            row = sug_box.row()
            row.label(text="Use Nodes Disabled!", icon="ERROR")
            row = sug_box.row()
            row.label(text="To use output paths Use Nodes must be enabled.")
            row = sug_box.row()
            row.prop(scene, "use_nodes", text="Use Nodes")

        def use_compositing_suggestion(layout):
            sug_box = layout.box()
            row = sug_box.row()
            row.label(text="Use Compositing Disabled!", icon="ERROR")
            row = sug_box.row()
            row.label(text="To use output paths Use Compositing must be enabled.")
            row = sug_box.row()
            row.prop(scene.render, "use_compositing", text="Use Compositing")

        def suggestion_draw(layout, suggestion_count=0, draw=True):
            if scene.node_tree:
                denoise_nodes = [node for node in scene.node_tree.nodes if node.type == 'DENOISE']
                if len(denoise_nodes) > 0:
                    if draw:
                        denoise_suggestion(layout, denoise_nodes)
                    suggestion_count += 1
            if not scene.use_nodes:
                if draw:
                    use_nodes_suggestion(layout)
                suggestion_count += 1
            if not scene.render.use_compositing:
                if draw:
                    use_compositing_suggestion(layout)
                suggestion_count += 1
            return suggestion_count

        suggestion_count = 0
        suggestion_count = suggestion_draw(box, suggestion_count, False)

        box = section(layout, properties, "suggestions_section_visible", f"{suggestion_count} Suggestions")
        if box is not None:
            if suggestion_count == 0:
                box.label(text="No Suggestions", icon="INFO")
            else:
                suggestion_count = suggestion_draw(box, suggestion_count, True)