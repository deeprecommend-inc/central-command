"""
User Agent Manager - Manages browser fingerprints and user agents
"""
import random
from dataclasses import dataclass
from typing import Optional
from fake_useragent import UserAgent
from loguru import logger


@dataclass
class BrowserProfile:
    """Browser profile with consistent fingerprint settings"""

    user_agent: str
    viewport_width: int
    viewport_height: int
    locale: str
    timezone: str
    platform: str

    def to_playwright_context(self) -> dict:
        """Convert to Playwright browser context options"""
        return {
            "user_agent": self.user_agent,
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "locale": self.locale,
            "timezone_id": self.timezone,
        }


class UserAgentManager:
    """Manages user agents and browser profiles"""

    VIEWPORTS = [
        (1920, 1080),
        (1366, 768),
        (1536, 864),
        (1440, 900),
        (1280, 720),
        (2560, 1440),
    ]

    LOCALES = ["en-US", "en-GB", "de-DE", "fr-FR", "ja-JP", "es-ES"]

    TIMEZONES = [
        "America/New_York",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Berlin",
        "Asia/Tokyo",
        "Australia/Sydney",
    ]

    def __init__(self):
        self._ua = UserAgent()
        self._profiles: dict[str, BrowserProfile] = {}

    def get_random_profile(self, session_id: Optional[str] = None) -> BrowserProfile:
        """Generate a random but consistent browser profile"""
        # If session_id provided and profile exists, return cached
        if session_id and session_id in self._profiles:
            return self._profiles[session_id]

        # Generate new profile
        ua_string = self._ua.random
        viewport = random.choice(self.VIEWPORTS)
        locale = random.choice(self.LOCALES)
        timezone = random.choice(self.TIMEZONES)

        # Detect platform from UA
        platform = "Windows"
        if "Mac" in ua_string:
            platform = "MacIntel"
        elif "Linux" in ua_string:
            platform = "Linux x86_64"

        profile = BrowserProfile(
            user_agent=ua_string,
            viewport_width=viewport[0],
            viewport_height=viewport[1],
            locale=locale,
            timezone=timezone,
            platform=platform,
        )

        # Cache if session_id provided
        if session_id:
            self._profiles[session_id] = profile
            logger.debug(f"Created browser profile for session {session_id}")

        return profile

    def get_chrome_profile(self, session_id: Optional[str] = None) -> BrowserProfile:
        """Get a Chrome-specific profile"""
        if session_id and session_id in self._profiles:
            return self._profiles[session_id]

        ua_string = self._ua.chrome
        viewport = random.choice(self.VIEWPORTS)
        locale = random.choice(self.LOCALES)
        timezone = random.choice(self.TIMEZONES)

        profile = BrowserProfile(
            user_agent=ua_string,
            viewport_width=viewport[0],
            viewport_height=viewport[1],
            locale=locale,
            timezone=timezone,
            platform="Windows",
        )

        if session_id:
            self._profiles[session_id] = profile

        return profile

    def clear_session(self, session_id: str) -> None:
        """Clear cached profile for session"""
        if session_id in self._profiles:
            del self._profiles[session_id]
            logger.debug(f"Cleared profile for session {session_id}")
