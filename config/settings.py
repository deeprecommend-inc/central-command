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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def brightdata_proxy_url(self) -> str:
        if not self.brightdata_username or not self.brightdata_password:
            return ""
        return f"http://{self.brightdata_username}:{self.brightdata_password}@{self.brightdata_host}:{self.brightdata_port}"


settings = Settings()
