from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, JSON, Float, Boolean, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.sql import func
from datetime import datetime
import enum
import hashlib

from ..core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


class PlatformEnum(str, enum.Enum):
    YOUTUBE = "youtube"
    X = "x"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"


class EngineTypeEnum(str, enum.Enum):
    API_FAST = "api_fast"
    BROWSER_QA = "browser_qa"


class ExecutionModeEnum(str, enum.Enum):
    """実行モード"""
    REQUESTS = "requests"  # Requests/HTTPライブラリ使用（高速、API直接）
    SELENIUM = "selenium"  # Selenium/Playwright使用（ブラウザ自動化）


class StatusEnum(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


class RunStatusEnum(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


# Accounts Table (Browser-based, no OAuth)
class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(SQLEnum(PlatformEnum), nullable=False, index=True)
    username = Column(String(255), nullable=False)  # SNS username
    email = Column(String(255))  # Login email
    password_encrypted = Column(String(255))  # Encrypted password for browser login
    owner_user_id = Column(Integer, nullable=False, index=True)
    status = Column(SQLEnum(StatusEnum), default=StatusEnum.ACTIVE)
    display_name = Column(String(255))
    account_metadata = Column(JSON, default={})  # Browser session, cookies, etc
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Runs Table
class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    platform = Column(SQLEnum(PlatformEnum), nullable=False, index=True)
    engine = Column(SQLEnum(EngineTypeEnum), default=EngineTypeEnum.API_FAST)
    execution_mode = Column(SQLEnum(ExecutionModeEnum), default=ExecutionModeEnum.SELENIUM, nullable=False)  # requests or selenium
    schedule_json = Column(JSON, nullable=False)  # start, end, repeat, timezone
    observability_json = Column(JSON, nullable=False)  # 16 categories thresholds
    prompt_json = Column(JSON, nullable=False)  # AI generation parameters
    rate_config = Column(JSON, nullable=False)  # hourly, daily, parallel, wait distribution
    approval_required = Column(Boolean, default=True)
    custom_prompt = Column(Text)
    status = Column(SQLEnum(RunStatusEnum), default=RunStatusEnum.PENDING, index=True)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Run Events Table
class RunEvent(Base):
    __tablename__ = "run_events"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False, index=True)
    action = Column(String(100), nullable=False)  # post, reply, like, follow
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True))
    response_code = Column(Integer)
    detail = Column(JSON)  # Full response, metrics
    success = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# AI Drafts Table
class AIDraft(Base):
    __tablename__ = "ai_drafts"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    outputs_json = Column(JSON, nullable=False)  # drafts, schedules, hashtags
    toxicity_score = Column(Float, default=0.0)
    duplication_rate = Column(Float, default=0.0)
    approved = Column(Boolean, default=False)
    approved_by = Column(Integer)
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# KPI Snapshots Table
class KPISnapshot(Base):
    __tablename__ = "kpi_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(SQLEnum(PlatformEnum), nullable=False, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    range_start = Column(DateTime(timezone=True), nullable=False)
    range_end = Column(DateTime(timezone=True), nullable=False)
    metrics_json = Column(JSON, nullable=False)  # followers, engagement, reach, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# Audit WORM Table (Write-Once-Read-Many)
class AuditWORM(Base):
    __tablename__ = "audit_worm"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    actor_user_id = Column(Integer, nullable=False)
    operation = Column(String(100), nullable=False)  # create_run, approve_draft, execute_action
    payload_immutable = Column(JSON, nullable=False)  # Complete operation details
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(String(500))
    hash = Column(String(64))  # SHA256 hash for integrity verification


# Observability Metrics Table
class ObservabilityMetric(Base):
    __tablename__ = "observability_metrics"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False, index=True)
    event_id = Column(Integer, ForeignKey("run_events.id"))
    category = Column(String(50), nullable=False, index=True)  # One of 16 categories
    metric_key = Column(String(100), nullable=False)
    metric_value = Column(Float, nullable=False)
    threshold_value = Column(Float)
    violated = Column(Boolean, default=False)
    action_taken = Column(String(50))  # alert, slow, freeze, abort
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# Campaign Table
class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=False)
    target_metrics = Column(JSON)  # Goals and KPIs
    run_ids = Column(JSON, default=[])  # Associated runs
    status = Column(SQLEnum(RunStatusEnum), default=RunStatusEnum.PENDING)
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Kill Switch Table
class KillSwitch(Base):
    __tablename__ = "kill_switches"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False, unique=True, index=True)
    is_active = Column(Boolean, default=True)
    triggered_at = Column(DateTime(timezone=True))
    triggered_by = Column(Integer)
    reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# Persona Type Enum
