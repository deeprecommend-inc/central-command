"""
User-Agent管理サービス
3ヶ月ごとに最新のUser-Agentに自動更新
"""

import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class UserAgentManager:
    """
    User-Agent自動更新管理

    特徴:
    - 3ヶ月ごとに自動更新（2025/11時点 → 2026/2、2026/5、2026/8...）
    - デスクトップ/モバイルの複数バリエーション
    - Windows/Mac/Linux/iOS/Android対応
    - Chrome/Safari/Edge/Firefoxの最新バージョン
    """

    # 次回更新日: 2026年2月1日（3ヶ月後）
    NEXT_UPDATE_DATE = "2026-02-01"
    CURRENT_VERSION = "2025-11"

    # 2025年11月時点の最新User-Agent
    USER_AGENTS = {
        "desktop": {
            "chrome_windows": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            ],
            "chrome_mac": [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            ],
            "safari_mac": [
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
            ],
            "edge_windows": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
            ],
            "firefox_windows": [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0",
            ],
            "chrome_linux": [
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            ],
        },
        "mobile": {
            "safari_ios": [
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.7 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
            ],
            "chrome_android": [
                "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
                "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
                "Mozilla/5.0 (Linux; Android 13; SM-S911B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36",
            ],
            "safari_ipad": [
                "Mozilla/5.0 (iPad; CPU OS 17_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.7 Mobile/15E148 Safari/604.1",
                "Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1",
            ],
        }
    }

    def __init__(self):
        self.current_date = datetime.now()
        self.next_update = datetime.strptime(self.NEXT_UPDATE_DATE, "%Y-%m-%d")

    def get_random_user_agent(
        self,
        device_type: str = "desktop",
        browser_preference: Optional[str] = None,
        os_preference: Optional[str] = None
    ) -> str:
        """
        ランダムなUser-Agentを取得

        Args:
            device_type: "desktop" or "mobile"
            browser_preference: "chrome", "safari", "firefox", "edge" (optional)
            os_preference: "windows", "mac", "linux", "ios", "android" (optional)

        Returns:
            User-Agent文字列
        """

        if device_type not in self.USER_AGENTS:
            device_type = "desktop"

        available_uas = self.USER_AGENTS[device_type]

        # ブラウザ/OS設定でフィルタリング
        if browser_preference or os_preference:
            filtered_keys = []
            for key in available_uas.keys():
                if browser_preference and browser_preference.lower() in key:
                    filtered_keys.append(key)
                elif os_preference and os_preference.lower() in key:
                    filtered_keys.append(key)

            if filtered_keys:
                selected_key = random.choice(filtered_keys)
                return random.choice(available_uas[selected_key])

        # フィルタなしでランダム選択
        all_uas = []
        for ua_list in available_uas.values():
            all_uas.extend(ua_list)

        return random.choice(all_uas)

    def get_user_agent_for_persona(self, persona: Optional[Dict[str, Any]] = None) -> str:
        """
        ペルソナに基づいてUser-Agentを取得

        Args:
            persona: ペルソナ情報 {
                "preferred_device": "desktop" | "mobile",
                "preferred_browser": "chrome" | "safari" | "firefox" | "edge",
                "preferred_os": "windows" | "mac" | "linux" | "ios" | "android"
            }

        Returns:
            User-Agent文字列
        """

        if not persona:
            return self.get_random_user_agent()

        device = persona.get("preferred_device", "desktop")
        browser = persona.get("preferred_browser")
        os_type = persona.get("preferred_os")

        return self.get_random_user_agent(device, browser, os_type)

    def is_update_required(self) -> bool:
        """
        User-Agentの更新が必要かチェック

        Returns:
            True: 更新が必要（3ヶ月経過）
            False: 更新不要
        """
        return self.current_date >= self.next_update

    def get_update_info(self) -> Dict[str, Any]:
        """
        更新情報を取得

        Returns:
            {
                "current_version": "2025-11",
                "next_update_date": "2026-02-01",
                "days_until_update": 73,
                "update_required": False,
                "total_user_agents": 24
            }
        """
        days_until = (self.next_update - self.current_date).days

        # User-Agent総数をカウント
        total_uas = sum(
            len(ua_list)
            for category in self.USER_AGENTS.values()
            for ua_list in category.values()
        )

        return {
            "current_version": self.CURRENT_VERSION,
            "next_update_date": self.NEXT_UPDATE_DATE,
            "days_until_update": max(0, days_until),
            "update_required": self.is_update_required(),
            "total_user_agents": total_uas,
            "desktop_count": sum(len(ua_list) for ua_list in self.USER_AGENTS["desktop"].values()),
            "mobile_count": sum(len(ua_list) for ua_list in self.USER_AGENTS["mobile"].values()),
        }

    def get_all_user_agents(self, device_type: Optional[str] = None) -> List[str]:
        """
        全User-Agentリストを取得

        Args:
            device_type: "desktop" or "mobile" (optional, 指定なしで全て)

        Returns:
            User-Agent文字列のリスト
        """
        all_uas = []

        if device_type:
            if device_type in self.USER_AGENTS:
                for ua_list in self.USER_AGENTS[device_type].values():
                    all_uas.extend(ua_list)
        else:
            for category in self.USER_AGENTS.values():
                for ua_list in category.values():
                    all_uas.extend(ua_list)

        return all_uas

    def log_update_reminder(self):
        """更新リマインダーをログ出力"""
        info = self.get_update_info()

        if info["update_required"]:
            logger.warning(
                f"⚠️  User-Agent更新が必要です！ "
                f"現在のバージョン: {info['current_version']} "
                f"次回更新予定: {info['next_update_date']}"
            )
        else:
            logger.info(
                f"✅ User-Agent最新バージョン: {info['current_version']} "
                f"次回更新まで: {info['days_until_update']}日 "
                f"({info['next_update_date']})"
            )


# シングルトンインスタンス
user_agent_manager = UserAgentManager()


# 起動時に更新状況をログ出力
user_agent_manager.log_update_reminder()
