import os
import pytest
from unittest.mock import patch


def test_config_loads_anthropic_key():
    env = {
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "GITHUB_PAT": "ghp_test",
        "WEBHOOK_SECRET": "secret",
        "SLACK_BOT_TOKEN": "xoxb-test",
    }
    with patch.dict(os.environ, env, clear=True):
        from importlib import reload
        import app.config as config_mod
        reload(config_mod)
        cfg = config_mod.get_config()
        assert cfg.anthropic_api_key == "sk-ant-test"
        assert cfg.llm_provider == "anthropic"


def test_config_loads_openrouter_key():
    env = {
        "OPENROUTER_API_KEY": "sk-or-test",
        "GITHUB_PAT": "ghp_test",
        "WEBHOOK_SECRET": "secret",
        "SLACK_BOT_TOKEN": "xoxb-test",
    }
    with patch.dict(os.environ, env, clear=True):
        from importlib import reload
        import app.config as config_mod
        reload(config_mod)
        cfg = config_mod.get_config()
        assert cfg.openrouter_api_key == "sk-or-test"
        assert cfg.llm_provider == "openrouter"


def test_config_fails_without_any_llm_key():
    env = {
        "GITHUB_PAT": "ghp_test",
        "WEBHOOK_SECRET": "secret",
        "SLACK_BOT_TOKEN": "xoxb-test",
    }
    with patch.dict(os.environ, env, clear=True):
        from importlib import reload
        import app.config as config_mod
        with pytest.raises(ValueError, match="At least one LLM API key"):
            reload(config_mod)
            config_mod.get_config()


def test_config_loads_review_rules():
    env = {
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "GITHUB_PAT": "ghp_test",
        "WEBHOOK_SECRET": "secret",
        "SLACK_BOT_TOKEN": "xoxb-test",
    }
    with patch.dict(os.environ, env, clear=True):
        from importlib import reload
        import app.config as config_mod
        reload(config_mod)
        cfg = config_mod.get_config()
        rules = cfg.review_rules
        assert "has_tests" in rules["checklist"]
        assert "*.lock" in rules["skip_files"]
        assert rules["skip_options"]["draft_prs"] is True