class PersonaTypeEnum(str, enum.Enum):
    INDIVIDUAL = "individual"  # 個人
    BUSINESS = "business"  # ビジネス
    INFLUENCER = "influencer"  # インフルエンサー
    BRAND = "brand"  # ブランド
    JOURNALIST = "journalist"  # ジャーナリスト
    ARTIST = "artist"  # アーティスト
    DEVELOPER = "developer"  # 開発者


# Account Generation Status Enum
class AccountGenStatusEnum(str, enum.Enum):
    PENDING = "pending"  # 生成待ち
    GENERATING = "generating"  # 生成中
    VERIFICATION = "verification"  # 認証コード待ち
    COMPLETED = "completed"  # 完了
    FAILED = "failed"  # 失敗
    SUSPENDED = "suspended"  # 停止


class ProxyTypeEnum(str, enum.Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"


class ProxyQualityEnum(str, enum.Enum):
    EXCELLENT = "excellent"  # 優良（応答時間<500ms、成功率>95%）
    GOOD = "good"  # 良好（応答時間<1000ms、成功率>85%）
    FAIR = "fair"  # 普通（応答時間<2000ms、成功率>70%）
    POOR = "poor"  # 低品質（それ以下）
    UNTESTED = "untested"  # 未テスト


# Persona Table
class Persona(Base):
    """ペルソナ（人格）定義"""
    __tablename__ = "personas"

    id = Column(Integer, primary_key=True, index=True)

    # ペルソナ基本情報
    name = Column(String(255), nullable=False)  # ペルソナ名
    persona_type = Column(SQLEnum(PersonaTypeEnum), nullable=False)  # タイプ

    # 人物像
    age_range = Column(String(50))  # 年齢層（例: 20-30）
    gender = Column(String(20))  # 性別
    location_country = Column(String(2))  # 国コード
    location_city = Column(String(100))  # 都市
    timezone = Column(String(50))  # タイムゾーン
    language = Column(String(10))  # 言語（例: en-US, ja-JP）

    # 興味・関心
    interests = Column(JSON, default=[])  # 興味のあるトピック
    occupation = Column(String(255))  # 職業
    education_level = Column(String(50))  # 学歴

    # 行動パターン
    activity_hours = Column(JSON, default={})  # アクティブな時間帯 {"weekday": "9-17", "weekend": "10-22"}
    posting_frequency = Column(String(50))  # 投稿頻度（例: high, medium, low）
    interaction_style = Column(String(50))  # インタラクションスタイル（例: friendly, professional, casual）

    # ブラウザ指紋設定
    browser_fingerprint_config = Column(JSON, default={})  # Mulogin設定
    preferred_device = Column(String(50))  # デバイスタイプ（例: desktop, mobile, tablet）
    screen_resolution = Column(String(50))  # 画面解像度（例: 1920x1080）

    # プロフィール生成設定
    profile_template = Column(JSON, default={})  # プロフィール雛形
    avatar_style = Column(String(50))  # アバタースタイル
    bio_template = Column(Text)  # 自己紹介テンプレート

    # ステータス
    is_active = Column(Boolean, default=True)

    # メタデータ
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Account Generation Tasks Table
class AccountGenerationTask(Base):
    """アカウント自動生成タスク"""
    __tablename__ = "account_generation_tasks"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(SQLEnum(PlatformEnum), nullable=False, index=True)

    # ペルソナベース生成
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True, index=True)  # ペルソナID

    # 大規模生成対応（100万アカウントまで）
    target_count = Column(Integer, nullable=False)  # 生成目標数（最大1000000）
    completed_count = Column(Integer, default=0)  # 完了数
    failed_count = Column(Integer, default=0)  # 失敗数

    # バッチ処理設定
    batch_size = Column(Integer, default=100)  # バッチサイズ（同時生成数）
    current_batch = Column(Integer, default=0)  # 現在のバッチ番号

    # 生成設定
    generation_config = Column(JSON, nullable=False)  # username_pattern, email_domain, phone_provider, etc.

    # プロキシ・IP設定
    proxy_list = Column(JSON, default=[])  # 使用するプロキシリスト
    use_residential_proxy = Column(Boolean, default=True)  # レジデンシャルプロキシを使用
    use_brightdata = Column(Boolean, default=False)  # BrightData使用
    brightdata_zone = Column(String(255))  # BrightDataゾーン

    # Mulogin設定
    use_mulogin = Column(Boolean, default=True)  # Mulogin使用
    mulogin_group_id = Column(String(255))  # Mulginグループグループ

    # 実行モード
    execution_mode = Column(SQLEnum(ExecutionModeEnum), default=ExecutionModeEnum.SELENIUM, nullable=False)  # requests or selenium

    # ブラウザ設定
    headless = Column(Boolean, default=True)

    # 進捗
    status = Column(SQLEnum(AccountGenStatusEnum), default=AccountGenStatusEnum.PENDING, index=True)
    error_message = Column(Text)

    # メタデータ
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Task Log Level Enum
class LogLevelEnum(str, enum.Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"


# Task Logs Table
class TaskLog(Base):
    """タスク実行ログ（リアルタイム表示用）"""
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("account_generation_tasks.id"), nullable=False, index=True)

    # ログ内容
    level = Column(SQLEnum(LogLevelEnum), nullable=False, default=LogLevelEnum.INFO)
    message = Column(Text, nullable=False)
    details = Column(JSON, default={})  # 追加情報（エラーstack trace、プロセス詳細など）

    # アカウント情報（このログが特定のアカウント生成に関連する場合）
    account_index = Column(Integer)  # バッチ内のアカウント番号
    account_username = Column(String(255))  # 生成中のアカウント名

    # タイムスタンプ
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# Generated Accounts Table
class GeneratedAccount(Base):
    """自動生成されたアカウント"""
    __tablename__ = "generated_accounts"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("account_generation_tasks.id"), nullable=False, index=True)
    persona_id = Column(Integer, ForeignKey("personas.id"), nullable=True, index=True)  # ペルソナID
    platform = Column(SQLEnum(PlatformEnum), nullable=False, index=True)

    # アカウント情報（暗号化）
    username = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    phone = Column(String(50))
    password_encrypted = Column(String(500), nullable=False)  # 暗号化されたパスワード

    # 生成時の情報
    proxy_used = Column(String(255))  # 使用したプロキシ
    ip_address = Column(String(45))  # 生成時のIPアドレス
    user_agent = Column(String(500))  # 使用したUser-Agent

    # Mulogin指紋情報
    mulogin_profile_id = Column(String(255))  # Muloginプロファイル ID
    mulogin_profile_name = Column(String(255))  # Muloginプロファイル名
    browser_fingerprint = Column(JSON, default={})  # ブラウザ指紋詳細

    # 認証情報
    verification_code = Column(String(100))  # SMS/Email認証コード
    verification_status = Column(String(50), default="pending")  # pending, verified, failed

    # ステータス
    status = Column(SQLEnum(StatusEnum), default=StatusEnum.ACTIVE, index=True)

    # OAuth連携（生成後にOAuth認証した場合）
    oauth_token_ref = Column(String(255))  # 暗号化されたOAuthトークン参照

    # メタデータ
    generation_metadata = Column(JSON, default={})  # 生成時の詳細情報
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    verified_at = Column(DateTime(timezone=True))
    last_login = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Proxy IP Pool Table
