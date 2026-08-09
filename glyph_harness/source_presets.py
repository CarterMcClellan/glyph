"""Bundled source images shown on Glyph's home screen."""

SOURCE_PRESETS = [
    {
        "id": "voxel-apprentice",
        "label": "Voxel Apprentice",
        "description": "Chunky 3D style",
        "filename": "voxel-apprentice.png",
        "prompt": "A single full-body voxel character with a clean silhouette and separated limbs",
        "recommended_aspect_ratio": "1:1",
    },
    {
        "id": "illustrated-apprentice",
        "label": "Storybook Apprentice",
        "description": "Clean illustrated style",
        "filename": "illustrated-apprentice.png",
        "prompt": "A single full-body illustrated character with a clean silhouette and separated limbs",
        "recommended_aspect_ratio": "2:3",
    },
    {
        "id": "voxel-elder",
        "label": "Voxel Elder",
        "description": "Tall block-built style",
        "filename": "voxel-elder.png",
        "prompt": "A single full-body voxel elder with a clean silhouette and visible staff",
        "recommended_aspect_ratio": "2:3",
    },
    {
        "id": "arcane-mage",
        "label": "Arcane Mage",
        "description": "Detailed fantasy style",
        "filename": "arcane-mage.png",
        "prompt": "A single full-body fantasy character with a clean silhouette and visible accessories",
        "recommended_aspect_ratio": "2:3",
    },
]


def public_source_presets() -> list[dict]:
    return [
        {
            **preset,
            "asset": f"../assets/source-presets/{preset['filename']}",
        }
        for preset in SOURCE_PRESETS
    ]


def source_preset(preset_id: str) -> dict:
    match = next((preset for preset in SOURCE_PRESETS if preset["id"] == preset_id), None)
    if not match:
        raise ValueError("Unknown source preset")
    return match
