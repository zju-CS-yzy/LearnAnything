from types import SimpleNamespace

import requests

import core.vlm_client as vlm_module


def _configured_client(monkeypatch):
    monkeypatch.setattr(
        vlm_module,
        "get_vlm_config",
        lambda: SimpleNamespace(
            api_key="test-key",
            base_url="https://vlm.example/v1",
            model="test-vlm",
        ),
    )
    monkeypatch.setattr(vlm_module.time, "sleep", lambda _seconds: None)
    return vlm_module.VLMClient()


def test_vlm_uses_separate_connect_and_read_timeouts(monkeypatch):
    client = _configured_client(monkeypatch)
    calls = []

    class SuccessfulResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(*_args, **kwargs):
        calls.append(kwargs)
        return SuccessfulResponse()

    monkeypatch.setattr(vlm_module.requests, "post", fake_post)

    result = client._call_api([{"role": "user", "content": "test"}])

    assert result == "ok"
    assert calls[0]["timeout"] == (15, 180)


def test_vlm_timeout_only_retries_once(monkeypatch):
    client = _configured_client(monkeypatch)
    call_count = 0

    def always_timeout(*_args, **_kwargs):
        nonlocal call_count
        call_count += 1
        raise requests.exceptions.Timeout("slow response")

    monkeypatch.setattr(vlm_module.requests, "post", always_timeout)

    result = client._call_api([{"role": "user", "content": "test"}])

    assert result is None
    assert call_count == 2