class ProxyIP(Base):
    """プロキシIPプール管理"""
    __tablename__ = "proxy_ips"

    id = Column(Integer, primary_key=True, index=True)

    # プロキシ情報
    ip_address = Column(String(45), nullable=False, index=True)  # IPv6対応
    port = Column(Integer, nullable=False)
    proxy_type = Column(SQLEnum(ProxyTypeEnum), default=ProxyTypeEnum.HTTP)
    username = Column(String(255))  # 認証ユーザー名
    password_encrypted = Column(String(500))  # 暗号化されたパスワード

    # プロキシの分類
    is_residential = Column(Boolean, default=False)  # レジデンシャルプロキシ
    is_mobile = Column(Boolean, default=False)  # モバイルプロキシ
    country_code = Column(String(2))  # ISO 3166-1 alpha-2
    region = Column(String(100))  # 地域
    city = Column(String(100))  # 都市
    isp = Column(String(255))  # ISP名

    # 品質メトリクス
    quality = Column(SQLEnum(ProxyQualityEnum), default=ProxyQualityEnum.UNTESTED, index=True)
    response_time_ms = Column(Float)  # 平均応答時間（ミリ秒）
    success_rate = Column(Float, default=0.0)  # 成功率（0.0-1.0）
    total_requests = Column(Integer, default=0)  # 総リクエスト数
    successful_requests = Column(Integer, default=0)  # 成功リクエスト数
    failed_requests = Column(Integer, default=0)  # 失敗リクエスト数

    # ブロック状況
    blocked_platforms = Column(JSON, default=[])  # ブロックされたプラットフォームリスト
    last_blocked_at = Column(DateTime(timezone=True))  # 最後にブロックされた時刻

    # 使用状況
    last_used_at = Column(DateTime(timezone=True))  # 最後に使用された時刻
    last_tested_at = Column(DateTime(timezone=True))  # 最後にテストされた時刻
    concurrent_users = Column(Integer, default=0)  # 同時使用数

    # ステータス
    is_active = Column(Boolean, default=True, index=True)  # アクティブ状態
    is_banned = Column(Boolean, default=False)  # 完全禁止

    # メタデータ
    source = Column(String(255))  # プロキシの入手元
    notes = Column(Text)  # メモ
    proxy_metadata = Column(JSON, default={})  # その他のメタデータ

    # タイムスタンプ
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Proxy Test Results Table
class ProxyTestResult(Base):
    """プロキシテスト結果の履歴"""
    __tablename__ = "proxy_test_results"

    id = Column(Integer, primary_key=True, index=True)
    proxy_id = Column(Integer, ForeignKey("proxy_ips.id"), nullable=False, index=True)

    # テスト結果
    success = Column(Boolean, nullable=False)
    response_time_ms = Column(Float)
    status_code = Column(Integer)
    error_message = Column(Text)

    # テスト対象
    test_url = Column(String(500))
    platform = Column(SQLEnum(PlatformEnum))  # どのプラットフォームでテストしたか

    # 検出情報
    detected_ip = Column(String(45))  # テスト時に検出されたIP
    detected_location = Column(JSON)  # 検出された位置情報
    is_vpn_detected = Column(Boolean, default=False)  # VPN検知
    is_proxy_detected = Column(Boolean, default=False)  # プロキシ検知

    # タイムスタンプ
    tested_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# LLM Provider Enum
