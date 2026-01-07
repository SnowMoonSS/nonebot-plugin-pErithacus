from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nonebot import logger

from .apscheduler import add_cron_job, remove_cron_job
from .lib import get_cron, get_num_list

if TYPE_CHECKING:
    from nonebot.adapters import Message
    from nonebot_plugin_alconna import Match, UniMessage

    from .database import Index


def handle_match_method(update_kwargs: dict, match_method: Match) -> dict:
    if match_method.available:
        update_kwargs["match_method"] = match_method.result
    return update_kwargs

def handle_is_random(update_kwargs: dict, is_random: Match) -> dict:
    if is_random.available:
        update_kwargs["is_random"] = is_random.result
    return update_kwargs

async def handle_cron(
    update_kwargs: dict,
    entry: Index,
    cron: Match
) -> dict:
    if cron.available:
        cron_expressions = await get_cron(cron)
        update_kwargs["cron"] = cron_expressions
        if cron_expressions:
            add_cron_job(entry.id, cron_expressions)
        else:
            remove_cron_job(entry.id)
    return update_kwargs

def handle_scope(
    update_kwargs: dict,
    scope_list: list,
    entry: Index,
    scope: Match
) -> dict:
    """
    合并新旧 scope 列表，避免重复，并更新到 update_kwargs
    """
    if scope.available:
        try:
            scope_list_from_db = json.loads(entry.scope) if entry.scope else []
        except json.JSONDecodeError:
            scope_list_from_db = []
        for item in scope_list:
            if item not in scope_list_from_db:
                scope_list_from_db.append(item)
        update_kwargs["scope"] = json.dumps(scope_list_from_db)
        logger.debug(
            f"输入的作用域与数据库中的记录合并但还没写入数据库: {scope_list_from_db}"
        )
    return update_kwargs

def handle_alias(
    update_kwargs: dict,
    alias_text: str,
    entry: Index,
    alias: Match
) -> dict:
    if alias.available:
        # 解析已有别名列表
        alias_list = json.loads(entry.alias) if entry.alias else []
        new_alias = alias_text
        if new_alias and new_alias not in alias_list:
            alias_list.append(new_alias)
        update_kwargs["alias"] = json.dumps(alias_list) if alias_list else None
    return update_kwargs

def handle_reg(update_kwargs: dict, reg: Match) -> dict:
    if reg.available:
        update_kwargs["reg"] = reg.result
    return update_kwargs

async def handle_del_alias(
    update_kwargs: dict,
    del_alias_id: Match,
    entry: Index
) -> dict:
    if del_alias_id.available:
        try:
            alias_list = json.loads(entry.alias) if entry.alias else []
        except json.JSONDecodeError:
            alias_list = []
        ids_to_delete = await get_num_list(del_alias_id.result)
        # 过滤掉无效的序号
        ids_to_delete = [i for i in ids_to_delete if 1 <= i <= len(alias_list)]
        # 根据序号删除对应的别名，注意序号是从1开始的
        alias_list = [
            alias for idx, alias in enumerate(alias_list, start=1)
            if idx not in ids_to_delete
        ]
        update_kwargs["alias"] = json.dumps(alias_list) if alias_list else None
    return update_kwargs

@dataclass
class MainArgs:
    keyword: UniMessage
    content: UniMessage

def handle_main_args(
    msg: UniMessage,
    sub_command: str,
) -> MainArgs:
    """
    从消息中提取 keyword 和 content 参数
    """
    msg_text = msg.dump(json=True)
