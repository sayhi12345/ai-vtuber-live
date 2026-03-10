from app.pipeline import SegmentAccumulator, detect_emotion


def test_segment_accumulator_splits_sentences():
    acc = SegmentAccumulator()
    result = acc.feed("你好！今天過得")
    assert result == ["你好！"]
    result2 = acc.feed("如何？")
    assert result2 == ["今天過得如何？"]
    assert acc.flush() == ""


def test_detect_emotion():
    assert detect_emotion("太好了！") == "happy"
    assert detect_emotion("我很難過") == "sad"
    assert detect_emotion("這讓我很生氣") == "angry"
    assert detect_emotion("真的假的？！") == "surprised"
    assert detect_emotion("這是一個敘述句") == "neutral"