class LLMProviderEnum(str, enum.Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"
    GROQ = "groq"


# LLM Settings Table
class LLMSetting(Base):
    """LLM API設定"""
    __tablename__ = "llm_settings"

    id = Column(Integer, primary_key=True, index=True)

    # プロバイダー情報
    provider = Column(SQLEnum(LLMProviderEnum), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=False)  # 表示名

    # API設定
    api_key_encrypted = Column(String(1000))  # 暗号化されたAPIキー
    api_base_url = Column(String(500))  # カスタムAPIベースURL（オプション）
    default_model = Column(String(255))  # デフォルトモデル

    # ステータス
    is_enabled = Column(Boolean, default=False)  # 有効/無効
    is_default = Column(Boolean, default=False)  # デフォルトプロバイダー

    # 使用制限
    rate_limit_rpm = Column(Integer)  # 1分あたりのリクエスト制限
    rate_limit_tpd = Column(Integer)  # 1日あたりのトークン制限

    # メタデータ
    settings_metadata = Column(JSON, default={})  # その他の設定
    last_verified_at = Column(DateTime(timezone=True))  # 最後に検証された時刻
    last_used_at = Column(DateTime(timezone=True))  # 最後に使用された時刻

    # タイムスタンプ
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# User Agents Table
class UserAgent(Base):
    """User-Agent管理テーブル"""
    __tablename__ = "user_agents"

    id = Column(Integer, primary_key=True, index=True)
    user_agent_string = Column(String(1000), nullable=False, unique=True)
    browser_name = Column(String(100))
    browser_version = Column(String(50))
    os_name = Column(String(100))
    os_version = Column(String(50))
    device_type = Column(String(50))  # desktop, mobile, tablet
    is_active = Column(Boolean, default=True, index=True)
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


async def get_db():
    async with async_session_maker() as session:
        yield session
        await session.commit()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
