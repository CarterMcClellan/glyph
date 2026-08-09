bl_info = {
    "name": "Glyph",
    "author": "Carter McClellan",
    "version": (0, 1, 1),
    "blender": (5, 0, 0),
    "location": "3D Viewport > Sidebar > Glyph",
    "description": "Selection + language + image references with recoverable mesh previews",
    "category": "3D View",
}

try:
    import bpy
except ModuleNotFoundError:  # Allows protocol tests in ordinary Python.
    bpy = None

if bpy is not None:
    from . import operators, ui

    CLASSES = ui.CLASSES + operators.CLASSES

    def register():
        for cls in CLASSES:
            bpy.utils.register_class(cls)
        ui.register_scene_properties()

    def unregister():
        ui.unregister_scene_properties()
        for cls in reversed(CLASSES):
            bpy.utils.unregister_class(cls)
