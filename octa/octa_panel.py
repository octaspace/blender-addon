import bpy
import os
from pathlib import Path
from bpy.types import Panel
from .submit_job_operator import SubmitJobOperator
from .download_job_operator import DownloadJobOperator
from .util import (
    get_all_render_passes,
    get_preferences,
    IMAGE_TYPE_TO_EXTENSION,
    section,
)
from .icon_manager import IconManager

# Global dictionary to store visibility states
visibility_states = {}


class ToggleVisibilityOperator(bpy.types.Operator):
    """Toggle the visibility of a section"""

    bl_idname = "ui.toggle_visibility"
    bl_label = "Toggle Visibility"

    section: bpy.props.StringProperty()

    def execute(self, context):
        # Toggle the visibility state
        visibility_states[self.section] = not visibility_states.get(self.section, False)
        context.area.tag_redraw()  # Force redraw of the UI
        return {"FINISHED"}


def collapsable_node_section(layout, node=None):
    if node is None:
        return None
    global visibility_states
    visible = visibility_states.get(node.name, False)

    row = layout.row()
    row.scale_y = 0.75
    icon = "DOWNARROW_HLT" if visible else "RIGHTARROW_THIN"
    op = row.operator("ui.toggle_visibility", text="", icon=icon, emboss=False)
    op.section = node.name

    if node.label:
        row.label(text=node.label, icon="OUTPUT")
    else:
        row.label(text=node.name, icon="OUTPUT")

    if node is None:
        return layout

    row.operator(
        ToggleNodeMuteOperator.bl_idname,
        text="",
        icon="RESTRICT_RENDER_ON" if node.mute else "RESTRICT_RENDER_OFF",
    ).node_name = node.name

    row.operator(
        SelectNodeOperator.bl_idname, text="", icon="RESTRICT_SELECT_OFF"
    ).node_name = node.name

    if visible:
        return layout
    return None


def collapsable_scene_section(layout, scene=None):
    if scene is None:
        return None
    global visibility_states
    visible = visibility_states.get(scene.name, False)

    row = layout.row()
    row.scale_y = 0.75
    icon = "DOWNARROW_HLT" if visible else "RIGHTARROW_THIN"
    op = row.operator("ui.toggle_visibility", text="", icon=icon, emboss=False)
    op.section = scene.name

    row.label(text=scene.name, icon="SCENE_DATA")

    # row.operator(
    #     SelectNodeOperator.bl_idname, text="", icon="RESTRICT_SELECT_OFF"
    # ).node_name = node.name

    if visible:
        return layout
    return None


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


class ToggleNodeMuteOperator(bpy.types.Operator):
    bl_idname = "scene.toggle_node_mute"
    bl_label = "Toggle Node Mute"
    node_name: bpy.props.StringProperty()

    def execute(self, context):
        node = context.scene.node_tree.nodes.get(self.node_name)
        node.mute = not node.mute
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


def setup_base_scene_panel(layout, current_scene):
    """Sets up the initial UI elements like checking if nodes are enabled and displaying basic scene information."""
    if (current_scene.node_tree is None) or (not current_scene.use_nodes):
        row = layout.row()
        row.label(text=current_scene.name, icon="SCENE_DATA")
        row.prop(current_scene, "use_nodes", text="Use Nodes")
        row.enabled = True
        row = layout.row()
        row.label(text="Compositing Disabled, only using current scene.")
        return False
    return True


def gather_render_nodes(current_scene):
    """Extracts render layer nodes from the current scene's node tree."""
    return set(
        [node for node in current_scene.node_tree.nodes if node.type == "R_LAYERS"]
    )


def build_scenes_info(render_nodes):
    """Organizes nodes and scenes information based on their relationships to scenes and view layers."""
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
                "current_scene": scene == bpy.context.scene,
            }
        scenes_info[scene.name] = render_layers_info
    return scenes_info


def build_scene_ui(layout, scene_name, scenes_info, current_scene):
    """Creates UI elements for each scene and their render layers dynamically."""
    scene = bpy.data.scenes[scene_name]

    box = layout.box()

    scene_section = collapsable_scene_section(box, scene)

    if scene_section:
        build_layer_ui(scene_section, scene, scenes_info[scene_name], current_scene)


