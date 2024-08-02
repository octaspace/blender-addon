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

    default_output = "/"

    if not scene.use_nodes:
        render_outputs.append([default_output, None])
    else:
        composite_added = False
        for node in scene.node_tree.nodes:
            if node.type == "COMPOSITE" and not composite_added:
                render_outputs.append([default_output, node])
                composite_added = True
            if node.type == "OUTPUT_FILE":
                for file_slot in node.file_slots:
                    file_path = ["/" + file_slot.path, node]
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
        return {"FINISHED"}


class ToggleSceneNodesOperator(bpy.types.Operator):
    bl_idname = "scene.toggle_scene_nodes"
    bl_label = "Toggle Scene Nodes"
    scene_name: bpy.props.StringProperty()
    rl_name: bpy.props.StringProperty(default="")
    new_state: bpy.props.BoolProperty()
    current_scene: bpy.props.BoolProperty(default=False)

    def execute(self, context):
        scene = context.scene
        for node in scene.node_tree.nodes:
            if node.type == "R_LAYERS":
                if node.scene.name == self.scene_name:
                    if (self.rl_name == "") or (node.layer == self.rl_name):
                        node.mute = self.new_state

        if self.rl_name != "" and self.current_scene:
            rl = bpy.data.scenes.get(self.scene_name).view_layers.get(self.rl_name)
            rl.use = not self.new_state

        if self.rl_name == "" and self.current_scene:
            for rl in bpy.data.scenes.get(self.scene_name).view_layers:
                rl.use = not self.new_state

        return {"FINISHED"}


def section(layout, properties, toggle_name, title):
    box = layout.box()
    visible = getattr(properties, toggle_name)
    box.prop(
        properties,
        toggle_name,
        text=title,
        icon="TRIA_DOWN" if visible else "TRIA_RIGHT",
        emboss=False,
    )
    if visible:
        return box
    return None


def scene_panel(layout):
    current_scene = bpy.context.scene
    if (current_scene.node_tree is None) or (not current_scene.use_nodes):
        row = layout.row()
        row.label(text=current_scene.name, icon="SCENE_DATA")
        row.prop(current_scene, "use_nodes", text="Use Nodes")
        row.enabled = True
        row = layout.row()
        row.label(text="Compositing Disabled, only using current scene.")
        return

    render_layer_nodes_scenes = set(
        [
            node.scene
            for node in current_scene.node_tree.nodes
            if node.type == "R_LAYERS"
        ]
    )

    render_nodes = set(
        [node for node in current_scene.node_tree.nodes if node.type == "R_LAYERS"]
    )

    scenes_info = {}

    for scene in bpy.data.scenes:
        render_layers_info = {}
        for view_layer in scene.view_layers:
            layer_nodes = [
                node
                for node in render_nodes
                if node.layer == view_layer.name and node.scene == scene
            ]
            render_layers_info[view_layer.name] = {
                "nodes": layer_nodes,
                "current_scene": scene == current_scene,
            }

        scenes_info[scene.name] = render_layers_info

    layout.label(text="Scene and Render Layer Rendering:")

    for scene_name in scenes_info.keys():
        scene = bpy.data.scenes[scene_name]

        col = layout.column(align=True)

        sub_box = col.box()
        row = sub_box.row()

        row.prop(
            scene,
            "show_expanded",
            text="",
            icon="TRIA_RIGHT" if not scene.show_expanded else "TRIA_DOWN",
            emboss=False,
        )

        row.label(text=scene.name, icon="SCENE_DATA")

        all_scene_nodes = [
            node
            for node in current_scene.node_tree.nodes
            if node.type == "R_LAYERS" and node.scene == scene
        ]
        majority_state = all([node.mute for node in all_scene_nodes])

        toggle_op = row.operator(
            ToggleSceneNodesOperator.bl_idname,
            text="",
            icon="RESTRICT_RENDER_ON" if majority_state else "RESTRICT_RENDER_OFF",
        )
        toggle_op.scene_name = scene.name
        toggle_op.new_state = not majority_state
        toggle_op.rl_name = ""

        if scene.show_expanded:
            for rl_name in scenes_info[scene_name].keys():
                all_rl_nodes = scenes_info[scene_name][rl_name]["nodes"]

                rl_majority_state = all([node.mute for node in all_rl_nodes])
                rl = scene.view_layers.get(rl_name)

                if len(all_rl_nodes) == 0:
                    rl_majority_state = not rl.use

                if (
                    scenes_info[scene_name][rl_name]["current_scene"]
                    or len(all_rl_nodes) != 0
                ):
                    sub_row = sub_box.row()
                    sub_row.label(text=rl_name, icon="RENDERLAYERS")

                    if len(all_rl_nodes) == 0:
                        sub_row.label(
                            text="Not used in Compositor!",
                            icon="ERROR",
                        )

                    toggle_op = sub_row.operator(
                        ToggleSceneNodesOperator.bl_idname,
                        text="",
                        icon=(
                            "RESTRICT_RENDER_ON"
                            if rl_majority_state
                            else "RESTRICT_RENDER_OFF"
                        ),
                    )
                    toggle_op.scene_name = scene.name
                    toggle_op.rl_name = rl_name
                    toggle_op.new_state = not rl_majority_state
                    toggle_op.current_scene = scenes_info[scene_name][rl_name][
                        "current_scene"
                    ]


