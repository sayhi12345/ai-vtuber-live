from app.characters import load_default_registry


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


def test_dengjie_has_her_own_persona_and_live2d_avatar() -> None:
    registry = load_default_registry()
    summaries = {
        character["id"]: character
        for character in registry.list_summaries()
    }

    assert summaries["dengjie"] == {
        "id": "dengjie",
        "name": "鄧捷",
        "short_description": "溫柔細膩的陪伴型互動 AI 主播",
        "avatar": "/live2d/haru/dengjie.model3.json",
    }

    prompt = registry.get("dengjie").to_system_prompt()
    assert "星座" in prompt
    assert "MBTI" in prompt
    assert "先承接情緒" in prompt