def build_layer_ui(box, scene, scene_info, current_scene):
    """Creates UI elements for each render layer within a scene."""
    table = BlenderUITable(
        box,
        ["Render Layer", "Status", ""],
        header_icons=["RENDERLAYERS", "INFO", "NONE"],
        column_widths=[None, None, 0.1],
    )

    for rl_name, layer_info in scene_info.items():
        all_rl_nodes = layer_info["nodes"]
        rl_majority_state = (
            all([node.mute for node in all_rl_nodes])
            if all_rl_nodes
            else not scene.view_layers.get(rl_name).use
        )

        padding = " " * 2

        if scene != current_scene:
            if not all_rl_nodes:
                continue

        table.add_row(
            [
                {"label": f"{padding}{rl_name}"},
                # {"data": layer_info, "path": "nodes"},
                {
                    "label": (
                        "Not used in Compositor!"
                        if not all_rl_nodes
                        else "Used in Compositor!"
                    )
                },
                {
                    "operator": ToggleSceneNodesOperator.bl_idname,
                    "data": scene,
                    "path": "use_nodes",
                    "operator_text": "",
                    "op_props": {
                        "scene_name": scene.name,
                        "rl_name": rl_name,
                        "new_state": not rl_majority_state,
                        "current_scene": layer_info["current_scene"],
                    },
                    "scale_x": 1.0,
                },
            ],
            icons=[
                "NONE",
                "CHECKMARK" if all_rl_nodes else "ERROR",
                "RESTRICT_RENDER_ON" if rl_majority_state else "RESTRICT_RENDER_OFF",
            ],
        )


def scene_panel(layout):
    """Main function that combines all the modular pieces into the full panel UI."""
    current_scene = bpy.context.scene
    if not setup_base_scene_panel(layout, current_scene):
        return
    render_nodes = gather_render_nodes(current_scene)
    scenes_info = build_scenes_info(render_nodes)

    col = layout.column(align=True)

    for scene_name in scenes_info:
        build_scene_ui(col, scene_name, scenes_info, current_scene)


def render_output_panel(layout):
    scene = bpy.context.scene

    check_and_display_errors(layout, scene)

    if scene.node_tree is None:
        return

    column = layout.column(align=True)

    display_composite_node_info(column, scene)
    layer_paths, file_paths = get_file_paths_from_all_nodes(scene)
    display_file_output_info(column, scene, layer_paths, file_paths)


def check_and_display_errors(layout, scene):
    if not scene.use_nodes:
        row = layout.row()
        row.label(text="Use Nodes must be enabled:", icon="ERROR")
        row.prop(scene, "use_nodes", text="Use Nodes")

    if not scene.render.use_compositing:
        row = layout.row()
        row.label(text="Use Compositing must be enabled:", icon="ERROR")
        row.prop(scene.render, "use_compositing", text="Use Compositing")


class BlenderUITable:
    def __init__(
        self,
        layout,
        headers,
        header_icons=None,
        row_scale=0.8,
        header_scale=0.5,
        column_widths=None,
    ):
        self.layout = layout
        self.headers = headers
        self.header_icons = header_icons or ["NONE"] * len(headers)
        self.row_scale = row_scale
        self.header_scale = header_scale
        self.column_widths = column_widths or [1.0] * len(
            headers
        )  # Default to equal width scaling
        self.create_headers()
        self.parent_col = layout.column(align=True)

    def create_headers(self):
        row = self.layout.row(align=True)  # Create a single row to contain all columns
        row.scale_y = self.header_scale  # Apply scaling to the entire row if needed

        # Creating a column for each header and setting up labels within each
        for header, icon, scale_x in zip(
            self.headers, self.header_icons, self.column_widths
        ):
            col = row.column(
                align=True
            )  # Create a new column in the row for each header
            if scale_x:
                col.scale_x = (
                    scale_x  # Apply horizontal scaling from the column_widths list
                )
            box = col.box()  # Create a box in the column
            box.label(text=header, icon=icon)  # Add a label to the box

    def add_row(self, properties, icons=None):
        row = self.parent_col.row(align=True)
        icons = icons or ["NONE"] * len(properties)
        row.scale_y = self.row_scale  # Apply vertical scaling to the entire row

        # Creating each column in the row
        for prop, icon, scale_x in zip(properties, icons, self.column_widths):
            col = row.column(align=True)
            prop_scale_x = prop.get("scale_x", None)
            if prop_scale_x:
                scale_x = prop_scale_x

            if scale_x:
                col.scale_x = scale_x  # Apply the same horizontal scaling as in headers
            col.enabled = prop.get("enabled", True)

            if "label" in prop:
                col.label(text=prop["label"], icon=icon)
            elif "operator" in prop:
                op = col.operator(
                    prop["operator"], text=prop.get("operator_text", ""), icon=icon
                )
                for key, value in prop["op_props"].items():
                    setattr(op, key, value)
            else:
                col.prop(prop["data"], prop["path"], text="", icon=icon)


