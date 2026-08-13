import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


def test_reference_texture_preserves_original_uv_alpha() -> None:
    texture_dir = (
        Path(__file__).parents[2]
        / "frontend/public/live2d/haru/haru_greeter_t03.2048"
    )
    original = Image.open(texture_dir / "texture_00.png")
    preview = Image.open(texture_dir / "texture_00_reference.png")

    assert preview.mode == "RGBA"
    assert preview.size == original.size
    assert preview.getchannel("A").tobytes() == original.getchannel("A").tobytes()


def test_face_v2_changes_only_face_uv_regions() -> None:
    texture_dir = (
        Path(__file__).parents[2]
        / "frontend/public/live2d/haru/haru_greeter_t03.2048"
    )
    v2_path = texture_dir / "texture_00_reference_face_v2.png"

    assert v2_path.exists()

    v1 = Image.open(texture_dir / "texture_00_reference.png").convert("RGBA")
    v2 = Image.open(v2_path)
    assert v2.mode == "RGBA"
    assert v2.size == v1.size

    face_regions = [
        (1170, 20, 1620, 560),
        (1150, 800, 1500, 990),
        (1200, 1040, 1710, 1360),
        (1620, 980, 1710, 1120),
    ]
    difference = ImageChops.difference(v1, v2)
    allowed = Image.new("L", v1.size)
    draw = ImageDraw.Draw(allowed)
    for region in face_regions:
        draw.rectangle(region, fill=255)

    outside_difference = Image.composite(
        Image.new("RGBA", v1.size), difference, allowed
    )
    assert outside_difference.getbbox() is None
    transparent = v2.getchannel("A").point(lambda alpha: 255 if alpha == 0 else 0)
    transparent_rgb_difference = Image.composite(
        ImageChops.difference(v1.convert("RGB"), v2.convert("RGB")),
        Image.new("RGB", v1.size),
        transparent,
    )
    assert transparent_rgb_difference.getbbox() is None
    for region in face_regions[:3]:
        assert difference.crop(region).getbbox() is not None


def test_texture_01_reference_changes_only_ponytail() -> None:
    texture_dir = (
        Path(__file__).parents[2]
        / "frontend/public/live2d/haru/haru_greeter_t03.2048"
    )
    original = Image.open(texture_dir / "texture_01.png").convert("RGBA")
    reference = Image.open(texture_dir / "texture_01_reference.png")

    assert reference.mode == "RGBA"
    assert reference.size == original.size
    assert reference.getchannel("A").tobytes() == original.getchannel("A").tobytes()

    ponytail_region = (1680, 1550, 2030, 2040)
    difference = ImageChops.difference(original, reference)
    allowed = Image.new("L", original.size)
    ImageDraw.Draw(allowed).rectangle(ponytail_region, fill=255)
    outside_difference = Image.composite(
        Image.new("RGBA", original.size), difference, allowed
    )
    assert outside_difference.getbbox() is None
    assert difference.crop(ponytail_region).convert("RGB").getbbox() is not None


def test_striped_outfit_preserves_uv_skirt_and_ponytail() -> None:
    texture_dir = (
        Path(__file__).parents[2]
        / "frontend/public/live2d/haru/haru_greeter_t03.2048"
    )
    reference = Image.open(texture_dir / "texture_01_reference.png").convert("RGBA")
    outfit_path = texture_dir / "texture_01_reference_striped_outfit.png"

    assert outfit_path.exists()

    outfit = Image.open(outfit_path)
    assert outfit.mode == "RGBA"
    assert outfit.size == reference.size
    assert outfit.getchannel("A").tobytes() == reference.getchannel("A").tobytes()
    skirt = (0, 0, 930, 980)
    ponytail = (1680, 1550, 2030, 2040)
    torso = (40, 980, 720, 2040)
    assert ImageChops.difference(reference.crop(skirt), outfit.crop(skirt)).convert("RGB").getbbox() is None
    assert ImageChops.difference(reference.crop(ponytail), outfit.crop(ponytail)).convert("RGB").getbbox() is None
    assert ImageChops.difference(reference.crop(torso), outfit.crop(torso)).convert("RGB").getbbox() is not None


def test_rongrong_manifest_uses_independent_named_textures() -> None:
    haru_dir = Path(__file__).parents[2] / "frontend/public/live2d/haru"
    texture_dir = haru_dir / "haru_greeter_t03.2048"
    manifest = json.loads((haru_dir / "rongrong.model3.json").read_text())

    assert manifest["FileReferences"]["Textures"] == [
        "haru_greeter_t03.2048/texture_00_rongrong.png",
        "haru_greeter_t03.2048/texture_01_rongrong.png",
    ]
    original_manifest = json.loads(
        (haru_dir / "haru_greeter_t03.model3.json").read_text()
    )
    assert original_manifest["FileReferences"]["Textures"] == [
        "haru_greeter_t03.2048/texture_00.png",
        "haru_greeter_t03.2048/texture_01.png",
    ]
    for source_name, rongrong_name in [
        ("texture_00_reference_face_v2.png", "texture_00_rongrong.png"),
        ("texture_01_reference_striped_outfit.png", "texture_01_rongrong.png"),
    ]:
        source = Image.open(texture_dir / source_name).convert("RGBA")
        rongrong = Image.open(texture_dir / rongrong_name)
        assert rongrong.mode == "RGBA"
        assert rongrong.size == (2048, 2048)
        assert rongrong.getchannel("A").tobytes() == source.getchannel("A").tobytes()


def test_dengjie_short_hair_preview_hides_only_the_ponytail() -> None:
    haru_dir = Path(__file__).parents[2] / "frontend/public/live2d/haru"
    texture_dir = haru_dir / "haru_greeter_t03.2048"
    manifest = json.loads(
        (haru_dir / "dengjie_short_preview.model3.json").read_text()
    )

    assert manifest["FileReferences"]["Textures"] == [
        "haru_greeter_t03.2048/texture_00_dengjie_short.png",
        "haru_greeter_t03.2048/texture_01_dengjie_short.png",
    ]

    face = Image.open(texture_dir / "texture_00_dengjie.png").convert("RGBA")
    short_face = Image.open(texture_dir / "texture_00_dengjie_short.png")
    assert short_face.mode == "RGBA"
    assert short_face.size == face.size
    assert short_face.getchannel("A").tobytes() == face.getchannel("A").tobytes()

    outfit = Image.open(texture_dir / "texture_01_dengjie.png").convert("RGBA")
    short_outfit = Image.open(texture_dir / "texture_01_dengjie_short.png")
    ponytail = (1680, 1550, 2030, 2040)
    assert short_outfit.mode == "RGBA"
    assert short_outfit.size == outfit.size
    assert short_outfit.crop(ponytail).getchannel("A").getbbox() is None

    outside_ponytail = Image.new("L", outfit.size, 255)
    ImageDraw.Draw(outside_ponytail).rectangle(ponytail, fill=0)
    difference = ImageChops.difference(outfit, short_outfit)
    outside_difference = Image.composite(
        difference, Image.new("RGBA", outfit.size), outside_ponytail
    )
    assert outside_difference.getbbox() is None
