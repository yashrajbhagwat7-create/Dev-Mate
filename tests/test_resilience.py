"""Unit tests for network resilience, retry with backoff, and local provider support."""

from unittest.mock import MagicMock, patch
import pytest
import requests
from devmate.providers import _request_with_retry, ProviderError, OpenRouterProvider


def test_retry_success_first_try():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    fn = MagicMock(return_value=mock_resp)

    res = _request_with_retry(fn, max_retries=3, initial_delay=0.001)
    assert res.status_code == 200
    assert fn.call_count == 1


def test_retry_on_429_then_succeeds():
    resp_429 = MagicMock()
    resp_429.status_code = 429

    resp_200 = MagicMock()
    resp_200.status_code = 200

    fn = MagicMock(side_effect=[resp_429, resp_200])

    res = _request_with_retry(fn, max_retries=3, initial_delay=0.001)
    assert res.status_code == 200
    assert fn.call_count == 2


def test_retry_on_503_then_succeeds():
    resp_503 = MagicMock()
    resp_503.status_code = 503

    resp_200 = MagicMock()
    resp_200.status_code = 200

    fn = MagicMock(side_effect=[resp_503, resp_200])

    res = _request_with_retry(fn, max_retries=3, initial_delay=0.001)
    assert res.status_code == 200
    assert fn.call_count == 2


def test_retry_on_connection_error_eventual_fail():
    fn = MagicMock(side_effect=requests.exceptions.ConnectionError("Network down"))

    with pytest.raises(requests.exceptions.ConnectionError):
        _request_with_retry(fn, max_retries=2, initial_delay=0.001)

    assert fn.call_count == 2


def test_openrouter_custom_base_url():
    p = OpenRouterProvider(api_key="sk-test", model="model-test", base_url="http://custom-host:8000/v1/")
    assert p.base_url == "http://custom-host:8000/v1"
