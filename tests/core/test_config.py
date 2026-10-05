"""Settings validators for M19's DISP_LLM_*/DISP_EMBEDDING_* fields —
"a deployment whose ingestion jobs all fail two minutes into a worker run
is worse than one that refuses to boot" (M19-llm.md §3)."""

import pytest
from pydantic import SecretStr, ValidationError

from disp.core.config import Settings, get_settings


def _settings(**overrides: object) -> Settings:
    data = get_settings().model_dump()
    data.update(overrides)
    return Settings(**data)


def test_llm_enabled_with_empty_key_refuses_to_boot() -> None:
    with pytest.raises(ValidationError, match="DISP_LLM_API_KEY"):
        _settings(llm_enabled=True, llm_api_key=SecretStr(""))


def test_llm_enabled_with_key_boots() -> None:
    settings = _settings(llm_enabled=True, llm_api_key=SecretStr("sk-test"))
    assert settings.llm_enabled is True


def test_llm_disabled_with_no_key_boots() -> None:
    settings = _settings(llm_enabled=False, llm_api_key=SecretStr(""))
    assert settings.llm_enabled is False


def test_embedding_enabled_voyage_with_empty_key_refuses_to_boot() -> None:
    with pytest.raises(ValidationError, match="DISP_EMBEDDING_API_KEY"):
        _settings(
            embedding_enabled=True, embedding_provider="voyage", embedding_api_key=SecretStr("")
        )


def test_embedding_enabled_voyage_with_key_boots() -> None:
    settings = _settings(
        embedding_enabled=True,
        embedding_provider="voyage",
        embedding_api_key=SecretStr("voyage-test"),
    )
    assert settings.embedding_enabled is True


def test_embedding_enabled_local_with_no_key_boots() -> None:
    """The local provider needs no API key at all (§7)."""
    settings = _settings(
        embedding_enabled=True, embedding_provider="local", embedding_api_key=SecretStr("")
    )
    assert settings.embedding_provider == "local"


def test_llm_defaults_match_spec() -> None:
    settings = get_settings()
    assert settings.llm_enabled is False
    assert settings.llm_model == "claude-opus-5"
    assert settings.llm_fast_model == "claude-haiku-4-5"
    assert settings.llm_max_output_tokens == 16000
    assert settings.llm_timeout_seconds == 600
    assert settings.llm_max_retries == 2
    assert settings.llm_effort == "high"
    assert settings.embedding_enabled is False
    assert settings.embedding_provider == "voyage"
    assert settings.embedding_model == "voyage-3"
    assert settings.embedding_dimensions == 1024


def test_translation_enabled_deepl_with_empty_key_refuses_to_boot() -> None:
    """M22-translation.md §3, same argument as the LLM validator above."""
    with pytest.raises(ValidationError, match="DISP_TRANSLATION_API_KEY"):
        _settings(
            translation_enabled=True,
            translation_backend="deepl",
            translation_api_key=SecretStr(""),
        )


def test_translation_enabled_fake_with_no_key_boots() -> None:
    """Provider-conditional: the fake backend needs no credential, which is
    what lets a hermetic dev or test deployment turn translation on (§3)."""
    settings = _settings(
        translation_enabled=True,
        translation_backend="fake",
        translation_api_key=SecretStr(""),
    )
    assert settings.translation_backend == "fake"


def test_translation_enabled_deepl_with_key_boots() -> None:
    settings = _settings(
        translation_enabled=True,
        translation_backend="deepl",
        translation_api_key=SecretStr("key:fx"),
    )
    assert settings.translation_enabled is True


def test_translation_defaults_match_spec() -> None:
    settings = get_settings()
    assert settings.translation_enabled is False
    assert settings.translation_backend == "deepl"
    assert settings.translation_base_url == ""
    assert settings.translation_default_target_lang == ""
    assert settings.translation_timeout_seconds == 30
    assert settings.translation_max_retries == 2
    assert settings.translation_max_chars == 120_000
