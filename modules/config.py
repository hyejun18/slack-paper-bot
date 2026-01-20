"""Configuration loader for Slack Paper Bot."""

import os
from pathlib import Path
from typing import Any

import yaml


class Config:
    """Application configuration manager."""

    def __init__(self, config_path: str = "config.yml"):
        self.config_path = Path(config_path)
        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.config_path}\n"
                f"Please copy config.yml.example to config.yml and fill in your values."
            )

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}

        # Override with environment variables if set
        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        """Override config values with environment variables."""
        env_mappings = {
            "SLACK_BOT_TOKEN": ("slack", "bot_token"),
            "SLACK_SIGNING_SECRET": ("slack", "signing_secret"),
            "GEMINI_API_KEY": ("gemini", "api_key"),
            "SERVER_PORT": ("server", "port"),
        }

        for env_var, path in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                self._set_nested(path, value)

    def _set_nested(self, path: tuple[str, ...], value: Any) -> None:
        """Set a nested config value."""
        current = self._config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Convert port to int if needed
        if path[-1] == "port":
            value = int(value)
        current[path[-1]] = value

    def _get_nested(self, path: tuple[str, ...], default: Any = None) -> Any:
        """Get a nested config value."""
        current = self._config
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
        return current

    # Slack settings
    @property
    def slack_bot_token(self) -> str:
        return self._get_nested(("slack", "bot_token"), "")

    @property
    def slack_signing_secret(self) -> str:
        return self._get_nested(("slack", "signing_secret"), "")

    @property
    def slack_channel_ids(self) -> list[str]:
        return self._get_nested(("slack", "channel_ids"), [])

    @property
    def slack_bot_user_id(self) -> str | None:
        return self._get_nested(("slack", "bot_user_id"))

    # Gemini settings
    @property
    def gemini_api_key(self) -> str:
        return self._get_nested(("gemini", "api_key"), "")

    @property
    def gemini_model(self) -> str:
        return self._get_nested(("gemini", "model"), "gemini-1.5-flash")

    # Server settings
    @property
    def server_host(self) -> str:
        return self._get_nested(("server", "host"), "0.0.0.0")

    @property
    def server_port(self) -> int:
        return self._get_nested(("server", "port"), 8000)

    @property
    def ssl_enabled(self) -> bool:
        return self._get_nested(("server", "ssl", "enabled"), True)

    @property
    def ssl_cert_file(self) -> str:
        return self._get_nested(("server", "ssl", "cert_file"), "certs/cert.pem")

    @property
    def ssl_key_file(self) -> str:
        return self._get_nested(("server", "ssl", "key_file"), "certs/key.pem")

    # Logging settings
    @property
    def log_level(self) -> str:
        return self._get_nested(("logging", "level"), "INFO")

    @property
    def log_file(self) -> str | None:
        return self._get_nested(("logging", "file"))

    @property
    def log_max_size_mb(self) -> int:
        return self._get_nested(("logging", "max_size_mb"), 10)

    @property
    def log_backup_count(self) -> int:
        return self._get_nested(("logging", "backup_count"), 5)

    # Summary settings
    @property
    def summary_max_pages(self) -> int:
        return self._get_nested(("summary", "max_pages"), 50)

    @property
    def summary_detail_level(self) -> str:
        return self._get_nested(("summary", "detail_level"), "normal")

    @property
    def summary_enable_cache(self) -> bool:
        return self._get_nested(("summary", "enable_cache"), True)

    @property
    def summary_cache_dir(self) -> str:
        return self._get_nested(("summary", "cache_dir"), "cache")

    # Advanced settings
    @property
    def timeout(self) -> int:
        return self._get_nested(("advanced", "timeout"), 120)

    @property
    def max_retries(self) -> int:
        return self._get_nested(("advanced", "max_retries"), 3)

    @property
    def retry_delay(self) -> int:
        return self._get_nested(("advanced", "retry_delay"), 2)

    def validate(self) -> list[str]:
        """Validate required configuration values."""
        errors = []

        if not self.slack_bot_token:
            errors.append("slack.bot_token is required")
        elif not self.slack_bot_token.startswith("xoxb-"):
            errors.append("slack.bot_token should start with 'xoxb-'")

        if not self.slack_signing_secret:
            errors.append("slack.signing_secret is required")

        if not self.slack_channel_ids:
            errors.append("slack.channel_ids must have at least one channel")

        if not self.gemini_api_key:
            errors.append("gemini.api_key is required")

        if self.ssl_enabled:
            cert_path = Path(self.ssl_cert_file)
            key_path = Path(self.ssl_key_file)
            if not cert_path.exists():
                errors.append(f"SSL cert file not found: {cert_path}")
            if not key_path.exists():
                errors.append(f"SSL key file not found: {key_path}")

        return errors


# Global config instance
_config: Config | None = None


def get_config(config_path: str = "config.yml") -> Config:
    """Get or create the global config instance."""
    global _config
    if _config is None:
        _config = Config(config_path)
    return _config


def reload_config(config_path: str = "config.yml") -> Config:
    """Reload configuration from file."""
    global _config
    _config = Config(config_path)
    return _config
