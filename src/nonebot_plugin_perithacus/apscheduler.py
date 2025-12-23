import asyncio
import json
import random
from functools import partial

from apscheduler.jobstores.base import JobLookupError
from apscheduler.triggers.cron import CronTrigger
from nonebot import logger
from nonebot_plugin_alconna import Target
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import get_session

from .database import Index, get_contents, get_cron_entries
from .lib import load_media


async def execute_cron_task(entry_id: int) -> None:
    """
    执行定时任务
    """
    logger.debug(f"执行定时任务，词条ID: {entry_id}")

    async with get_session() as session:
        existing_entry = await session.get(Index, entry_id)
        contents = await get_contents(session, entry_id)
        if existing_entry:
            if existing_entry.is_random:
                content = random.choice(contents)
                logger.debug(f"随机选择内容 ID {content.id} 进行发送")
            else:
                content = max(contents, key=lambda x: x.date_modified)
                logger.debug(f"选择最新内容 ID {content.id} 进行发送")
            for scope in json.loads(existing_entry.scope):
                target = Target.load(json.loads(existing_entry.target))
                if scope.startswith("g"):
                    target.id = scope[1:]
                    target.private = False
                elif scope.startswith("u"):
                    target.id = scope[1:]
                    target.private = True
                await load_media(content.content).send(target)
                await asyncio.sleep(random.uniform(0, 1))


async def load_cron_tasks() -> None:
    """
    从数据库加载所有带有cron表达式的任务
    """
    # 查询所有cron列有内容的行
    async with get_session() as session:
        entries = await get_cron_entries(session)

        # 为每个有cron表达式的词条创建定时任务
        if entries:
            logger.info(f"已加载 {len(entries)} 个定时任务")
            for entry in entries:
                logger.info(f"已加载定时任务，词条ID: {entry.id}")
                add_cron_job(entry.id, entry.cron) # pyright: ignore[reportArgumentType]
        else:
            logger.info("未找到定时任务")

def add_cron_job(
    entry_id: int,
    cron_expression: str
) -> None:
    """
    添加定时任务
    :param entry_id: 词条ID
    :param cron_expression: cron表达式
    """
    try:
        job_func = partial(execute_cron_task, entry_id)
        trigger = CronTrigger.from_crontab(cron_expression)
        scheduler.add_job(
            job_func,
            trigger = trigger,
            id = str(entry_id),
            replace_existing=True,
        )
        logger.debug(f"已添加定时任务 {entry_id}: {cron_expression}")
    except ValueError as e:
        logger.error(f"无效 cron 表达式 ({entry_id}): {cron_expression} - {e}")
    except TypeError as e:
        logger.error(f"任务参数错误 ({entry_id}, {cron_expression}): {e}")
    except RuntimeError as e:
        logger.error(f"调度器错误，无法添加任务 {entry_id}: {e}")

def remove_cron_job(entry_id: int) -> None:
    """
    移除定时任务
    :param entry_id: 词条ID
    """
    job_id = str(entry_id)
    try:
        scheduler.remove_job(job_id)
        logger.debug(f"已移除定时任务: {entry_id}")
    except JobLookupError:
        # 任务不存在 —— 这是正常情况，比如任务已被手动删除
        logger.warning(f"尝试移除不存在的定时任务: {entry_id}")
    except RuntimeError as e:
        # 调度器未运行（如插件正在关闭）
        logger.error(f"调度器不可用，无法移除任务 {entry_id}: {e}")
