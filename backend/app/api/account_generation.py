from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
import secrets
import string

from ..models.database import (
    get_db,
    AccountGenerationTask,
    GeneratedAccount,
    TaskLog,
    LogLevelEnum,
    PlatformEnum,
    AccountGenStatusEnum,
    StatusEnum,
    ExecutionModeEnum
)
from ..services.audit_service import audit_log

router = APIRouter()


# Pydantic Models
class AccountGenerationTaskCreate(BaseModel):
    platform: str
    target_count: int = Field(ge=1, le=1_000_000)
    persona_id: Optional[int] = None
    username_pattern: str = "user_{}"
    email_domain: str = "gmail.com"
    phone_provider: Optional[str] = None
    proxy_list: List[str] = []
    use_residential_proxy: bool = True
    use_brightdata: bool = False
    brightdata_zone: Optional[str] = None
    use_mulogin: bool = True
    mulogin_group_id: Optional[str] = None
    batch_size: int = 100
    headless: bool = True
    execution_mode: str = "selenium"  # "requests" or "selenium"


def generate_username(pattern: str, index: int) -> str:
    """
    Generate username based on pattern
    Pattern examples:
    - "user_{}" -> user_1, user_2, ...
    - "test_{:04d}" -> test_0001, test_0002, ...
    - "random" -> random string
    """
    if pattern == "random":
        return ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(12))
    return pattern.format(index)


def generate_email(domain: str, username: str) -> str:
    """Generate email address"""
    return f"{username}@{domain}"


