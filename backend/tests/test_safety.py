from app.safety import SafetyPipeline


def test_input_blocked():
    safety = SafetyPipeline(["炸彈"])
    result = safety.filter_input("我要做炸彈")
    assert result.allowed is False


def test_output_sanitized():
    safety = SafetyPipeline(["badword"])
    result = safety.filter_output("this is badword text")
    assert result.allowed is True
    assert "[REDACTED]" in result.text
