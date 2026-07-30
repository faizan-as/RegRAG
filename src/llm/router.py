"""LLM provider abstraction for Azure OpenAI, Anthropic, and vLLM."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from apps.api.settings import LLMProvider, Settings, get_settings


class LLMConfigurationError(RuntimeError):
    """Raised when an LLM provider is selected without required configuration."""


class LLMClient(Protocol):
    """Provider-neutral async LLM client."""

    provider_name: str

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        """Generate one complete response."""

    async def stream(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """Stream response tokens."""


class AzureOpenAIClient:
    """Azure OpenAI chat-completions client wrapper."""

    provider_name = LLMProvider.AZURE_OPENAI.value

    def __init__(self, settings: Settings) -> None:
        if not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
            raise LLMConfigurationError("Azure OpenAI endpoint and API key are required.")
        from openai import AsyncAzureOpenAI

        self._deployment = settings.azure_openai_deployment
        self._client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop_sequences,
        )
        return response.choices[0].message.content or ""

    async def stream(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop_sequences,
            stream=True,
        )
        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token


class AnthropicClient:
    """Anthropic Claude client wrapper."""

    provider_name = LLMProvider.ANTHROPIC.value
    def __init__(self, settings: Settings) -> None:
        if not settings.anthropic_api_key:
            raise LLMConfigurationError("Anthropic API key is required.")
        from anthropic import AsyncAnthropic

        self._model = settings.llm_choice
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or 1024,
            temperature=temperature,
            stop_sequences=stop_sequences,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")

    async def stream(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> AsyncIterator[str]:
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens or 1024,
            temperature=temperature,
            stop_sequences=stop_sequences,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text


class VLLMClient:
    """OpenAI-compatible vLLM client wrapper."""

    provider_name = LLMProvider.VLLM.value
    def __init__(self, settings: Settings) -> None:
        if not settings.onprem_llm_base_url:
            raise LLMConfigurationError("ONPREM_LLM_BASE_URL is required for vLLM.")
        from openai import AsyncOpenAI

        self._model = settings.llm_choice
        self._client = AsyncOpenAI(base_url=settings.onprem_llm_base_url, api_key="unused")

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop_sequences,
        )
        return response.choices[0].message.content or ""

    async def stream(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        stop_sequences: list[str] | None = None,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stop=stop_sequences,
            stream=True,
        )
        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build the configured LLM client."""
    settings = settings or get_settings()
    if settings.llm_provider == LLMProvider.AZURE_OPENAI:
        return AzureOpenAIClient(settings)
    if settings.llm_provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(settings)
    if settings.llm_provider == LLMProvider.VLLM:
        return VLLMClient(settings)
    raise LLMConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}")