def display_composite_node_info(layout, scene):
    composite_nodes = [
        node for node in scene.node_tree.nodes if node.type == "COMPOSITE"
    ]

    if len(composite_nodes) == 0:
        composite_node = None
        return
    else:
        composite_node = composite_nodes[0]

    box = layout.box()
    node_section = collapsable_node_section(box, composite_node)
    if node_section is None:
        return

    file_ext = IMAGE_TYPE_TO_EXTENSION.get(
        scene.render.image_settings.file_format, "unknown"
    )
    row = node_section.row(align=True)
    row.label(text=f"/{str(scene.frame_current).zfill(4)}.{file_ext}", icon="URL")


def get_file_paths_from_all_nodes(scene):
    layer_paths = []
    file_paths = []

    for node in scene.node_tree.nodes:
        if node.type == "OUTPUT_FILE":
            layer_paths, file_paths = get_file_paths_from_slots(
                node, scene, layer_paths, file_paths
            )

    return layer_paths, file_paths


def display_file_output_info(layout, scene, layer_paths, file_paths):
    for node in scene.node_tree.nodes:
        if node.type == "OUTPUT_FILE":
            box = layout.box()
            node_section = collapsable_node_section(box, node)
            if node_section is None:
                continue
            display_file_slots(node_section, node, scene, layer_paths, file_paths)


def get_file_paths_from_slots(node, scene, layer_paths, file_paths):
    IMAGE_TYPE_TO_EXTENSION = {
        "JPEG": "jpg",
        "PNG": "png",
        "OPEN_EXR_MULTILAYER": "exr",
    }  # Dummy extension map

    file_format = node.format.file_format
    slots = (
        node.file_slots if file_format != "OPEN_EXR_MULTILAYER" else node.layer_slots
    )

    new_file_paths = []

    for slot in slots:
        file_ext = IMAGE_TYPE_TO_EXTENSION.get(file_format, "unknown")
        if file_format != "OPEN_EXR_MULTILAYER":
            file_path = f"/{slot.path}/{str(scene.frame_current).zfill(4)}.{file_ext}"
            new_file_paths.append(file_path)
            final_path = file_path
        else:
            slot_name = slot.name
            file_path = f"/{node.octa_node_properties.multilayer_directory}/{str(scene.frame_current).zfill(4)}.exr"
            new_file_paths.append(file_path)
            final_path = file_path + f"/{slot_name}"

        layer_paths.append(final_path)

    new_file_paths = list(set(new_file_paths))
    file_paths.extend(new_file_paths)

    return layer_paths, file_paths


