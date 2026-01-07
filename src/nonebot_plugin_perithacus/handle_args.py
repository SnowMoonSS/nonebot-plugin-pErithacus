from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nonebot import logger
from nonebot_plugin_alconna import Arparma, UniMessage

from .apscheduler import add_cron_job, remove_cron_job
from .lib import get_cron, get_num_list

if TYPE_CHECKING:
    from nonebot_plugin_alconna import Match

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

async def handle_main_args(
    msg: UniMessage,
    sub_command: str,
) -> MainArgs | None:
    """
    从消息中提取 keyword 和 content 参数
    """
    removed_prefix_msg = msg.removeprefix(f"pe {sub_command} ")
    onebot_v11_msg = await removed_prefix_msg.export(adapter="OneBot V11")

    options_r = r"\s(?:-|--)(?:m|match|r|random|c|cron|s|scope|g|reg|a|alias)\s+\S+(?=$|\s)"
    matched_options = re.findall(options_r, str(onebot_v11_msg))
    for option in matched_options:
        removed_prefix_msg = removed_prefix_msg.replace(option, "")
    clean_msg = removed_prefix_msg
    logger.debug(f"去除选项后的消息: {clean_msg}")
    msg_text = clean_msg.dump(json=True)
    logger.debug(f"需要处理的消息: {msg_text}")

    onebot_v11_msg = re.sub(options_r, "", str(onebot_v11_msg)).strip()
    main_args_r = r'^(?:"([^"]+)"|(\S+))\s+(?:"([^"]+)"|(.*))$'
    match = re.match(main_args_r, onebot_v11_msg)
    if not match:
        return None
    keyword = match.group(1) or match.group(2)
    content = match.group(3) or match.group(4)
    uni_keyword = UniMessage(keyword)
    uni_content = UniMessage(content)
    return MainArgs(uni_keyword, uni_content)
