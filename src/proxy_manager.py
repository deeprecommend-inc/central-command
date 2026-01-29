"""
Proxy Manager - BrightData proxy rotation management
"""
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from loguru import logger


class ProxyType(Enum):
    """BrightData proxy types"""
    DATACENTER = "datacenter"
    RESIDENTIAL = "residential"  # 住宅IP
    MOBILE = "mobile"
    ISP = "isp"


@dataclass
class ProxyConfig:
    username: str
    password: str
    host: str = "brd.superproxy.io"
    port: int = 22225
    country: Optional[str] = None
    session_id: Optional[str] = None
    proxy_type: ProxyType = ProxyType.RESIDENTIAL  # デフォルトは住宅IP

    def get_url(self) -> str:
        user = self.username
        if self.country:
            user = f"{user}-country-{self.country}"
        if self.session_id:
            user = f"{user}-session-{self.session_id}"
        return f"http://{user}:{self.password}@{self.host}:{self.port}"


@dataclass
class ProxyStats:
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests


class ProxyManager:
    """Manages BrightData proxy rotation with Residential IP support"""

    COUNTRIES = ["us", "gb", "de", "fr", "jp", "au", "ca"]

    # BrightData host/port by proxy type
    PROXY_ENDPOINTS = {
        ProxyType.DATACENTER: ("brd.superproxy.io", 22225),
        ProxyType.RESIDENTIAL: ("brd.superproxy.io", 22225),  # Same host, zone differs in username
        ProxyType.MOBILE: ("brd.superproxy.io", 22225),
        ProxyType.ISP: ("brd.superproxy.io", 22225),
    }

    def __init__(
        self,
        username: str,
        password: str,
        host: str = "brd.superproxy.io",
        port: int = 22225,
        proxy_type: ProxyType = ProxyType.RESIDENTIAL,  # デフォルト住宅IP
    ):
        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.proxy_type = proxy_type
        self._session_counter = 0
        self._stats: dict[str, ProxyStats] = {}

        logger.info(f"ProxyManager initialized: type={proxy_type.value}, host={host}")

    def get_proxy(
        self,
        country: Optional[str] = None,
        new_session: bool = True,
        proxy_type: Optional[ProxyType] = None,
    ) -> ProxyConfig:
        """Get a proxy configuration with optional country and session rotation"""
        session_id = None
        if new_session:
            self._session_counter += 1
            session_id = f"sess{self._session_counter}_{random.randint(1000, 9999)}"

        use_type = proxy_type or self.proxy_type

        proxy = ProxyConfig(
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            country=country or random.choice(self.COUNTRIES),
            session_id=session_id,
            proxy_type=use_type,
        )
        logger.debug(
            f"Created proxy config: type={use_type.value}, "
            f"country={proxy.country}, session={proxy.session_id}"
        )
        return proxy

    def get_rotating_proxy_url(self) -> str:
        """Get a simple rotating proxy URL (BrightData handles rotation)"""
        return f"http://{self.username}:{self.password}@{self.host}:{self.port}"

    def record_success(self, session_id: str) -> None:
        """Record successful request for stats"""
        if session_id not in self._stats:
            self._stats[session_id] = ProxyStats()
        self._stats[session_id].total_requests += 1
        self._stats[session_id].successful_requests += 1

    def record_failure(self, session_id: str) -> None:
        """Record failed request for stats"""
        if session_id not in self._stats:
            self._stats[session_id] = ProxyStats()
        self._stats[session_id].total_requests += 1
        self._stats[session_id].failed_requests += 1

    def get_stats(self) -> dict[str, ProxyStats]:
        """Get all proxy stats"""
        return self._stats.copy()