def display_file_slots(node_box, node, scene, layer_paths, file_paths):
    IMAGE_TYPE_TO_EXTENSION = {
        "JPEG": "jpg",
        "PNG": "png",
        "OPEN_EXR_MULTILAYER": "exr",
    }  # Dummy extension map

    file_format = node.format.file_format
    slots = (
        node.file_slots if file_format != "OPEN_EXR_MULTILAYER" else node.layer_slots
    )

    node_has_layer_overlaps = False
    node_has_file_overlaps = False

    for slot in slots:
        file_ext = IMAGE_TYPE_TO_EXTENSION.get(file_format, "unknown")
        if file_format != "OPEN_EXR_MULTILAYER":
            file_path = f"/{slot.path}/{str(scene.frame_current).zfill(4)}.{file_ext}"
            if file_paths.count(file_path) > 1:
                node_has_file_overlaps = True
            final_path = file_path
        else:
            slot_name = slot.name
            file_path = f"/{node.octa_node_properties.multilayer_directory}/{str(scene.frame_current).zfill(4)}.exr"
            if file_paths.count(file_path) > 1:
                node_has_file_overlaps = True
            final_path = file_path + f"/{slot_name}"

        if layer_paths.count(final_path) > 1:
            node_has_layer_overlaps = True

    if node_box is None:
        return layer_paths

    if file_format == "OPEN_EXR_MULTILAYER":
        # if node_has_file_overlaps:
        #     row = node_box.row()
        #     row.label(
        #         text="Multilayer directory name conflicts with other nodes!",
        #     )
        #     row.enabled = False

        row = node_box.row()
        col = row.column(align=True)
        col.label(text="Multilayer Directory Name:")
        col = row.column(align=True)
        icon = "ERROR" if node_has_file_overlaps else "NONE"
        col.prop(node.octa_node_properties, "multilayer_directory", text="", icon=icon)

    headers = [
        "File Path" if file_format == "OPEN_EXR_MULTILAYER" else "Base Path",
        "Layer Name" if file_format == "OPEN_EXR_MULTILAYER" else "File Path",
    ]

    header_icons = ["FILE_FOLDER", "RENDERLAYERS"]

    if node_has_layer_overlaps or node_has_file_overlaps:
        headers.append("Warnings")
        header_icons.append("ERROR")

    table = BlenderUITable(
        node_box,
        headers,
        header_icons=header_icons,
    )

    padding = " " * 2

    for slot in slots:
        file_ext = IMAGE_TYPE_TO_EXTENSION.get(file_format, "unknown")
        if file_format != "OPEN_EXR_MULTILAYER":
            file_path = f"/{slot.path}/{str(scene.frame_current).zfill(4)}.{file_ext}"
            final_path = file_path
        else:
            slot_name = slot.name
            file_path = f"/{node.octa_node_properties.multilayer_directory}/{str(scene.frame_current).zfill(4)}.exr"
            final_path = file_path + f"/{slot_name}"

        row = [
            {"label": f"{padding}{file_path}"},
            {
                "data": slot,
                "path": "path" if file_format != "OPEN_EXR_MULTILAYER" else "name",
            },
        ]

        if node_has_layer_overlaps or node_has_file_overlaps:
            row.append(
                {
                    "label": (
                        "Overwrite detected!"
                        if (layer_paths.count(final_path) > 1 or node_has_file_overlaps)
                        else ""
                    ),
                    "enabled": False,
                }
            )

        table.add_row(row)

    return layer_paths


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


def use_nodes_suggestion(context, layout):
    sug_box = layout.box()
    row = sug_box.row()
    row.label(text="Use Nodes Disabled!", icon="ERROR")
    row = sug_box.row()
    row.label(text="To use output paths Use Nodes must be enabled.")
    row = sug_box.row()
    row.prop(context.scene, "use_nodes", text="Use Nodes")


def use_compositing_suggestion(context, layout):
    sug_box = layout.box()
    row = sug_box.row()
    row.label(text="Use Compositing Disabled!", icon="ERROR")
    row = sug_box.row()
    row.label(text="To use output paths Use Compositing must be enabled.")
    row = sug_box.row()
    row.prop(context.scene.render, "use_compositing", text="Use Compositing")


def suggestion_draw(context, layout, suggestion_count=0, draw=True):
    if not context.scene:
        return suggestion_count
    if context.scene.node_tree:
        denoise_nodes = [
            node for node in context.scene.node_tree.nodes if node.type == "DENOISE"
        ]
        if len(denoise_nodes) > 0:
            if draw:
                denoise_suggestion(layout, denoise_nodes)
            suggestion_count += 1
    if not context.scene.use_nodes:
        if draw:
            use_nodes_suggestion(context, layout)
        suggestion_count += 1
    if not context.scene.render.use_compositing:
        if draw:
            use_compositing_suggestion(context, layout)
        suggestion_count += 1
    return suggestion_count


