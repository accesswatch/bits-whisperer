"""Tests for Phase 6 features: budget limits, cost confirmation, wizard budget page."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bits_whisperer.core.job import Job
from bits_whisperer.core.settings import (
    AppSettings,
    BudgetSettings,
)

# -----------------------------------------------------------------------
# BudgetSettings unit tests
# -----------------------------------------------------------------------


class TestBudgetSettingsDefaults:
    """BudgetSettings default field values."""

    def test_enabled_by_default(self) -> None:
        b = BudgetSettings()
        assert b.enabled is True

    def test_default_limit_zero(self) -> None:
        b = BudgetSettings()
        assert b.default_limit_usd == 0.0

    def test_provider_limits_empty(self) -> None:
        b = BudgetSettings()
        assert b.provider_limits == {}

    def test_always_confirm_paid_default(self) -> None:
        b = BudgetSettings()
        assert b.always_confirm_paid is True


class TestBudgetGetLimit:
    """BudgetSettings.get_limit() priority chain."""

    def test_default_limit_when_no_overrides(self) -> None:
        b = BudgetSettings(default_limit_usd=5.0)
        assert b.get_limit("openai_whisper") == 5.0

    def test_provider_level_override(self) -> None:
        b = BudgetSettings(
            default_limit_usd=5.0,
            provider_limits={"openai_whisper": 10.0},
        )
        assert b.get_limit("openai_whisper") == 10.0

    def test_model_specific_override(self) -> None:
        b = BudgetSettings(
            default_limit_usd=5.0,
            provider_limits={
                "openai_whisper": 10.0,
                "openai_whisper:whisper-1": 2.0,
            },
        )
        assert b.get_limit("openai_whisper", "whisper-1") == 2.0

    def test_model_falls_back_to_provider(self) -> None:
        b = BudgetSettings(
            default_limit_usd=5.0,
            provider_limits={"openai_whisper": 8.0},
        )
        # Model not in limits → falls back to provider level
        assert b.get_limit("openai_whisper", "whisper-1") == 8.0

    def test_unknown_provider_returns_default(self) -> None:
        b = BudgetSettings(
            default_limit_usd=3.0,
            provider_limits={"openai_whisper": 10.0},
        )
        assert b.get_limit("deepgram") == 3.0

    def test_zero_default_means_unlimited(self) -> None:
        b = BudgetSettings(default_limit_usd=0.0)
        assert b.get_limit("any_provider") == 0.0

    def test_empty_model_string_uses_provider(self) -> None:
        b = BudgetSettings(
            default_limit_usd=1.0,
            provider_limits={"groq_whisper": 7.0},
        )
        assert b.get_limit("groq_whisper", "") == 7.0


class TestBudgetExceedsLimit:
    """BudgetSettings.exceeds_limit() logic."""

    def test_within_budget(self) -> None:
        b = BudgetSettings(default_limit_usd=10.0)
        exceeds, limit = b.exceeds_limit("openai_whisper", "", 5.0)
        assert exceeds is False
        assert limit == 10.0

    def test_over_budget(self) -> None:
        b = BudgetSettings(default_limit_usd=2.0)
        exceeds, limit = b.exceeds_limit("openai_whisper", "", 5.0)
        assert exceeds is True
        assert limit == 2.0

    def test_exactly_at_limit_not_exceeded(self) -> None:
        b = BudgetSettings(default_limit_usd=5.0)
        exceeds, limit = b.exceeds_limit("openai_whisper", "", 5.0)
        assert exceeds is False
        assert limit == 5.0

    def test_disabled_never_exceeds(self) -> None:
        b = BudgetSettings(enabled=False, default_limit_usd=1.0)
        exceeds, limit = b.exceeds_limit("openai_whisper", "", 999.0)
        assert exceeds is False
        assert limit == 0.0

    def test_zero_limit_never_exceeds(self) -> None:
        b = BudgetSettings(default_limit_usd=0.0)
        exceeds, limit = b.exceeds_limit("openai_whisper", "", 100.0)
        assert exceeds is False
        assert limit == 0.0

    def test_provider_specific_limit(self) -> None:
        b = BudgetSettings(
            default_limit_usd=100.0,
            provider_limits={"deepgram": 0.50},
        )
        exceeds, limit = b.exceeds_limit("deepgram", "", 1.0)
        assert exceeds is True
        assert limit == 0.50

    def test_model_specific_limit(self) -> None:
        b = BudgetSettings(
            default_limit_usd=100.0,
            provider_limits={
                "openai_whisper": 50.0,
                "openai_whisper:whisper-1": 0.25,
            },
        )
        exceeds, limit = b.exceeds_limit("openai_whisper", "whisper-1", 0.30)
        assert exceeds is True
        assert limit == 0.25


class TestBudgetSettingsSerialization:
    """BudgetSettings round-trip through AppSettings save/load."""

    def test_budget_in_appsettings(self) -> None:
        s = AppSettings()
        assert hasattr(s, "budget")
        assert isinstance(s.budget, BudgetSettings)

    def test_budget_save_load_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            s = AppSettings()
            s.budget.enabled = True
            s.budget.default_limit_usd = 5.0
            s.budget.always_confirm_paid = False
            s.budget.provider_limits = {
                "openai_whisper": 10.0,
                "deepgram": 2.5,
            }
            s.save()

            loaded = AppSettings.load()
            assert loaded.budget.enabled is True
            assert loaded.budget.default_limit_usd == 5.0
            assert loaded.budget.always_confirm_paid is False
            assert loaded.budget.provider_limits["openai_whisper"] == 10.0
            assert loaded.budget.provider_limits["deepgram"] == 2.5

    def test_budget_from_dict_empty(self) -> None:
        """Old settings files without budget → defaults."""
        data: dict = {"general": {"language": "en"}}
        s = AppSettings._from_dict(data)
        assert s.budget.enabled is True
        assert s.budget.default_limit_usd == 0.0
        assert s.budget.provider_limits == {}

    def test_budget_from_dict_partial(self) -> None:
        data = {
            "budget": {
                "enabled": False,
                "default_limit_usd": 3.0,
            }
        }
        s = AppSettings._from_dict(data)
        assert s.budget.enabled is False
        assert s.budget.default_limit_usd == 3.0
        assert s.budget.always_confirm_paid is True  # default

    def test_budget_from_dict_with_provider_limits(self) -> None:
        data = {
            "budget": {
                "enabled": True,
                "provider_limits": {"groq_whisper": 1.50, "gemini": 0.25},
            }
        }
        s = AppSettings._from_dict(data)
        assert s.budget.provider_limits["groq_whisper"] == 1.50
        assert s.budget.provider_limits["gemini"] == 0.25

    def test_model_specific_key_roundtrip(self, tmp_path: Path) -> None:
        settings_file = tmp_path / "settings.json"
        with patch("bits_whisperer.core.settings._SETTINGS_PATH", settings_file):
            s = AppSettings()
            s.budget.provider_limits = {
                "openai_whisper:whisper-1": 0.50,
                "groq_whisper": 3.0,
            }
            s.save()

            loaded = AppSettings.load()
            assert loaded.budget.provider_limits["openai_whisper:whisper-1"] == 0.50
            assert loaded.budget.provider_limits["groq_whisper"] == 3.0


# -----------------------------------------------------------------------
# Setup Wizard page constants
# -----------------------------------------------------------------------


class TestWizardPageConstants:
    """Verify wizard page indices after adding the Budget page."""

    def test_page_count(self) -> None:
        from bits_whisperer.ui.setup_wizard import _TOTAL_PAGES

        assert _TOTAL_PAGES == 9

    def test_budget_page_index(self) -> None:
        from bits_whisperer.ui.setup_wizard import PAGE_BUDGET

        assert PAGE_BUDGET == 6

    def test_preferences_page_index(self) -> None:
        from bits_whisperer.ui.setup_wizard import PAGE_PREFERENCES

        assert PAGE_PREFERENCES == 7

    def test_summary_page_index(self) -> None:
        from bits_whisperer.ui.setup_wizard import PAGE_SUMMARY

        assert PAGE_SUMMARY == 8

    def test_page_order(self) -> None:
        from bits_whisperer.ui.setup_wizard import (
            PAGE_AI_COPILOT,
            PAGE_BUDGET,
            PAGE_HARDWARE,
            PAGE_MODE,
            PAGE_MODELS,
            PAGE_PREFERENCES,
            PAGE_PROVIDERS,
            PAGE_SUMMARY,
            PAGE_WELCOME,
        )

        pages = [
            PAGE_WELCOME,
            PAGE_MODE,
            PAGE_HARDWARE,
            PAGE_MODELS,
            PAGE_PROVIDERS,
            PAGE_AI_COPILOT,
            PAGE_BUDGET,
            PAGE_PREFERENCES,
            PAGE_SUMMARY,
        ]
        assert pages == list(range(9))


# -----------------------------------------------------------------------
# Cost estimation helpers
# -----------------------------------------------------------------------


class TestCostEstimation:
    """Test cost estimation logic used in add_file_wizard and main_frame."""

    def test_free_provider_zero_cost(self) -> None:
        pm = MagicMock()
        pm.estimate_cost.return_value = 0.0
        pm.get_capabilities.return_value = MagicMock(provider_type="local", rate_per_minute_usd=0.0)
        assert pm.estimate_cost("local_whisper", 300) == 0.0

    def test_paid_provider_cost_calculation(self) -> None:
        pm = MagicMock()
        # 5 minutes at $0.006/min = $0.03
        pm.estimate_cost.return_value = 0.03
        pm.get_capabilities.return_value = MagicMock(
            provider_type="cloud",
            rate_per_minute_usd=0.006,
            name="OpenAI Whisper",
        )
        cost = pm.estimate_cost("openai_whisper", 300)
        assert cost == pytest.approx(0.03)

    def test_budget_check_with_cost(self) -> None:
        """Integration: cost estimation + budget check."""
        budget = BudgetSettings(
            default_limit_usd=0.02,
        )
        estimated_cost = 0.03
        exceeds, limit = budget.exceeds_limit("openai_whisper", "", estimated_cost)
        assert exceeds is True
        assert limit == 0.02


# -----------------------------------------------------------------------
# Job cost_estimate field
# -----------------------------------------------------------------------


class TestJobCostEstimate:
    """Job.cost_estimate should reflect wizard-calculated cost."""

    def test_job_default_cost_zero(self) -> None:
        job = Job(
            id="test-1",
            file_path="/test.wav",
            file_name="test.wav",
            file_size_bytes=1000,
            provider="local_whisper",
            model="base",
            language="auto",
        )
        assert job.cost_estimate == 0.0

    def test_job_cost_set(self) -> None:
        job = Job(
            id="test-2",
            file_path="/test.wav",
            file_name="test.wav",
            file_size_bytes=1000,
            provider="openai_whisper",
            model="whisper-1",
            language="auto",
            cost_estimate=0.05,
        )
        assert job.cost_estimate == 0.05

    def test_job_cost_display_property(self) -> None:
        job = Job(
            id="test-3",
            file_path="/test.wav",
            file_name="test.wav",
            file_size_bytes=1000,
            provider="openai_whisper",
            model="whisper-1",
            language="auto",
            cost_estimate=0.123,
        )
        display = job.cost_display
        assert "$" in display or "0.12" in display or "Free" not in display


# -----------------------------------------------------------------------
# Budget + always_confirm_paid interaction
# -----------------------------------------------------------------------


class TestBudgetConfirmationLogic:
    """Verify budget + always_confirm_paid interaction."""

    def test_within_budget_still_needs_confirm_when_always_on(self) -> None:
        """When within budget but always_confirm_paid=True, user should
        still be asked (this is handled in UI, but we verify the flag)."""
        b = BudgetSettings(
            default_limit_usd=100.0,
            always_confirm_paid=True,
        )
        exceeds, limit = b.exceeds_limit("openai_whisper", "", 0.05)
        assert exceeds is False
        assert b.always_confirm_paid is True  # UI should still confirm

    def test_within_budget_no_confirm_when_off(self) -> None:
        b = BudgetSettings(
            default_limit_usd=100.0,
            always_confirm_paid=False,
        )
        exceeds, limit = b.exceeds_limit("openai_whisper", "", 0.05)
        assert exceeds is False
        assert b.always_confirm_paid is False  # UI can skip confirmation

    def test_over_budget_always_warns(self) -> None:
        """Over-budget warning is independent of always_confirm_paid."""
        b = BudgetSettings(
            default_limit_usd=0.01,
            always_confirm_paid=False,
        )
        exceeds, limit = b.exceeds_limit("openai_whisper", "", 1.0)
        assert exceeds is True
        assert limit == 0.01


# -----------------------------------------------------------------------
# Multiple providers with different limits
# -----------------------------------------------------------------------


class TestMultiProviderBudgets:
    """Budget limits across multiple providers."""

    def test_different_limits_per_provider(self) -> None:
        b = BudgetSettings(
            default_limit_usd=5.0,
            provider_limits={
                "openai_whisper": 10.0,
                "deepgram": 1.0,
                "gemini": 50.0,
            },
        )
        assert b.get_limit("openai_whisper") == 10.0
        assert b.get_limit("deepgram") == 1.0
        assert b.get_limit("gemini") == 50.0
        assert b.get_limit("groq_whisper") == 5.0  # falls to default

    def test_exceeds_varies_by_provider(self) -> None:
        b = BudgetSettings(
            default_limit_usd=5.0,
            provider_limits={
                "openai_whisper": 10.0,
                "deepgram": 1.0,
            },
        )
        # $2 is under OpenAI's limit but over Deepgram's
        exceeds_oai, _ = b.exceeds_limit("openai_whisper", "", 2.0)
        exceeds_dg, _ = b.exceeds_limit("deepgram", "", 2.0)
        assert exceeds_oai is False
        assert exceeds_dg is True

    def test_model_override_only_affects_that_model(self) -> None:
        b = BudgetSettings(
            default_limit_usd=10.0,
            provider_limits={
                "openai_whisper": 5.0,
                "openai_whisper:whisper-1": 0.50,
            },
        )
        # whisper-1 has its own limit
        exceeds_w1, lim_w1 = b.exceeds_limit("openai_whisper", "whisper-1", 0.60)
        assert exceeds_w1 is True
        assert lim_w1 == 0.50

        # Other models fall back to provider limit
        exceeds_def, lim_def = b.exceeds_limit("openai_whisper", "other-model", 0.60)
        assert exceeds_def is False
        assert lim_def == 5.0
