"""Tests for LLM provider routing."""

from __future__ import annotations

import pytest

from apps.api.settings import LLMProvider, Settings
from src.llm.router import LLMConfigurationError, build_llm_client


def test_missing_azure_configuration_fails_safely() -> None:
    settings = Settings(LLM_PROVIDER=LLMProvider.AZURE_OPENAI)

    with pytest.raises(LLMConfigurationError, match="Azure OpenAI"):
        build_llm_client(settings)


def test_missing_anthropic_configuration_fails_safely() -> None:
    settings = Settings(LLM_PROVIDER=LLMProvider.ANTHROPIC)

    with pytest.raises(LLMConfigurationError, match="Anthropic"):
        build_llm_client(settings)


def test_missing_vllm_configuration_fails_safely() -> None:
    settings = Settings(LLM_PROVIDER=LLMProvider.VLLM)

    with pytest.raises(LLMConfigurationError, match="ONPREM_LLM_BASE_URL"):
        build_llm_client(settings)