def content_manager(layout, context):
    properties = context.scene.octa_properties
    column = layout.column(align=True)
    box = column.box()
    box.label(text="Only render what you want:", icon="RESTRICT_RENDER_OFF")

    scene_vis_box = section(
        column, properties, "scene_visibility_visible", "Scene Rendering"
    )

    if scene_vis_box is not None:
        scene_panel(scene_vis_box)

    column = layout.column(align=True)
    box = column.box()
    box.label(text="Choose what you want to output:", icon="OUTPUT")

    section_box = section(
        column, properties, "render_output_path_visible", "Render Output"
    )

    if section_box is not None:
        render_output_panel(section_box)


class OctaPanel(Panel):
    bl_idname = "SCENE_PT_octa_panel"
    bl_label = "Octa Render"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        layout = self.layout
        icon_manager = IconManager()
        layout.label(text="", icon_value=icon_manager.icons["custom_icon"].icon_id)

    def draw(self, context):
        properties = context.scene.octa_properties
        scene = context.scene
        layout = self.layout

        box = layout.box()
        box.use_property_split = True
        box.use_property_decorate = False
        box.prop(properties, "job_name")
        box.prop(properties, "octa_farm_config")
        box.prop(properties, "render_format")

        box = layout.box()
        box.use_property_split = True
        box.use_property_decorate = False

        row = box.row()
        row.prop(properties, "render_type", expand=True)

        row = box.row()
        row.prop(
            properties,
            "match_scene",
            text=f"Match Scene {'Frame' if properties.render_type == 'IMAGE' else 'Frame Range'}",
        )

        col = box.column(align=True)

        if properties.render_type == "ANIMATION":
            fr_enabled = not properties.match_scene

            row = col.row()
            row.prop(
                scene if properties.match_scene else properties,
                "frame_start",
                text="Frame Start",
            )
            row.enabled = fr_enabled
            row = col.row()
            row.prop(
                scene if properties.match_scene else properties, "frame_end", text="End"
            )

            row.enabled = fr_enabled
            row = col.row()
            row.prop(
                properties,
                "frame_step",
                text="Step",
            )

            row.enabled = True
        else:
            col.prop(
                scene if properties.match_scene else properties,
                "frame_current",
                text="Frame",
            )
        if properties.render_type == "ANIMATION":
            row = box.row()
            if properties.frame_step == 1:
                row.prop(properties, "batch_size")
            else:
                row.prop(properties, "batch_size_tmp")
                row.enabled = False
                row.prop(properties, "batch_size_warning", text="", icon="INFO")

        icons = IconManager().icons
        col = box.column(align=True)

        is_running = SubmitJobOperator.get_running()

        if is_running:
            row = col.row()
            row.progress(
                text=SubmitJobOperator.get_progress_name(),
                factor=SubmitJobOperator.get_progress(),
            )

        debug_zip = False
        addon_prefs = get_preferences()
        if addon_prefs.debug_options:
            row = col.row()
            row.prop(properties, "debug_zip")
            debug_zip = properties.debug_zip

        row = col.row()
        submit_op = row.operator(
            SubmitJobOperator.bl_idname,
            icon_value=icons["custom_icon"].icon_id,
        )

        submit_op.debug_zip = debug_zip

        if is_running:
            row.enabled = False

        box = section(
            layout, properties, "advanced_section_visible", "Advanced Options"
        )
        if box is not None:
            row = box.row()
            col = row.column()
            col.label(text="Thumbnail Size:")
            col.scale_x = 0.6
            col = row.column()
            col.prop(properties, "max_thumbnail_size", text="")
            col.scale_x = 0.4

            row = box.row()
            col = row.column()
            col.label(text="Blender Version:")
            col.scale_x = 0.6
            col = row.column()
            col.prop(properties, "blender_version", text="")
            col.scale_x = 0.4

        content_manager_section = section(
            layout, properties, "content_manager_visible", "Content Manager"
        )

        if content_manager_section is not None:
            content_manager(content_manager_section, context)

            # box = section(layout, properties, "download_section_visible", "Download")
            # if box is not None:
            #     box.use_property_split = True
            #     box.use_property_decorate = False
            #     box.prop(properties, "dl_job_id")

            #     row = box.row()
            #     row.prop(properties, "dl_output_path")

            #     row = box.row()
            #     row.prop(properties, "dl_threads")

            #     row = box.row()
            #     row.operator(DownloadJobOperator.bl_idname, icon="SORT_ASC")

        suggestion_count = 0
        suggestion_count = suggestion_draw(context, box, suggestion_count, False)

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
