import asyncio

from app.tarot import _load_card_reference_index, is_tarot_query, prepare_tarot_turn


def test_tarot_query_detection():
    assert is_tarot_query("幫我用塔羅看最近運勢")
    assert is_tarot_query("最近運勢如何")
    assert is_tarot_query("給我一個指引")
    assert not is_tarot_query("幫我寫一段 React component")


def test_card_reference_index_loads_known_cards():
    index = _load_card_reference_index()

    assert "愚者" in index
    assert "聖盃二" in index
    assert "關鍵詞" in index["愚者"]


def test_prepare_tarot_turn_uses_real_draw_script():
    system_prompt, messages = asyncio.run(
        prepare_tarot_turn(
            question="最近運勢如何",
            history=[{"role": "user", "content": "最近運勢如何"}],
            persona_prompt="你是一位 AI VTuber。",
        )
    )

    assert "塔羅解讀模式" in system_prompt
    assert len(messages) == 1
    content = messages[0]["content"]
    assert "系統已完成真實抽牌" in content
    assert "牌陣：三牌陣" in content
    assert "抽牌種子：" in content
    assert "本地牌義參考：" in content
