"""
Mulogin API連携サービス
ブラウザ指紋管理・マルチアカウント運用
"""

import httpx
from typing import Dict, Any, Optional, List
from ..core.config import settings
from .user_agent_manager import user_agent_manager


class MuloginService:
    """Mulogin API Client"""

    def __init__(self):
        self.api_url = getattr(settings, 'MULOGIN_API_URL', 'http://127.0.0.1:35000/api/v1')
        self.api_key = getattr(settings, 'MULOGIN_API_KEY', '')
        self.timeout = 30

    async def create_profile(
        self,
        name: str,
        proxy: Optional[str] = None,
        fingerprint_config: Optional[Dict[str, Any]] = None,
        persona: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        ブラウザプロファイルを作成

        Args:
            name: プロファイル名
            proxy: プロキシ設定 (例: "192.168.1.1:8080" or "user:pass@192.168.1.1:8080")
            fingerprint_config: 指紋設定
            persona: ペルソナ情報

        Returns:
            {"profile_id": "xxx", "profile_name": "xxx"}
        """

        # デフォルト設定
        config = {
            "name": name,
            "proxyEnabled": proxy is not None,
            "proxyType": "http",
            "proxyHost": "",
            "proxyPort": "",
            "proxyUser": "",
            "proxyPassword": "",

            # ブラウザ指紋設定
            "ua": fingerprint_config.get("user_agent") if fingerprint_config else self._generate_random_ua(persona),
            "canvas": fingerprint_config.get("canvas", "random") if fingerprint_config else "random",
            "webgl": fingerprint_config.get("webgl", "random") if fingerprint_config else "random",
            "webglInfo": fingerprint_config.get("webgl_info", "random") if fingerprint_config else "random",
            "clientRects": fingerprint_config.get("client_rects", "random") if fingerprint_config else "random",

            # 位置情報
            "timezone": persona.get("timezone") if persona else "America/New_York",
            "language": persona.get("language") if persona else "en-US",
            "geolocation": self._get_geolocation(persona) if persona else {"accuracy": 10, "latitude": 40.7128, "longitude": -74.0060},

            # 画面設定
            "resolution": fingerprint_config.get("screen_resolution") if fingerprint_config else persona.get("screen_resolution", "1920x1080") if persona else "1920x1080",

            # デバイス
            "deviceName": persona.get("preferred_device", "desktop") if persona else "desktop",

            # その他
            "platform": "Win32",
            "hardwareConcurrency": 8,
            "deviceMemory": 8,
            "doNotTrack": "1",
            "mediaDevices": "random",
            "audioContext": "random",
            "fonts": "random"
        }

        # プロキシ設定をパース
        if proxy:
            proxy_parts = self._parse_proxy(proxy)
            config.update({
                "proxyHost": proxy_parts["host"],
                "proxyPort": proxy_parts["port"],
                "proxyUser": proxy_parts.get("username", ""),
                "proxyPassword": proxy_parts.get("password", "")
            })

        # API呼び出し
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_url}/profile/create",
                json=config,
                headers={"Authorization": f"Bearer {self.api_key}"}
            )

            if response.status_code != 200:
                raise Exception(f"Mulogin API error: {response.text}")

            data = response.json()

            return {
                "profile_id": data.get("id"),
                "profile_name": data.get("name"),
                "fingerprint": {
                    "user_agent": config["ua"],
                    "canvas": config["canvas"],
                    "webgl": config["webgl"],
                    "timezone": config["timezone"],
                    "language": config["language"],
                    "resolution": config["resolution"]
                }
            }

    async def start_browser(self, profile_id: str) -> Dict[str, Any]:
        """
        ブラウザを起動

        Returns:
            {"ws_endpoint": "ws://...", "selenium_port": "9222"}
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_url}/profile/start",
                json={"id": profile_id},
                headers={"Authorization": f"Bearer {self.api_key}"}
            )

            if response.status_code != 200:
                raise Exception(f"Mulogin API error: {response.text}")

            data = response.json()

            return {
                "ws_endpoint": data.get("ws"),
                "selenium_port": data.get("http"),
                "profile_id": profile_id
            }

    async def stop_browser(self, profile_id: str) -> bool:
        """ブラウザを停止"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_url}/profile/stop",
                json={"id": profile_id},
                headers={"Authorization": f"Bearer {self.api_key}"}
            )

            return response.status_code == 200

    async def delete_profile(self, profile_id: str) -> bool:
        """プロファイルを削除"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_url}/profile/delete",
                json={"id": profile_id},
                headers={"Authorization": f"Bearer {self.api_key}"}
            )

            return response.status_code == 200

    async def list_profiles(self, limit: int = 100) -> List[Dict[str, Any]]:
        """プロファイル一覧を取得"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.api_url}/profile/list?limit={limit}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )

            if response.status_code != 200:
                raise Exception(f"Mulogin API error: {response.text}")

            return response.json().get("list", [])

    async def update_profile(self, profile_id: str, updates: Dict[str, Any]) -> bool:
        """プロファイルを更新"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.api_url}/profile/update",
                json={"id": profile_id, **updates},
                headers={"Authorization": f"Bearer {self.api_key}"}
            )

            return response.status_code == 200

    def _parse_proxy(self, proxy: str) -> Dict[str, str]:
        """プロキシ文字列をパース"""
        import re

        # user:pass@host:port 形式
        auth_match = re.match(r'^([^:]+):([^@]+)@([^:]+):(\d+)$', proxy)
        if auth_match:
            return {
                "username": auth_match.group(1),
                "password": auth_match.group(2),
                "host": auth_match.group(3),
                "port": auth_match.group(4)
            }

        # host:port 形式
        simple_match = re.match(r'^([^:]+):(\d+)$', proxy)
        if simple_match:
            return {
                "host": simple_match.group(1),
                "port": simple_match.group(2)
            }

        raise ValueError(f"Invalid proxy format: {proxy}")

    def _generate_random_ua(self, persona: Optional[Dict[str, Any]] = None) -> str:
        """
        ペルソナに基づいてUser-Agentを生成

        user_agent_managerを使用して最新のUser-Agentを取得
        3ヶ月ごとに自動更新される
        """
        return user_agent_manager.get_user_agent_for_persona(persona)

    def _get_geolocation(self, persona: Dict[str, Any]) -> Dict[str, float]:
        """ペルソナに基づいて位置情報を取得"""
        # 都市から緯度経度を取得（簡易版）
        city_coords = {
            "New York": {"latitude": 40.7128, "longitude": -74.0060},
            "Los Angeles": {"latitude": 34.0522, "longitude": -118.2437},
            "Tokyo": {"latitude": 35.6762, "longitude": 139.6503},
            "London": {"latitude": 51.5074, "longitude": -0.1278},
            "Paris": {"latitude": 48.8566, "longitude": 2.3522},
        }

        city = persona.get("location_city", "New York")
        coords = city_coords.get(city, city_coords["New York"])

        return {
            "accuracy": 10,
            **coords
        }


# シングルトンインスタンス
mulogin_service = MuloginService()