def generate_password(length: int = 16) -> str:
    """Generate secure random password"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


@router.post("/account-generation/tasks")
async def create_generation_task(
    task_data: AccountGenerationTaskCreate,
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    ペルソナベースアカウント生成タスク作成

    大規模生成対応: 1 ~ 1,000,000 アカウント
    """
    # Validate platform
    try:
        platform_enum = PlatformEnum[task_data.platform.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid platform: {task_data.platform}")

    # Validate execution mode
    try:
        execution_mode_enum = ExecutionModeEnum[task_data.execution_mode.upper()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid execution_mode: {task_data.execution_mode}. Must be 'requests' or 'selenium'")

    # Create generation task
    task = AccountGenerationTask(
        platform=platform_enum,
        persona_id=task_data.persona_id,
        target_count=task_data.target_count,
        batch_size=task_data.batch_size,
        generation_config={
            "username_pattern": task_data.username_pattern,
            "email_domain": task_data.email_domain,
            "phone_provider": task_data.phone_provider,
        },
        proxy_list=task_data.proxy_list,
        use_residential_proxy=task_data.use_residential_proxy,
        use_brightdata=task_data.use_brightdata,
        brightdata_zone=task_data.brightdata_zone,
        use_mulogin=task_data.use_mulogin,
        mulogin_group_id=task_data.mulogin_group_id,
        headless=task_data.headless,
        execution_mode=execution_mode_enum,
        status=AccountGenStatusEnum.PENDING,
        created_by=1  # TODO: Get from authenticated user
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Audit log
    if request:
        await audit_log(
            actor_user_id=1,
            operation="create_account_generation_task",
            payload={
                "task_id": task.id,
                "platform": task_data.platform,
                "target_count": task_data.target_count,
            },
            session=db,
            ip_address=request.client.host if request.client else None
        )

    return {
        "success": True,
        "task_id": task.id,
        "status": task.status.value
    }


@router.get("/account-generation/tasks")
async def list_generation_tasks(
    platform: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """
    List account generation tasks
    """
    query = select(AccountGenerationTask).order_by(AccountGenerationTask.created_at.desc())

    if platform:
        try:
            platform_enum = PlatformEnum[platform.upper()]
            query = query.where(AccountGenerationTask.platform == platform_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid platform: {platform}")

    if status:
        try:
            status_enum = AccountGenStatusEnum[status.upper()]
            query = query.where(AccountGenerationTask.status == status_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    query = query.limit(limit)
    result = await db.execute(query)
    tasks = result.scalars().all()

    return {
        "tasks": [
            {
                "id": task.id,
                "platform": task.platform.value,
                "target_count": task.target_count,
                "completed_count": task.completed_count,
                "failed_count": task.failed_count,
                "status": task.status.value,
                "execution_mode": task.execution_mode.value,
                "generation_config": task.generation_config,
                "proxy_list": task.proxy_list,
                "use_residential_proxy": task.use_residential_proxy,
                "headless": task.headless,
                "error_message": task.error_message,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "started_at": task.started_at.isoformat() if task.started_at else None,
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            }
            for task in tasks
        ]
    }


@router.get("/account-generation/tasks/{task_id}")
async def get_generation_task(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get specific generation task with generated accounts
    """
    result = await db.execute(
        select(AccountGenerationTask).where(AccountGenerationTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get generated accounts for this task
    accounts_result = await db.execute(
        select(GeneratedAccount).where(GeneratedAccount.task_id == task_id)
    )
    accounts = accounts_result.scalars().all()

    return {
        "task": {
            "id": task.id,
            "platform": task.platform.value,
            "target_count": task.target_count,
            "completed_count": task.completed_count,
            "failed_count": task.failed_count,
            "status": task.status.value,
            "generation_config": task.generation_config,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        },
        "accounts": [
            {
                "id": acc.id,
                "username": acc.username,
                "email": acc.email,
                "phone": acc.phone,
                "proxy_used": acc.proxy_used,
                "ip_address": acc.ip_address,
                "verification_status": acc.verification_status,
                "status": acc.status.value,
                "created_at": acc.created_at.isoformat() if acc.created_at else None,
                "verified_at": acc.verified_at.isoformat() if acc.verified_at else None,
            }
            for acc in accounts
        ]
    }


@router.post("/account-generation/tasks/{task_id}/start")
async def start_generation_task(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Start account generation task (would trigger worker in production)
    """
    result = await db.execute(
        select(AccountGenerationTask).where(AccountGenerationTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != AccountGenStatusEnum.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Task cannot be started from status: {task.status.value}"
        )

    # Update task status
    task.status = AccountGenStatusEnum.GENERATING
    task.started_at = datetime.now()
    await db.commit()

    # Create initial log entry
    initial_log = TaskLog(
        task_id=task.id,
        level=LogLevelEnum.INFO,
        message=f"タスク開始: {task.target_count}件のアカウント生成を開始します",
        details={
            "platform": task.platform.value,
            "batch_size": task.batch_size,
            "use_mulogin": task.use_mulogin,
            "use_brightdata": task.use_brightdata
        }
    )
    db.add(initial_log)
    await db.commit()

    # In production, this would enqueue the task to a worker
    # For now, we'll simulate by creating pending accounts

    # Audit log
    await audit_log(
        actor_user_id=1,
        operation="start_account_generation_task",
        payload={
            "task_id": task.id,
        },
        session=db,
        ip_address=request.client.host if request.client else None
    )

    return {
        "success": True,
        "task_id": task.id,
        "status": task.status.value,
        "message": "Task started. Accounts will be generated in the background."
    }


@router.post("/account-generation/tasks/{task_id}/cancel")
async def cancel_generation_task(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel account generation task
    """
    result = await db.execute(
        select(AccountGenerationTask).where(AccountGenerationTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in [AccountGenStatusEnum.COMPLETED, AccountGenStatusEnum.FAILED]:
        raise HTTPException(
            status_code=400,
            detail=f"Task cannot be cancelled from status: {task.status.value}"
        )

    # Update task status
    task.status = AccountGenStatusEnum.SUSPENDED
    await db.commit()

    # Audit log
    await audit_log(
        actor_user_id=1,
        operation="cancel_account_generation_task",
        payload={
            "task_id": task.id,
        },
        session=db,
        ip_address=request.client.host if request.client else None
    )

    return {
        "success": True,
        "task_id": task.id,
        "status": task.status.value,
        "message": "Task cancelled."
    }


@router.post("/account-generation/tasks/{task_id}/resume")
async def resume_generation_task(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Resume suspended account generation task
    """
    result = await db.execute(
        select(AccountGenerationTask).where(AccountGenerationTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status != AccountGenStatusEnum.SUSPENDED:
        raise HTTPException(
            status_code=400,
            detail=f"Task cannot be resumed from status: {task.status.value}"
        )

    # Update task status
    task.status = AccountGenStatusEnum.GENERATING
    await db.commit()

    # Create log entry
    resume_log = TaskLog(
        task_id=task.id,
        level=LogLevelEnum.INFO,
        message=f"タスク再開: {task.target_count - task.completed_count - task.failed_count}件のアカウント生成を再開します",
        details={
            "completed_count": task.completed_count,
            "failed_count": task.failed_count,
            "remaining_count": task.target_count - task.completed_count - task.failed_count
        }
    )
    db.add(resume_log)
    await db.commit()

    # Audit log
    await audit_log(
        actor_user_id=1,
        operation="resume_account_generation_task",
        payload={
            "task_id": task.id,
        },
        session=db,
        ip_address=request.client.host if request.client else None
    )

    return {
        "success": True,
        "task_id": task.id,
        "status": task.status.value,
        "message": "Task resumed. Accounts will continue to be generated in the background."
    }


@router.delete("/account-generation/tasks/{task_id}")
async def delete_generation_task(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete account generation task
    """
    result = await db.execute(
        select(AccountGenerationTask).where(AccountGenerationTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Delete associated generated accounts first
    accounts_result = await db.execute(
        select(GeneratedAccount).where(GeneratedAccount.task_id == task_id)
    )
    accounts = accounts_result.scalars().all()

    for account in accounts:
        await db.delete(account)

    await db.delete(task)
    await db.commit()

    # Audit log
    await audit_log(
        actor_user_id=1,
        operation="delete_account_generation_task",
        payload={
            "task_id": task.id,
            "deleted_accounts_count": len(accounts)
        },
        session=db,
        ip_address=request.client.host if request.client else None
    )

    return {
        "success": True,
        "message": f"Task {task_id} and {len(accounts)} accounts deleted"
    }


@router.get("/account-generation/accounts")
async def list_generated_accounts(
    platform: Optional[str] = None,
    task_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    List generated accounts
    """
    query = select(GeneratedAccount).order_by(GeneratedAccount.created_at.desc())

    if platform:
        try:
            platform_enum = PlatformEnum[platform.upper()]
            query = query.where(GeneratedAccount.platform == platform_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid platform: {platform}")

    if task_id:
        query = query.where(GeneratedAccount.task_id == task_id)

    if status:
        try:
            status_enum = StatusEnum[status.upper()]
            query = query.where(GeneratedAccount.status == status_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    query = query.limit(limit)
    result = await db.execute(query)
    accounts = result.scalars().all()

    return {
        "accounts": [
            {
                "id": acc.id,
                "task_id": acc.task_id,
                "platform": acc.platform.value,
                "username": acc.username,
                "email": acc.email,
                "password": acc.password_encrypted,  # TODO: Decrypt if encrypted
                "phone": acc.phone,
                "proxy_used": acc.proxy_used,
                "verification_status": acc.verification_status,
                "status": acc.status.value,
                "created_at": acc.created_at.isoformat() if acc.created_at else None,
                "verified_at": acc.verified_at.isoformat() if acc.verified_at else None,
                "last_login": acc.last_login.isoformat() if acc.last_login else None,
            }
            for acc in accounts
        ]
    }


@router.get("/account-generation/tasks/{task_id}/logs")
async def get_task_logs(
    task_id: int,
    limit: int = 100,
    since: Optional[int] = None,
    level: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    タスクのリアルタイムログを取得
    
    - limit: 取得するログの最大数（デフォルト100）
    - since: このLog ID以降のログのみ取得（ポーリング用）
    - level: ログレベルフィルター（debug, info, warning, error, success）
    """
    result = await db.execute(
        select(AccountGenerationTask).where(AccountGenerationTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    query = select(TaskLog).where(TaskLog.task_id == task_id)

    if since:
        query = query.where(TaskLog.id > since)

    if level:
        try:
            level_enum = LogLevelEnum[level.upper()]
            query = query.where(TaskLog.level == level_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid level: {level}")

    query = query.order_by(TaskLog.created_at.asc()).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "task_id": task_id,
        "task_status": task.status.value,
        "completed_count": task.completed_count,
        "failed_count": task.failed_count,
        "target_count": task.target_count,
        "logs": [
            {
                "id": log.id,
                "level": log.level.value,
                "message": log.message,
                "details": log.details,
                "account_index": log.account_index,
                "account_username": log.account_username,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }


@router.get("/account-generation/tasks/{task_id}/progress")
async def get_task_progress(
    task_id: int,
    db: AsyncSession = Depends(get_db)
):
    """タスクの進捗情報を取得（軽量版、ポーリング用）"""
    result = await db.execute(
        select(AccountGenerationTask).where(AccountGenerationTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    latest_log_result = await db.execute(
        select(TaskLog)
        .where(TaskLog.task_id == task_id)
        .order_by(TaskLog.created_at.desc())
        .limit(1)
    )
    latest_log = latest_log_result.scalar_one_or_none()

    return {
        "task_id": task_id,
        "status": task.status.value,
        "completed_count": task.completed_count,
        "failed_count": task.failed_count,
        "target_count": task.target_count,
        "progress_percentage": round((task.completed_count + task.failed_count) / task.target_count * 100, 2) if task.target_count > 0 else 0,
        "current_batch": task.current_batch,
        "total_batches": (task.target_count + task.batch_size - 1) // task.batch_size,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "latest_log": {
            "id": latest_log.id,
            "level": latest_log.level.value,
            "message": latest_log.message,
            "created_at": latest_log.created_at.isoformat()
        } if latest_log else None
    }
