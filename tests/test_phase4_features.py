"""Tests for Phase 4 features: AI model catalog, pricing, templates, multi-language, vocabulary."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bits_whisperer.core.settings import (
    AISettings,
    AppSettings,
    CopilotSettings,
)
from bits_whisperer.utils.constants import (
    ALL_AI_MODELS,
    ANTHROPIC_AI_MODELS,
    BUILTIN_PROMPT_TEMPLATES,
    COPILOT_AI_MODELS,
    COPILOT_TIERS,
    GEMINI_AI_MODELS,
    OLLAMA_AI_MODELS,
    OPENAI_AI_MODELS,
    format_price_per_1k,
    get_ai_model_by_id,
    get_copilot_models_for_tier,
    get_models_for_provider,
    get_prompt_template_by_id,
    get_templates_by_category,
)

# -----------------------------------------------------------------------
# AI Model Catalog tests
# -----------------------------------------------------------------------


class TestAIModelCatalog:
    """AI model catalog constants."""

    def test_openai_model_count(self) -> None:
        assert len(OPENAI_AI_MODELS) == 4

    def test_anthropic_model_count(self) -> None:
        assert len(ANTHROPIC_AI_MODELS) == 3

    def test_gemini_model_count(self) -> None:
        assert len(GEMINI_AI_MODELS) == 8

    def test_copilot_model_count(self) -> None:
        assert len(COPILOT_AI_MODELS) == 7

    def test_all_ai_models_combined(self) -> None:
        total = (
            len(OPENAI_AI_MODELS)
            + len(ANTHROPIC_AI_MODELS)
            + len(GEMINI_AI_MODELS)
            + len(COPILOT_AI_MODELS)
            + len(OLLAMA_AI_MODELS)
        )
        assert len(ALL_AI_MODELS) == total

    def test_model_ids_unique_per_provider(self) -> None:
        for models in [
            OPENAI_AI_MODELS,
            ANTHROPIC_AI_MODELS,
            GEMINI_AI_MODELS,
            COPILOT_AI_MODELS,
            OLLAMA_AI_MODELS,
        ]:
            ids = [m.id for m in models]
            assert len(ids) == len(set(ids)), "Duplicate model IDs"

    def test_all_models_have_name(self) -> None:
        for m in ALL_AI_MODELS:
            assert m.name, f"Model {m.id} missing name"

    def test_all_models_have_provider(self) -> None:
        for m in ALL_AI_MODELS:
            assert m.provider in ("openai", "anthropic", "gemini", "copilot", "ollama")

    def test_all_models_have_context_window(self) -> None:
        for m in ALL_AI_MODELS:
            assert m.context_window > 0, f"Model {m.id} context_window must be positive"

    def test_model_is_frozen(self) -> None:
        model = OPENAI_AI_MODELS[0]
        with pytest.raises(AttributeError):
            model.id = "tampered"  # type: ignore[misc]


class TestGemmaModels:
    """Gemma model support in Gemini catalog."""

    def test_gemma_models_present(self) -> None:
        gemma = [m for m in GEMINI_AI_MODELS if "gemma" in m.id.lower()]
        assert len(gemma) == 5

    def test_gemma_27b(self) -> None:
        m = get_ai_model_by_id("gemma-3-27b-it", "gemini")
        assert m is not None
        assert "27B" in m.name

    def test_gemma_12b(self) -> None:
        m = get_ai_model_by_id("gemma-3-12b-it", "gemini")
        assert m is not None
        assert "12B" in m.name

    def test_gemma_4b(self) -> None:
        m = get_ai_model_by_id("gemma-3-4b-it", "gemini")
        assert m is not None
        assert "4B" in m.name

    def test_gemma_1b(self) -> None:
        m = get_ai_model_by_id("gemma-3-1b-it", "gemini")
        assert m is not None
        assert "1B" in m.name

    def test_gemma_3n_e4b(self) -> None:
        m = get_ai_model_by_id("gemma-3n-e4b-it", "gemini")
        assert m is not None
        assert "E4B" in m.name

    def test_gemma_pricing_is_low(self) -> None:
        gemma = [m for m in GEMINI_AI_MODELS if "gemma" in m.id.lower()]
        for m in gemma:
            assert m.input_price_per_1m <= 1.0, f"Gemma {m.id} pricing too high"


# -----------------------------------------------------------------------
# Pricing helper tests
# -----------------------------------------------------------------------


class TestPricingHelpers:
    """format_price_per_1k and related helpers."""

    def test_format_price_normal(self) -> None:
        result = format_price_per_1k(5.0)
        assert "$" in result
        assert "1K" in result

    def test_format_price_zero(self) -> None:
        result = format_price_per_1k(0.0)
        assert "free" in result.lower() or "$0" in result.lower()

    def test_format_price_small(self) -> None:
        result = format_price_per_1k(0.15)  # $0.15 per 1M
        assert "$" in result

    def test_get_ai_model_by_id_found(self) -> None:
        model = get_ai_model_by_id("gpt-4o-mini", "openai")
        assert model is not None
        assert model.name

    def test_get_ai_model_by_id_not_found(self) -> None:
        assert get_ai_model_by_id("nonexistent", "openai") is None

    def test_get_ai_model_by_id_wrong_provider(self) -> None:
        assert get_ai_model_by_id("gpt-4o-mini", "anthropic") is None

    def test_get_models_for_provider(self) -> None:
        models = get_models_for_provider("openai")
        assert len(models) == 4

    def test_get_models_for_unknown_provider(self) -> None:
        models = get_models_for_provider("unknown")
        assert len(models) == 0


# -----------------------------------------------------------------------
# Copilot subscription tier tests
# -----------------------------------------------------------------------


class TestCopilotTiers:
    """Copilot subscription tier configuration."""

    def test_four_tiers(self) -> None:
        assert len(COPILOT_TIERS) == 4

    def test_tier_keys(self) -> None:
        assert set(COPILOT_TIERS.keys()) == {"free", "pro", "business", "enterprise"}

    def test_free_tier_price(self) -> None:
        assert "free" in COPILOT_TIERS["free"]["price"].lower()

    def test_pro_tier_price(self) -> None:
        assert "$10" in COPILOT_TIERS["pro"]["price"]

    def test_all_tiers_have_description(self) -> None:
        for tier_key, tier_info in COPILOT_TIERS.items():
            assert "description" in tier_info, f"Tier {tier_key} missing description"
            assert tier_info["description"], f"Tier {tier_key} has empty description"

    def test_all_tiers_have_name(self) -> None:
        for tier_info in COPILOT_TIERS.values():
            assert "name" in tier_info

    def test_get_copilot_models_for_free_tier(self) -> None:
        models = get_copilot_models_for_tier("free")
        assert len(models) >= 1
        # All models should have copilot_tier == "free"
        for m in models:
            assert m.copilot_tier == "free"

    def test_get_copilot_models_for_pro_tier(self) -> None:
        models = get_copilot_models_for_tier("pro")
        # Pro should include free models plus pro models
        assert len(models) > len(get_copilot_models_for_tier("free"))

    def test_copilot_models_have_tier(self) -> None:
        for m in COPILOT_AI_MODELS:
            assert m.copilot_tier in ("free", "pro", "business", "enterprise")

    def test_premium_models_exist(self) -> None:
        premium = [m for m in COPILOT_AI_MODELS if m.is_premium]
        assert len(premium) >= 1


# -----------------------------------------------------------------------
# Prompt Templates tests
# -----------------------------------------------------------------------


class TestPromptTemplates:
    """Built-in prompt templates."""

    def test_ten_builtin_templates(self) -> None:
        assert len(BUILTIN_PROMPT_TEMPLATES) == 10

    def test_unique_ids(self) -> None:
        ids = [t.id for t in BUILTIN_PROMPT_TEMPLATES]
        assert len(ids) == len(set(ids))

    def test_all_have_template_text(self) -> None:
        for t in BUILTIN_PROMPT_TEMPLATES:
            assert t.template, f"Template {t.id} has empty template"

    def test_all_have_category(self) -> None:
        for t in BUILTIN_PROMPT_TEMPLATES:
            assert t.category in ("translation", "summarization", "analysis")

    def test_all_builtin(self) -> None:
        for t in BUILTIN_PROMPT_TEMPLATES:
            assert t.is_builtin is True

    def test_translation_templates(self) -> None:
        trans = get_templates_by_category("translation")
        assert len(trans) == 4

    def test_summarization_templates(self) -> None:
        summ = get_templates_by_category("summarization")
        assert len(summ) == 4

    def test_analysis_templates(self) -> None:
        analysis = get_templates_by_category("analysis")
        assert len(analysis) == 2

    def test_get_template_by_id_found(self) -> None:
        t = get_prompt_template_by_id("translate_standard")
        assert t is not None
        assert t.category == "translation"

    def test_get_template_by_id_not_found(self) -> None:
        assert get_prompt_template_by_id("nonexistent") is None

    def test_template_is_frozen(self) -> None:
        t = BUILTIN_PROMPT_TEMPLATES[0]
        with pytest.raises(AttributeError):
            t.id = "tampered"  # type: ignore[misc]


# -----------------------------------------------------------------------
# Settings tests for new fields
# -----------------------------------------------------------------------


class TestAISettingsNewFields:
    """New AI settings fields for Phase 4."""

    def test_default_multi_target_languages(self) -> None:
        s = AISettings()
        assert s.multi_target_languages == []

    def test_default_custom_vocabulary(self) -> None:
        s = AISettings()
        assert s.custom_vocabulary == []

    def test_default_active_translation_template(self) -> None:
        s = AISettings()
        assert s.active_translation_template == "translate_standard"

    def test_default_active_summarization_template(self) -> None:
        s = AISettings()
        assert s.active_summarization_template == "summary_concise"

    def test_default_custom_prompt_templates(self) -> None:
        s = AISettings()
        assert s.custom_prompt_templates == []

    def test_set_multi_target_languages(self) -> None:
        s = AISettings()
        s.multi_target_languages = ["Spanish", "French", "German"]
        assert len(s.multi_target_languages) == 3

    def test_set_custom_vocabulary(self) -> None:
        s = AISettings()
        s.custom_vocabulary = ["BITS Whisperer", "wxPython", "WCAG"]
        assert len(s.custom_vocabulary) == 3


class TestCopilotSettingsSubscription:
    """CopilotSettings subscription tier field."""

    def test_default_subscription_tier(self) -> None:
        s = CopilotSettings()
        assert s.subscription_tier == "pro"

    def test_set_subscription_tier(self) -> None:
        s = CopilotSettings()
        s.subscription_tier = "enterprise"
        assert s.subscription_tier == "enterprise"


class TestSettingsSerialization:
    """Settings serialization with new fields."""

    def test_ai_settings_roundtrip(self) -> None:
        s = AppSettings()
        s.ai.multi_target_languages = ["Spanish", "French"]
        s.ai.custom_vocabulary = ["BITS Whisperer"]
        s.ai.active_translation_template = "translate_technical"
        s.copilot.subscription_tier = "business"

        # Verify fields are set
        assert s.ai.multi_target_languages == ["Spanish", "French"]
        assert s.ai.custom_vocabulary == ["BITS Whisperer"]
        assert s.ai.active_translation_template == "translate_technical"
        assert s.copilot.subscription_tier == "business"


# -----------------------------------------------------------------------
# AI Service tests
# -----------------------------------------------------------------------


class TestAIServiceTranslateMulti:
    """AI Service translate_multi method."""

    def test_translate_multi_calls_translate_per_language(self) -> None:
        from bits_whisperer.core.ai_service import AIResponse, AIService

        mock_keys = MagicMock()
        settings = AISettings()
        settings.selected_provider = "openai"

        service = AIService(mock_keys, settings)

        # Mock the translate method
        fake_response = AIResponse(
            text="translated text",
            provider="openai",
            model="gpt-4o",
            tokens_used=100,
        )
        service.translate = MagicMock(return_value=fake_response)

        results = service.translate_multi(
            "Hello world",
            target_languages=["Spanish", "French"],
        )

        assert len(results) == 2
        assert "Spanish" in results
        assert "French" in results
        assert service.translate.call_count == 2

    def test_translate_multi_empty_languages(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_keys = MagicMock()
        settings = AISettings()
        service = AIService(mock_keys, settings)

        results = service.translate_multi("Hello", target_languages=[])
        assert results == {}


class TestAIServiceVocabulary:
    """Custom vocabulary in AI Service."""

    def test_translate_with_custom_vocabulary(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_keys = MagicMock()
        settings = AISettings()
        settings.selected_provider = "openai"
        settings.custom_vocabulary = ["BITS Whisperer", "wxPython"]

        service = AIService(mock_keys, settings)

        # We can't test the actual API call but we verify the method accepts vocabulary
        # The method signature should accept custom_vocabulary parameter
        import inspect

        sig = inspect.signature(service.translate)
        assert "custom_vocabulary" in sig.parameters


class TestAIServiceTemplates:
    """Prompt template support in AI Service."""

    def test_translate_accepts_template_id(self) -> None:
        import inspect

        from bits_whisperer.core.ai_service import AIService

        mock_keys = MagicMock()
        settings = AISettings()
        service = AIService(mock_keys, settings)

        sig = inspect.signature(service.translate)
        assert "template_id" in sig.parameters

    def test_summarize_accepts_template_id(self) -> None:
        import inspect

        from bits_whisperer.core.ai_service import AIService

        mock_keys = MagicMock()
        settings = AISettings()
        service = AIService(mock_keys, settings)

        sig = inspect.signature(service.summarize)
        assert "template_id" in sig.parameters


# -----------------------------------------------------------------------
# Streaming support verification
# -----------------------------------------------------------------------


class TestStreamingSupport:
    """Provider streaming capability verification."""

    def test_provider_capabilities_has_streaming(self) -> None:
        from bits_whisperer.providers.base import ProviderCapabilities

        caps = ProviderCapabilities(name="Test", provider_type="cloud")
        assert hasattr(caps, "supports_streaming")
        assert caps.supports_streaming is False  # default

    def test_deepgram_supports_streaming(self) -> None:
        from bits_whisperer.providers.deepgram_provider import DeepgramProvider

        provider = DeepgramProvider()
        caps = provider.get_capabilities()
        assert caps.supports_streaming is True

    def test_assemblyai_supports_streaming(self) -> None:
        from bits_whisperer.providers.assemblyai_provider import AssemblyAIProvider

        provider = AssemblyAIProvider()
        caps = provider.get_capabilities()
        assert caps.supports_streaming is True


# -----------------------------------------------------------------------
# AIProvider chat_stream tests
# -----------------------------------------------------------------------


class TestAIProviderChatStream:
    """AIProvider.chat_stream() method tests."""

    def test_chat_stream_exists_on_abc(self) -> None:
        from bits_whisperer.core.ai_service import AIProvider

        assert hasattr(AIProvider, "chat_stream")

    def test_chat_stream_signature(self) -> None:
        import inspect

        from bits_whisperer.core.ai_service import AIProvider

        sig = inspect.signature(AIProvider.chat_stream)
        params = list(sig.parameters.keys())
        assert "messages" in params
        assert "system_message" in params
        assert "on_delta" in params

    def test_openai_has_chat_stream(self) -> None:
        from bits_whisperer.core.ai_service import OpenAIAIProvider

        provider = OpenAIAIProvider(api_key="test", model="gpt-4o-mini")
        assert hasattr(provider, "chat_stream")

    def test_anthropic_has_chat_stream(self) -> None:
        from bits_whisperer.core.ai_service import AnthropicAIProvider

        provider = AnthropicAIProvider(api_key="test", model="claude-sonnet-4-20250514")
        assert hasattr(provider, "chat_stream")

    def test_gemini_has_chat_stream(self) -> None:
        from bits_whisperer.core.ai_service import GeminiAIProvider

        provider = GeminiAIProvider(api_key="test", model="gemini-2.0-flash")
        assert hasattr(provider, "chat_stream")

    def test_ollama_has_chat_stream(self) -> None:
        from bits_whisperer.core.ai_service import OllamaAIProvider

        provider = OllamaAIProvider(model="llama3.2")
        assert hasattr(provider, "chat_stream")

    def test_azure_has_chat_stream(self) -> None:
        from bits_whisperer.core.ai_service import AzureOpenAIProvider

        provider = AzureOpenAIProvider(
            api_key="test", endpoint="https://test.openai.azure.com", deployment="gpt-4o"
        )
        assert hasattr(provider, "chat_stream")

    def test_default_chat_stream_delegates_to_generate(self) -> None:
        """The default chat_stream falls back to generate()."""
        from bits_whisperer.core.ai_service import AIProvider, AIResponse

        class FakeProvider(AIProvider):
            def generate(self, prompt, *, max_tokens=4096, temperature=0.3):
                return AIResponse(text="hello", provider="fake", model="test")

            def validate_key(self, api_key):
                return True

        provider = FakeProvider()
        messages = [{"role": "user", "content": "hi"}]
        deltas = []
        response = provider.chat_stream(messages, on_delta=lambda d: deltas.append(d))
        assert response.text == "hello"
        assert deltas == ["hello"]


# -----------------------------------------------------------------------
# AIService.chat() tests
# -----------------------------------------------------------------------


class TestAIServiceChat:
    """AIService.chat() method tests."""

    def test_chat_method_exists(self) -> None:
        import inspect

        from bits_whisperer.core.ai_service import AIService

        assert hasattr(AIService, "chat")
        sig = inspect.signature(AIService.chat)
        params = list(sig.parameters.keys())
        assert "messages" in params
        assert "transcript_context" in params
        assert "on_delta" in params
        assert "on_complete" in params
        assert "on_error" in params

    def test_get_provider_display_name(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_keys = MagicMock()
        settings = AISettings()
        settings.selected_provider = "openai"
        settings.openai_model = "gpt-4o-mini"

        service = AIService(mock_keys, settings)
        display = service.get_provider_display_name()
        assert "OpenAI" in display
        assert "gpt-4o-mini" in display

    def test_get_provider_display_name_ollama(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_keys = MagicMock()
        settings = AISettings()
        settings.selected_provider = "ollama"
        settings.ollama_model = "llama3.2"

        service = AIService(mock_keys, settings)
        display = service.get_provider_display_name()
        assert "Ollama" in display
        assert "llama3.2" in display

    def test_get_provider_display_name_anthropic(self) -> None:
        from bits_whisperer.core.ai_service import AIService

        mock_keys = MagicMock()
        settings = AISettings()
        settings.selected_provider = "anthropic"

        service = AIService(mock_keys, settings)
        display = service.get_provider_display_name()
        assert "Anthropic" in display

    def test_chat_calls_on_error_when_no_provider(self) -> None:
        import time

        from bits_whisperer.core.ai_service import AIService

        mock_keys = MagicMock()
        mock_keys.get_key.return_value = None  # no keys configured
        settings = AISettings()
        settings.selected_provider = "openai"

        service = AIService(mock_keys, settings)
        errors = []

        service.chat(
            [{"role": "user", "content": "hello"}],
            on_error=lambda e: errors.append(e),
        )

        # Wait for background thread
        time.sleep(0.5)
        assert len(errors) == 1
        assert "No AI provider configured" in errors[0]
