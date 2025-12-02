"""
LLM Settings API - Configure API keys for multiple LLM providers
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from cryptography.fernet import Fernet
import base64
import os

from ..models.database import (
    get_db,
    LLMSetting,
    LLMProviderEnum,
)
from ..core.config import settings

router = APIRouter()


# 暗号化キーの取得または生成
def get_encryption_key() -> bytes:
    """Get or generate encryption key for API keys"""
    key = getattr(settings, 'ENCRYPTION_KEY', None)
    if key:
        return base64.urlsafe_b64decode(key)
    # フォールバック: SECRET_KEYからキーを派生
    secret = getattr(settings, 'SECRET_KEY', 'default-secret-key-change-me')
    return base64.urlsafe_b64encode(secret[:32].encode().ljust(32, b'0'))


def encrypt_api_key(api_key: str) -> str:
    """Encrypt API key"""
    if not api_key:
        return ""
    f = Fernet(get_encryption_key())
    return f.encrypt(api_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt API key"""
    if not encrypted_key:
        return ""
    try:
        f = Fernet(get_encryption_key())
        return f.decrypt(encrypted_key.encode()).decode()
    except Exception:
        return ""


# Request/Response Models
class LLMSettingCreate(BaseModel):
    """Create LLM setting request"""
    provider: str = Field(..., description="Provider: anthropic, openai, google, groq")
    api_key: str = Field(..., description="API Key")
    default_model: Optional[str] = Field(None, description="Default model name")
    api_base_url: Optional[str] = Field(None, description="Custom API base URL")
    is_enabled: bool = Field(True, description="Enable this provider")
    is_default: bool = Field(False, description="Set as default provider")


class LLMSettingUpdate(BaseModel):
    """Update LLM setting request"""
    api_key: Optional[str] = Field(None, description="API Key (leave empty to keep current)")
    default_model: Optional[str] = Field(None, description="Default model name")
    api_base_url: Optional[str] = Field(None, description="Custom API base URL")
    is_enabled: Optional[bool] = Field(None, description="Enable this provider")
    is_default: Optional[bool] = Field(None, description="Set as default provider")


class LLMSettingResponse(BaseModel):
    """LLM setting response"""
    id: int
    provider: str
    display_name: str
    default_model: Optional[str]
    api_base_url: Optional[str]
    is_enabled: bool
    is_default: bool
    has_api_key: bool
    last_verified_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]


class LLMProviderInfo(BaseModel):
    """LLM provider information"""
    provider: str
    display_name: str
    default_models: List[str]
    description: str


# Provider configurations
PROVIDER_INFO = {
    LLMProviderEnum.ANTHROPIC: {
        "display_name": "Anthropic (Claude)",
        "default_models": [
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
        ],
        "description": "Claude models by Anthropic - recommended for browser automation"
    },
    LLMProviderEnum.OPENAI: {
        "display_name": "OpenAI (GPT)",
        "default_models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
        ],
        "description": "GPT models by OpenAI"
    },
    LLMProviderEnum.GOOGLE: {
        "display_name": "Google (Gemini)",
        "default_models": [
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ],
        "description": "Gemini models by Google"
    },
    LLMProviderEnum.GROQ: {
        "display_name": "Groq",
        "default_models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ],
        "description": "Fast inference with Groq - good for speed optimization"
    },
}


@router.get("/llm-settings/providers", response_model=List[LLMProviderInfo])
async def get_available_providers():
    """Get list of available LLM providers with their configurations"""
    return [
        LLMProviderInfo(
            provider=provider.value,
            display_name=info["display_name"],
            default_models=info["default_models"],
            description=info["description"]
        )
        for provider, info in PROVIDER_INFO.items()
    ]


