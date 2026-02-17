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

    # OpenAI
    openai_api_key: Optional[str] = Field(default=None, env="OPENAI_API_KEY")

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def brightdata_proxy_url(self) -> str:
        if not self.brightdata_username or not self.brightdata_password:
            return ""
        return f"http://{self.brightdata_username}:{self.brightdata_password}@{self.brightdata_host}:{self.brightdata_port}"


settings = Settings()
