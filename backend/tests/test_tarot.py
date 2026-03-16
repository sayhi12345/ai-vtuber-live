import asyncio

from app.tarot import draw_tarot_cards, is_tarot_query


def test_tarot_query_detection():
    assert is_tarot_query("幫我用塔羅看最近運勢")
    assert is_tarot_query("最近運勢如何")
    assert is_tarot_query("給我一個指引")
    assert not is_tarot_query("幫我寫一段 React component")


def test_draw_tarot_cards_returns_agent_payload():
    payload = asyncio.run(draw_tarot_cards(question="最近運勢如何"))

    assert payload["spread"] == "three"
    assert payload["spread_name"] == "三牌陣"
    assert isinstance(payload["seed"], int)
    assert payload["cards"]
    first_card = payload["cards"][0]
    assert {"position", "card", "orientation", "is_major"} <= set(first_card)
    assert payload["time_factor_label"]
