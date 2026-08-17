import json
import struct
from pathlib import Path

from app.characters import load_default_registry


ROOT = Path(__file__).parents[2]
HARU_DIR = ROOT / "frontend/public/live2d/haru"


def test_rongrong_has_her_own_live2d_avatar() -> None:
    summaries = {
        character["id"]: character
        for character in load_default_registry().list_summaries()
    }

    assert summaries["rongrong"] == {
        "id": "rongrong",
        "name": "容容",
        "short_description": "親切活潑的生活型直播主",
        "avatar": "/live2d/haru/rongrong.model3.json",
    }
    assert summaries["luna"]["avatar"] is None
    assert summaries["aria"]["avatar"] is None


def test_rongrong_manifest_uses_independent_rgba_textures() -> None:
    manifest = json.loads((HARU_DIR / "rongrong.model3.json").read_text())
    textures = manifest["FileReferences"]["Textures"]

    assert textures == [
        "haru_greeter_t05.2048/texture_00_rongrong.png",
        "haru_greeter_t05.2048/texture_01_rongrong.png",
    ]
    for texture in textures:
        data = (HARU_DIR / texture).read_bytes()
        width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        assert (width, height, bit_depth, color_type) == (2048, 2048, 8, 6)


def test_original_haru_manifest_keeps_original_textures() -> None:
    manifest = json.loads((HARU_DIR / "haru_greeter_t05.model3.json").read_text())

    assert manifest["FileReferences"]["Textures"] == [
        "haru_greeter_t05.2048/texture_00.png",
        "haru_greeter_t05.2048/texture_01.png",
    ]
