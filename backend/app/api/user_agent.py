"""
User-Agent管理API
"""

from fastapi import APIRouter
from typing import Optional, List, Dict, Any
from ..services.user_agent_manager import user_agent_manager

router = APIRouter(prefix="/user-agents", tags=["User-Agent"])


@router.get("/info")
async def get_user_agent_info() -> Dict[str, Any]:
    """
    User-Agent更新情報を取得

    Returns:
        {
            "current_version": "2025-11",
            "next_update_date": "2026-02-01",
            "days_until_update": 73,
            "update_required": false,
            "total_user_agents": 24,
            "desktop_count": 12,
            "mobile_count": 12
        }
    """
    return user_agent_manager.get_update_info()


@router.get("/random")
async def get_random_user_agent(
    device_type: Optional[str] = "desktop",
    browser: Optional[str] = None,
    os: Optional[str] = None
) -> Dict[str, str]:
    """
    ランダムなUser-Agentを取得

    Args:
        device_type: "desktop" or "mobile"
        browser: "chrome", "safari", "firefox", "edge" (optional)
        os: "windows", "mac", "linux", "ios", "android" (optional)

    Returns:
        {"user_agent": "Mozilla/5.0 ..."}
    """
    ua = user_agent_manager.get_random_user_agent(
        device_type=device_type,
        browser_preference=browser,
        os_preference=os
    )

    return {"user_agent": ua}


@router.get("/list")
async def list_user_agents(device_type: Optional[str] = None) -> Dict[str, List[str]]:
    """
    全User-Agentリストを取得

    Args:
        device_type: "desktop" or "mobile" (optional, 指定なしで全て)

    Returns:
        {"user_agents": ["Mozilla/5.0 ...", ...], "count": 24}
    """
    uas = user_agent_manager.get_all_user_agents(device_type)

    return {
        "user_agents": uas,
        "count": len(uas)
    }


@router.post("/test")
async def test_user_agent_with_persona(persona: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """
    ペルソナに基づいてUser-Agentをテスト生成

    Body:
        {
            "preferred_device": "desktop" | "mobile",
            "preferred_browser": "chrome" | "safari" | "firefox" | "edge",
            "preferred_os": "windows" | "mac" | "linux" | "ios" | "android"
        }

    Returns:
        {"user_agent": "Mozilla/5.0 ..."}
    """
    ua = user_agent_manager.get_user_agent_for_persona(persona)

    return {"user_agent": ua}
