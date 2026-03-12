from app.providers.openai_provider import _normalize_openai_urls


def test_normalize_openai_urls_adds_v1_for_langchain_api_base():
    http_base_url, api_base_url = _normalize_openai_urls("https://api.openai.com")

    assert http_base_url == "https://api.openai.com"
    assert api_base_url == "https://api.openai.com/v1"


def test_normalize_openai_urls_preserves_existing_v1_path():
    http_base_url, api_base_url = _normalize_openai_urls("https://proxy.example.com/openai/v1")

    assert http_base_url == "https://proxy.example.com/openai"
    assert api_base_url == "https://proxy.example.com/openai/v1"
