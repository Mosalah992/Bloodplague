from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


FRAME_W = 16
FRAME_H = 32
FRAME_COLS = 7
FRAME_ROWS = 3
FRAME_BOTTOM_PAD = 2
TARGET_MAX_W = 14
TARGET_MAX_H = 28
PREVIEW_COLUMNS = 2
PREVIEW_PADDING = 6

ROOT = Path(__file__).resolve().parents[1]
SPRITES_DIR = ROOT / "Sprites"
OUTPUT_DIR = ROOT / "frontend" / "public" / "pixel-assets" / "characters"
PREVIEW_PATH = SPRITES_DIR / "custom-character-preview.png"


@dataclass(frozen=True)
class CharacterBuildSpec:
    zip_name: str
    output_name: str


CHARACTER_SPECS = [
    CharacterBuildSpec("SHADOW.zip", "shadow.png"),
    CharacterBuildSpec("PHANTOM.zip", "phantom.png"),
    CharacterBuildSpec("ORACLE.zip", "oracle.png"),
    CharacterBuildSpec("CIPHER.zip", "cipher.png"),
    CharacterBuildSpec("SENTINEL.zip", "sentinel.png"),
]

ROW_WALK_ROTATIONS = {
    "down": ("south-west", "south", "south-east"),
    "up": ("north-west", "north", "north-east"),
    "right": ("south-east", "east", "north-east"),
}

ROW_CARDINAL_ROTATION = {
    "down": "south",
    "up": "north",
    "right": "east",
}


def load_zip_json(zip_file: zipfile.ZipFile, member: str) -> dict:
    with zip_file.open(member) as handle:
        return json.load(handle)


def load_zip_image(zip_file: zipfile.ZipFile, member: str) -> Image.Image:
    with zip_file.open(member) as handle:
        data = handle.read()
    return Image.open(io.BytesIO(data)).convert("RGBA")


def trim_image(image: Image.Image) -> Image.Image:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    return image.crop(bbox)


