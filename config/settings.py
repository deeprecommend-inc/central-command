from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional, Literal


class Settings(BaseSettings):
    # BrightData Proxy
    brightdata_username: str = Field(default="", env="BRIGHTDATA_USERNAME")
    brightdata_password: str = Field(default="", env="BRIGHTDATA_PASSWORD")
    brightdata_host: str = Field(default="brd.superproxy.io", env="BRIGHTDATA_HOST")
    brightdata_port: int = Field(default=22225, env="BRIGHTDATA_PORT")
    # Proxy type: residential (住宅IP), datacenter, mobile, isp
    brightdata_proxy_type: Literal["residential", "datacenter", "mobile", "isp"] = Field(
        default="residential", env="BRIGHTDATA_PROXY_TYPE"
    )

    # Browser
    headless: bool = Field(default=True, env="HEADLESS")
    parallel_sessions: int = Field(default=5, env="PARALLEL_SESSIONS")

    # LLM Configuration
    # provider: openai, anthropic, local (OpenAI-compatible local server)
    llm_provider: str = Field(default="openai", env="LLM_PROVIDER")
    # base_url for local LLM servers (Ollama, LM Studio, vLLM, llama.cpp, etc.)
    # Examples: http://localhost:11434/v1 (Ollama), http://localhost:1234/v1 (LM Studio)
    llm_base_url: str = Field(default="http://localhost:11434/v1", env="LLM_BASE_URL")
    llm_model: str = Field(default="gpt-4o", env="LLM_MODEL")
    llm_api_key: str = Field(default="", env="LLM_API_KEY")

    # OpenAI (legacy, used as fallback if LLM_API_KEY not set)
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, env="ANTHROPIC_API_KEY")

    # Channels - Slack
    slack_webhook_url: str = Field(default="", env="SLACK_WEBHOOK_URL")
    slack_bot_token: str = Field(default="", env="SLACK_BOT_TOKEN")
    slack_default_channel: str = Field(default="", env="SLACK_DEFAULT_CHANNEL")

    # Channels - Teams
    teams_webhook_url: str = Field(default="", env="TEAMS_WEBHOOK_URL")

    # Channels - Email
    email_smtp_host: str = Field(default="", env="EMAIL_SMTP_HOST")
    email_smtp_port: int = Field(default=587, env="EMAIL_SMTP_PORT")
    email_smtp_user: str = Field(default="", env="EMAIL_SMTP_USER")
    email_smtp_password: str = Field(default="", env="EMAIL_SMTP_PASSWORD")
    email_from: str = Field(default="", env="EMAIL_FROM")

    # Channels - Webhook (comma-separated URLs)
    webhook_urls: str = Field(default="", env="WEBHOOK_URLS")

    # Vault
    vault_enabled: bool = Field(default=False, env="CCP_VAULT_ENABLED")
    vault_dir: str = Field(default=".ccp_vault", env="CCP_VAULT_DIR")

    # CAPTCHA
    captcha_provider: str = Field(default="", env="CAPTCHA_PROVIDER")
    captcha_api_key: str = Field(default="", env="CAPTCHA_API_KEY")

    # Redis
    redis_url: str = Field(default="", env="REDIS_URL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def brightdata_proxy_url(self) -> str:
        if not self.brightdata_username or not self.brightdata_password:
            return ""
        return f"http://{self.brightdata_username}:{self.brightdata_password}@{self.brightdata_host}:{self.brightdata_port}"


    def load_from_vault(self) -> dict[str, str]:
        """Load secrets from vault if enabled"""
        if not self.vault_enabled:
            return {}
        try:
            from src.security.vault import SecureVault
            vault = SecureVault(vault_dir=self.vault_dir)
            vault.init()
            return vault.get_for_settings()
        except Exception:
            return {}


settings = Settings()