# exporter panel
class OctaPanel(Panel):
    bl_idname = "SCENE_PT_octa_panel"
    bl_label = "Octa Render"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"
    bl_options = {"DEFAULT_CLOSED"}

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
            row.progress(
                text=SubmitJobOperator.get_progress_name(),
                factor=SubmitJobOperator.get_progress(),
            )

        box = section(
            layout, properties, "advanced_section_visible", "Advanced Options"
        )
        if box is not None:
            row = box.row()
            row.prop(properties, "generate_video")
            row = box.row()
            row.prop(properties, "max_thumbnail_size")
            row = box.row()
            row.prop(properties, "blender_version")

            scene_vis_box = section(
                box, properties, "scene_visibility_visible", "Scene Rendering"
            )

            if scene_vis_box is not None:
                scene_panel(scene_vis_box)

            section_box = section(
                box, properties, "render_output_path_visible", "Render Output"
            )

            if section_box is not None:
                all_paths = []
                if (
                    scene.use_nodes
                    and scene.render.use_compositing
                    and scene.node_tree is not None
                ):
                    node_box = section_box.box()
                    row = node_box.row()
                    row.label(text="File Output:", icon="FORWARD")

                    if scene.use_nodes:
                        row.label(text="Composite", icon="NODE_COMPOSITING")
                    else:
                        row.label(text="Output", icon="OUTPUT")

                    composite_nodes = [
                        node
                        for node in scene.node_tree.nodes
                        if node.type == "COMPOSITE"
                    ]
                    if len(composite_nodes) > 0:
                        select_op = row.operator(
                            SelectNodeOperator.bl_idname,
                            text="",
                            icon="RESTRICT_SELECT_OFF",
                        )
                        select_op.node_name = composite_nodes[0].name

                    file_ext = IMAGE_TYPE_TO_EXTENSION.get(
                        scene.render.image_settings.file_format, "unknown"
                    )
                    row = node_box.row(align=True)
                    frame_suffix = f"/{str(scene.frame_current).zfill(4)}.{file_ext}"
                    row.label(text=frame_suffix, icon="URL")

                    for node in scene.node_tree.nodes:
                        if node.type == "OUTPUT_FILE":
                            node_box = section_box.box()
                            row = node_box.row()
                            row.label(text="File Output Node:", icon="FORWARD")
                            row.label(text=node.name, icon="NODE")
                            select_op = row.operator(
                                SelectNodeOperator.bl_idname,
                                text="",
                                icon="RESTRICT_SELECT_OFF",
                            )
                            select_op.node_name = node.name
                            # row.prop(node, "base_path", text="")

                            bp = node.base_path
                            formatted_base_path = bp.rstrip("/\\") + (
                                "\\" if bp.count("\\") > bp.count("/") else "/"
                            )

                            # box = node_box.box()

                            if node.format.file_format == "OPEN_EXR_MULTILAYER":
                                row = node_box.row()

                                row.prop(
                                    node.octa_node_properties,
                                    "multilayer_directory",
                                    text="Multilayer Directory Name",
                                )

                            row = node_box.row()
                            col = row.column(align=True)
                            col.label(text="Base Path")
                            col = row.column(align=True)
                            col.label(
                                text=(
                                    "Layer"
                                    if node.format.file_format == "OPEN_EXR_MULTILAYER"
                                    else "File Subpath"
                                )
                            )
                            row.scale_y = 0.5

                            split = node_box.split()
                            col = split.column(align=True)

                            for slot in node.file_slots:
                                box = col.box()

                                row = box.row()
                                row.scale_y = 1.0
                                # row.label(text=formatted_base_path)
                                file_ext = IMAGE_TYPE_TO_EXTENSION.get(
                                    node.format.file_format, "unknown"
                                )
                                row.label(text="", icon="URL")
                                bp_stem = Path(formatted_base_path).stem

                                if node.format.file_format != "OPEN_EXR_MULTILAYER":
                                    row.label(
                                        text=f"/{slot.path}/{str(scene.frame_current).zfill(4)}.{file_ext}"
                                    )
                                else:
                                    row.label(
                                        text=f"/{node.octa_node_properties.multilayer_directory}/{str(scene.frame_current).zfill(4)}.exr"
                                    )

                                row.prop(slot, "path", text="")

                                full_path = slot.path
                                if full_path in all_paths:
                                    row = node_box.row()
                                    row.label(
                                        text=f'Output Path "{str(full_path)}" already in use!',
                                        icon="ERROR",
                                    )
                                all_paths.append(full_path)
                                # row.operator(SelectNodeOperator.bl_idname, text="", icon="FILE_FOLDER").node_name = node.name
                else:
                    if not scene.use_nodes:
                        row = section_box.row()
                        row.label(text="Use Nodes must be enabled:", icon="ERROR")
                        row.prop(scene, "use_nodes", text="Use Nodes")

                    if not scene.render.use_compositing:
                        row = section_box.row()
                        row.label(text="Use Compositing must be enabled:", icon="ERROR")
                        row.prop(
                            scene.render, "use_compositing", text="Use Compositing"
                        )

        # download stuff
        box = section(layout, properties, "download_section_visible", "Download")
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
                row.progress(
                    text=DownloadJobOperator.instance.get_progress_name(),
                    factor=DownloadJobOperator.instance.get_progress(),
                )

        def denoise_suggestion(layout, denoise_nodes):
            sug_box = layout.box()
            row = sug_box.row()
            row.label(text="Denoise Node Found!", icon="SORTTIME")
            row.operator(
                SelectNodeOperator.bl_idname, text="", icon="RESTRICT_SELECT_OFF"
            ).node_name = denoise_nodes[0].name
            row = sug_box.row()
            row.label(
                text="The Denoising Node may be slow and incompatible with multilayer EXR files."
            )

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
                denoise_nodes = [
                    node for node in scene.node_tree.nodes if node.type == "DENOISE"
                ]
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

        box = section(
            layout,
            properties,
            "suggestions_section_visible",
            f"{suggestion_count} Suggestions",
        )
        if box is not None:
            if suggestion_count == 0:
                box.label(text="No Suggestions", icon="INFO")
            else:
                suggestion_count = suggestion_draw(box, suggestion_count, True)