@router.get("/llm-settings", response_model=List[LLMSettingResponse])
async def get_llm_settings(db: AsyncSession = Depends(get_db)):
    """Get all LLM settings"""
    result = await db.execute(select(LLMSetting).order_by(LLMSetting.provider))
    settings_list = result.scalars().all()

    # 設定がないプロバイダーを初期化
    existing_providers = {s.provider for s in settings_list}
    for provider in LLMProviderEnum:
        if provider not in existing_providers:
            new_setting = LLMSetting(
                provider=provider,
                display_name=PROVIDER_INFO[provider]["display_name"],
                default_model=PROVIDER_INFO[provider]["default_models"][0],
                is_enabled=False,
                is_default=False,
            )
            db.add(new_setting)

    await db.commit()

    # 再取得
    result = await db.execute(select(LLMSetting).order_by(LLMSetting.provider))
    settings_list = result.scalars().all()

    return [
        LLMSettingResponse(
            id=s.id,
            provider=s.provider.value,
            display_name=s.display_name,
            default_model=s.default_model,
            api_base_url=s.api_base_url,
            is_enabled=s.is_enabled,
            is_default=s.is_default,
            has_api_key=bool(s.api_key_encrypted),
            last_verified_at=s.last_verified_at,
            last_used_at=s.last_used_at,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in settings_list
    ]


@router.get("/llm-settings/{provider}", response_model=LLMSettingResponse)
async def get_llm_setting(provider: str, db: AsyncSession = Depends(get_db)):
    """Get LLM setting for a specific provider"""
    try:
        provider_enum = LLMProviderEnum(provider.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")

    result = await db.execute(
        select(LLMSetting).where(LLMSetting.provider == provider_enum)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        # 新規作成
        setting = LLMSetting(
            provider=provider_enum,
            display_name=PROVIDER_INFO[provider_enum]["display_name"],
            default_model=PROVIDER_INFO[provider_enum]["default_models"][0],
            is_enabled=False,
            is_default=False,
        )
        db.add(setting)
        await db.commit()
        await db.refresh(setting)

    return LLMSettingResponse(
        id=setting.id,
        provider=setting.provider.value,
        display_name=setting.display_name,
        default_model=setting.default_model,
        api_base_url=setting.api_base_url,
        is_enabled=setting.is_enabled,
        is_default=setting.is_default,
        has_api_key=bool(setting.api_key_encrypted),
        last_verified_at=setting.last_verified_at,
        last_used_at=setting.last_used_at,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


@router.put("/llm-settings/{provider}", response_model=LLMSettingResponse)
async def update_llm_setting(
    provider: str,
    request: LLMSettingUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update LLM setting for a specific provider"""
    try:
        provider_enum = LLMProviderEnum(provider.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")

    result = await db.execute(
        select(LLMSetting).where(LLMSetting.provider == provider_enum)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        # 新規作成
        setting = LLMSetting(
            provider=provider_enum,
            display_name=PROVIDER_INFO[provider_enum]["display_name"],
            default_model=PROVIDER_INFO[provider_enum]["default_models"][0],
        )
        db.add(setting)
        await db.flush()

    # 更新
    if request.api_key is not None and request.api_key != "":
        setting.api_key_encrypted = encrypt_api_key(request.api_key)

    if request.default_model is not None:
        setting.default_model = request.default_model

    if request.api_base_url is not None:
        setting.api_base_url = request.api_base_url if request.api_base_url else None

    if request.is_enabled is not None:
        setting.is_enabled = request.is_enabled

    if request.is_default is not None and request.is_default:
        # 他のプロバイダーのデフォルトを解除
        await db.execute(
            update(LLMSetting).where(LLMSetting.provider != provider_enum).values(is_default=False)
        )
        setting.is_default = True
    elif request.is_default is not None:
        setting.is_default = request.is_default

    await db.commit()
    await db.refresh(setting)

    return LLMSettingResponse(
        id=setting.id,
        provider=setting.provider.value,
        display_name=setting.display_name,
        default_model=setting.default_model,
        api_base_url=setting.api_base_url,
        is_enabled=setting.is_enabled,
        is_default=setting.is_default,
        has_api_key=bool(setting.api_key_encrypted),
        last_verified_at=setting.last_verified_at,
        last_used_at=setting.last_used_at,
        created_at=setting.created_at,
        updated_at=setting.updated_at,
    )


@router.post("/llm-settings/{provider}/verify")
async def verify_llm_setting(provider: str, db: AsyncSession = Depends(get_db)):
    """Verify API key for a specific provider by making a test call"""
    try:
        provider_enum = LLMProviderEnum(provider.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")

    result = await db.execute(
        select(LLMSetting).where(LLMSetting.provider == provider_enum)
    )
    setting = result.scalar_one_or_none()

    if not setting or not setting.api_key_encrypted:
        raise HTTPException(status_code=400, detail="API key not configured")

    api_key = decrypt_api_key(setting.api_key_encrypted)
    if not api_key:
        raise HTTPException(status_code=400, detail="Failed to decrypt API key")

    # プロバイダーごとの検証
    try:
        if provider_enum == LLMProviderEnum.ANTHROPIC:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            # 簡単なテストリクエスト
            response = client.messages.create(
                model=setting.default_model or "claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            verified = True

        elif provider_enum == LLMProviderEnum.OPENAI:
            import openai
            client = openai.OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model=setting.default_model or "gpt-4o-mini",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            verified = True

        elif provider_enum == LLMProviderEnum.GOOGLE:
            # Google AI SDK
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=setting.default_model or "gemini-2.0-flash",
                contents="Hi"
            )
            verified = True

        elif provider_enum == LLMProviderEnum.GROQ:
            from groq import Groq
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model=setting.default_model or "llama-3.3-70b-versatile",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            verified = True

        else:
            raise HTTPException(status_code=400, detail=f"Verification not supported for {provider}")

        # 検証成功時刻を更新
        setting.last_verified_at = datetime.utcnow()
        await db.commit()

        return {"success": True, "message": f"{setting.display_name} API key verified successfully"}

    except Exception as e:
        return {"success": False, "message": f"Verification failed: {str(e)}"}


@router.delete("/llm-settings/{provider}/api-key")
async def delete_api_key(provider: str, db: AsyncSession = Depends(get_db)):
    """Delete API key for a specific provider"""
    try:
        provider_enum = LLMProviderEnum(provider.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}")

    result = await db.execute(
        select(LLMSetting).where(LLMSetting.provider == provider_enum)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")

    setting.api_key_encrypted = None
    setting.is_enabled = False
    setting.last_verified_at = None

    await db.commit()

    return {"success": True, "message": f"API key deleted for {setting.display_name}"}


@router.get("/llm-settings/default/provider")
async def get_default_provider(db: AsyncSession = Depends(get_db)):
    """Get the default LLM provider"""
    result = await db.execute(
        select(LLMSetting).where(LLMSetting.is_default == True, LLMSetting.is_enabled == True)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        # デフォルトがない場合は有効な最初のプロバイダーを返す
        result = await db.execute(
            select(LLMSetting).where(LLMSetting.is_enabled == True).order_by(LLMSetting.provider)
        )
        setting = result.scalar_one_or_none()

    if not setting:
        return {"provider": None, "model": None, "message": "No LLM provider configured"}

    return {
        "provider": setting.provider.value,
        "model": setting.default_model,
        "display_name": setting.display_name
    }
