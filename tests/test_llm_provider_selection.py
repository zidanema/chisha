"""tests/test_llm_provider_selection.py — provider 路由逻辑 (D-047)."""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture
def _clean_env(monkeypatch):
    """清掉关键 env, 每个测试独立."""
    for k in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "CHISHA_LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    yield monkeypatch


@pytest.fixture(autouse=True)
def _reset_cli_cache():
    from chisha.llm_providers import claude_code_cli as cc
    cc.reset_cli_check_cache()
    yield
    cc.reset_cli_check_cache()


# ====================== _resolve_provider 优先级 ======================


def test_env_override_wins(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("CHISHA_LLM_PROVIDER", "openrouter")
    _clean_env.setenv("OPENROUTER_API_KEY", "sk-or")
    assert _resolve_provider({"provider": "anthropic"}) == "openrouter"


def test_invalid_env_raises(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("CHISHA_LLM_PROVIDER", "foo")
    with pytest.raises(ValueError, match="CHISHA_LLM_PROVIDER"):
        _resolve_provider(None)


def test_env_empty_string_treated_as_unset(_clean_env):
    """CHISHA_LLM_PROVIDER='' fallback 到 auto"""
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("CHISHA_LLM_PROVIDER", "")
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk")
    assert _resolve_provider(None) == "anthropic"


def test_env_whitespace_only_treated_as_unset(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("CHISHA_LLM_PROVIDER", "   ")
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk")
    assert _resolve_provider(None) == "anthropic"


def test_env_explicit_but_unavailable_raises(_clean_env):
    """显式选 openrouter 但没 OPENROUTER_API_KEY → RuntimeError"""
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("CHISHA_LLM_PROVIDER", "openrouter")
    with pytest.raises(RuntimeError, match="不可用"):
        _resolve_provider(None)


def test_profile_explicit(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("OPENROUTER_API_KEY", "sk-or")
    assert _resolve_provider({"provider": "openrouter"}) == "openrouter"


def test_profile_invalid_raises(_clean_env):
    from chisha.llm_client import _resolve_provider
    with pytest.raises(ValueError, match="profile.llm.provider"):
        _resolve_provider({"provider": "deepseek"})


def test_profile_explicit_but_unavailable_raises(_clean_env):
    """profile.llm.provider=anthropic 但无 ANTHROPIC_API_KEY → RuntimeError"""
    from chisha.llm_client import _resolve_provider
    with pytest.raises(RuntimeError, match="不可用"):
        _resolve_provider({"provider": "anthropic"})


def test_auto_anthropic_wins_when_key_present(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk-fake")
    assert _resolve_provider({"provider": "auto"}) == "anthropic"


def test_auto_falls_to_claude_code_cli_when_no_key(_clean_env):
    from chisha.llm_client import _resolve_provider
    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=True):
        assert _resolve_provider({"provider": "auto"}) == "claude_code_cli"


def test_auto_falls_to_openrouter_when_no_cli(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("OPENROUTER_API_KEY", "sk-or-fake")
    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=False):
        assert _resolve_provider({"provider": "auto"}) == "openrouter"


def test_auto_all_unavailable_raises(_clean_env):
    from chisha.llm_client import _resolve_provider
    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=False):
        with pytest.raises(RuntimeError, match="无可用 LLM provider"):
            _resolve_provider({"provider": "auto"})


def test_no_profile_treated_as_auto(_clean_env):
    from chisha.llm_client import _resolve_provider
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert _resolve_provider(None) == "anthropic"


# ====================== _resolve_model 优先级 ======================


def test_model_explicit_wins():
    from chisha.llm_client import _resolve_model
    profile = {"model": {"anthropic": "from-profile"}}
    assert _resolve_model("anthropic", "explicit", profile) == "explicit"


def test_model_from_profile():
    from chisha.llm_client import _resolve_model
    profile = {"model": {"anthropic": "from-profile"}}
    assert _resolve_model("anthropic", None, profile) == "from-profile"


def test_model_default_when_none():
    from chisha.llm_client import _resolve_model
    assert _resolve_model("anthropic", None, None) is None
    assert _resolve_model("anthropic", None, {}) is None


# ====================== call_text 路由 ======================


def test_call_text_routes_to_anthropic(_clean_env):
    """D-047 接口: call_text 现在返回 dict, provider call 也返回 dict."""
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk-fake")
    from chisha import llm_client
    fake_dict = {"type": "text", "content": "ANTHROPIC_REPLY",
                 "stop_reason": "end_turn", "usage": {},
                 "model": "x", "raw_text": "ANTHROPIC_REPLY"}
    with patch("chisha.llm_providers.anthropic_api.call",
                return_value=fake_dict) as m:
        out = llm_client.call_text("p", system="s")
        assert out == fake_dict
        assert m.call_count == 1


def test_call_text_routes_to_claude_code_cli(_clean_env):
    """D-047: claude_code_cli 也返回 dict."""
    from chisha import llm_client
    fake_dict = {"type": "text", "content": "CC_REPLY",
                 "stop_reason": "stop", "usage": {},
                 "model": "sonnet", "raw_text": "CC_REPLY"}
    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=True), \
         patch("chisha.llm_providers.claude_code_cli.call",
                return_value=fake_dict) as m:
        out = llm_client.call_text(
            "p", system="s", profile_llm={"provider": "auto"},
        )
        assert out == fake_dict
        assert m.call_count == 1


_STUB_DICT = {"type": "text", "content": "x", "stop_reason": "end_turn",
              "usage": {}, "model": "x", "raw_text": "x"}


def test_call_text_passes_model_kwarg(_clean_env):
    """显式 model 参数透传到 provider"""
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk")
    from chisha import llm_client
    with patch("chisha.llm_providers.anthropic_api.call") as m:
        m.return_value = _STUB_DICT
        llm_client.call_text(
            "p", model="claude-opus-4-7",
            profile_llm={"model": {"anthropic": "ignored"}},
        )
        assert m.call_args.kwargs["model"] == "claude-opus-4-7"


def test_call_text_profile_model_used_when_no_explicit(_clean_env):
    """没传 model 时 profile.model.<provider> 生效"""
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk")
    from chisha import llm_client
    with patch("chisha.llm_providers.anthropic_api.call") as m:
        m.return_value = _STUB_DICT
        llm_client.call_text(
            "p",
            profile_llm={"model": {"anthropic": "claude-opus-4-7"}},
        )
        assert m.call_args.kwargs["model"] == "claude-opus-4-7"


def test_has_llm_key_truthy(_clean_env):
    _clean_env.setenv("ANTHROPIC_API_KEY", "sk")
    from chisha import llm_client
    assert llm_client.has_llm_key() is True


def test_has_llm_key_false(_clean_env):
    from chisha import llm_client
    with patch("chisha.llm_providers.claude_code_cli.is_available",
                return_value=False):
        assert llm_client.has_llm_key() is False
