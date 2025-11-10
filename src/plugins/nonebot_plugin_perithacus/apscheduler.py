import random
import json
import asyncio

from sqlalchemy import select
from nonebot import logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import get_session
from nonebot_plugin_alconna import Target

from .database import Index, get_contents
from .lib import load_media

async def execute_cron_task(
    entry_id: int
):
    """
    执行定时任务
    """
    logger.debug(f"执行定时任务，词条ID: {entry_id}")

    session = get_session()
    existing_entry = await session.get(Index, id)
    contents = await get_contents(entry_id)
    if existing_entry:
        if existing_entry.isRandom:
            content = random.choice(contents)
            logger.debug(f"随机选择内容 ID {content.id} 进行发送")
        else:
            content = max(contents, key=lambda x: x.timap)
            logger.debug(f"选择最新内容 ID {content.id} 进行发送")
        for scope in json.loads(existing_entry.scope):
            target = Target.load(json.loads(existing_entry.target))
            if scope.startswith("g"):
                target.id = scope[1:]
                target.private = False
                await load_media(content.content).send(target)
            elif scope.startswith("u"):
                target.id = scope[1:]
                target.private = True
                await load_media(content.content).send(target)
            await asyncio.sleep(random.uniform(0, 1))
    await session.close()
            

async def load_cron_tasks():
    """
    从数据库加载所有带有cron表达式的任务
    """
    session = get_session()
    # 查询所有cron列有内容的行
    result = await session.execute(
        select(Index).where(Index.cron.isnot(None))
    )
    entries = result.scalars().all()
    
    # 为每个有cron表达式的词条创建定时任务
    if entries:
        logger.info(f"已加载 {len(entries)} 个定时任务")
        for entry in entries:
            logger.info(f"已加载定时任务，词条ID: {entry.id}")
            add_cron_job(entry.id, entry.cron) # type: ignore
    else:
        logger.info("未找到定时任务")
    await session.close()

def add_cron_job(entry_id: int, cron_expression: str):
    """
    添加定时任务
    :param entry_id: 词条ID
    :param cron_expression: cron表达式
    """
    try:
        scheduler.add_job(
            execute_cron_task(entry_id),
            trigger = cron_expression,
            id = entry_id,
            replace_existing=True,
        )
        logger.debug(f"已添加定时任务 {entry_id}: {cron_expression}")
    except Exception as e:
        logger.error(f"添加定时任务失败: {e}")

def remove_cron_job(entry_id: int):
    """
    移除定时任务
    :param entry_id: 词条ID
    """
    try:
        scheduler.remove_job(entry_id)
        logger.debug(f"已移除定时任务: {entry_id}")
    except Exception as e:
        logger.error(f"移除定时任务 {entry_id} 失败: {e}")