def scale_to_fit(image: Image.Image) -> Image.Image:
    width, height = image.size
    scale = min(TARGET_MAX_W / width, TARGET_MAX_H / height)
    scaled = (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    return image.resize(scaled, Image.Resampling.NEAREST)


def place_in_frame(image: Image.Image, x_shift: int = 0, y_shift: int = 0) -> Image.Image:
    frame = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    x = (FRAME_W - image.width) // 2 + x_shift
    y = FRAME_H - FRAME_BOTTOM_PAD - image.height + y_shift
    x = max(min(x, FRAME_W - image.width), 0)
    y = max(min(y, FRAME_H - image.height), 0)
    frame.alpha_composite(image, (x, y))
    return frame


def prepare_frame(source: Image.Image, x_shift: int = 0, y_shift: int = 0) -> Image.Image:
    return place_in_frame(scale_to_fit(trim_image(source)), x_shift=x_shift, y_shift=y_shift)


def build_direction_frames(
    direction: str,
    rotations: dict[str, Image.Image],
    animation_frames: list[Image.Image],
) -> list[Image.Image]:
    walk_a = prepare_frame(rotations[ROW_WALK_ROTATIONS[direction][0]])
    walk_b = prepare_frame(rotations[ROW_WALK_ROTATIONS[direction][1]])
    walk_c = prepare_frame(rotations[ROW_WALK_ROTATIONS[direction][2]])

    cardinal = rotations[ROW_CARDINAL_ROTATION[direction]]
    typing_a = prepare_frame(cardinal)
    typing_b = prepare_frame(cardinal, y_shift=1)
    reading_a = prepare_frame(cardinal, y_shift=-1)
    reading_b = prepare_frame(cardinal)

    if animation_frames and direction == "down":
        prepared = [prepare_frame(frame) for frame in animation_frames]
        if len(prepared) >= 6:
            walk_a, walk_b, walk_c = prepared[0], prepared[2], prepared[4]
            typing_a, typing_b = prepared[1], prepared[3]
            reading_a, reading_b = prepared[2], prepared[5]

    return [walk_a, walk_b, walk_c, typing_a, typing_b, reading_a, reading_b]


def build_character_sheet(spec: CharacterBuildSpec) -> tuple[Path, Image.Image]:
    zip_path = SPRITES_DIR / spec.zip_name
    if not zip_path.exists():
        raise FileNotFoundError(f"missing source archive: {zip_path}")

    with zipfile.ZipFile(zip_path) as archive:
        metadata = load_zip_json(archive, "metadata.json")
        rotation_paths = metadata["frames"]["rotations"]
        rotations = {
            key: load_zip_image(archive, path)
            for key, path in rotation_paths.items()
        }

        animations = metadata["frames"].get("animations", {})
        down_animation_frames: list[Image.Image] = []
        if animations:
            first_animation = next(iter(animations.values()))
            south_frames = first_animation.get("south", [])
            down_animation_frames = [load_zip_image(archive, path) for path in south_frames]

    sheet = Image.new("RGBA", (FRAME_W * FRAME_COLS, FRAME_H * FRAME_ROWS), (0, 0, 0, 0))
    for row_index, direction in enumerate(("down", "up", "right")):
        frames = build_direction_frames(direction, rotations, down_animation_frames)
        for col_index, frame in enumerate(frames):
            sheet.alpha_composite(frame, (col_index * FRAME_W, row_index * FRAME_H))

    destination = OUTPUT_DIR / spec.output_name
    sheet.save(destination)
    return destination, sheet


def validate_sheet(path: Path) -> None:
    image = Image.open(path).convert("RGBA")
    if image.size != (FRAME_W * FRAME_COLS, FRAME_H * FRAME_ROWS):
        raise ValueError(f"{path.name} has wrong size {image.size}")

    for row in range(FRAME_ROWS):
        for col in range(FRAME_COLS):
            frame = image.crop(
                (
                    col * FRAME_W,
                    row * FRAME_H,
                    (col + 1) * FRAME_W,
                    (row + 1) * FRAME_H,
                )
            )
            if frame.getchannel("A").getbbox() is None:
                raise ValueError(f"{path.name} has an empty frame at row {row} col {col}")


def build_preview(entries: list[tuple[str, Image.Image]]) -> None:
    if not entries:
        return

    rows = (len(entries) + PREVIEW_COLUMNS - 1) // PREVIEW_COLUMNS
    preview_width = PREVIEW_COLUMNS * FRAME_W * FRAME_COLS + PREVIEW_PADDING * (PREVIEW_COLUMNS + 1)
    preview_height = rows * FRAME_H * FRAME_ROWS + PREVIEW_PADDING * (rows + 1)
    preview = Image.new("RGBA", (preview_width, preview_height), (7, 10, 16, 255))

    for index, (_, sheet) in enumerate(entries):
        grid_x = index % PREVIEW_COLUMNS
        grid_y = index // PREVIEW_COLUMNS
        x = PREVIEW_PADDING + grid_x * (FRAME_W * FRAME_COLS + PREVIEW_PADDING)
        y = PREVIEW_PADDING + grid_y * (FRAME_H * FRAME_ROWS + PREVIEW_PADDING)
        preview.alpha_composite(sheet, (x, y))

    preview.save(PREVIEW_PATH)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    built: list[tuple[str, Image.Image]] = []
    skipped: list[str] = []

    for spec in CHARACTER_SPECS:
        try:
            path, sheet = build_character_sheet(spec)
        except FileNotFoundError:
            skipped.append(spec.zip_name)
            continue
        validate_sheet(path)
        built.append((path.name, sheet))
        print(f"built {path.name}")

    build_preview(built)
    print(f"preview {PREVIEW_PATH}")
    if skipped:
        print("skipped " + ", ".join(skipped))


if __name__ == "__main__":
    main()
