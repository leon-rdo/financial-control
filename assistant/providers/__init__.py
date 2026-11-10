from django.conf import settings

from .base import LLMProvider, Part, ProviderError, StepResult


class ProviderNotAvailable(Exception):
    pass


def get_provider() -> LLMProvider:
    name = (settings.AI_PROVIDER or "anthropic").lower()
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    if name == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider()
    raise ProviderNotAvailable(name)


__all__ = ["LLMProvider", "Part", "ProviderError", "StepResult", "ProviderNotAvailable", "get_provider"]
