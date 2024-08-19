import bpy.utils.previews
import os


class IconManager:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(IconManager, cls).__new__(cls)
            addon_directory = os.path.dirname(os.path.abspath(__file__))
            parent_directory = os.path.dirname(addon_directory)
            icons_directory = os.path.join(parent_directory, "icons")
            icon_path = os.path.join(icons_directory, "logo.png")
            cls._instance.icons = bpy.utils.previews.new()
            cls._instance.icons.load("custom_icon", icon_path, "IMAGE")
        return cls._instance

    @classmethod
    def unload_icons(cls):
        if cls._instance:
            bpy.utils.previews.remove(cls._instance.icons)
            cls._instance = None
