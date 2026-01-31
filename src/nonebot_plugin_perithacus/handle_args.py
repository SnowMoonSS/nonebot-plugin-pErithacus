from __future__ import annotations

import codecs
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from nonebot import logger
from nonebot_plugin_alconna import Text, UniMessage

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
    alias: UniMessage | None

def get_part_text(msg_text: str) -> list[str]:
    pattern = r"\[[^\]]*\]"
    matches = list(re.finditer(pattern, msg_text))

    parts = []
    last_end = 0

    for match in matches:
        start, end = match.start(), match.end()
        if start > last_end:  # 有非空的[]前部分
            parts.append(msg_text[last_end:start])
        parts.append(match.group())
        last_end = end

    if last_end < len(msg_text):  # 最后还有剩余部分
        parts.append(msg_text[last_end:])

    return parts

def get_part_keyword(msg_text: str) -> str:
    logger.debug(f"输入的文本: {msg_text}")
    if msg_text.startswith(" "):
        pattern = r"\s\S"
        matches = list(re.finditer(pattern, msg_text))
        keyword = msg_text[:matches[1].start()] if matches[1] else msg_text
    elif msg_text.startswith('"'):
        pattern = r'"((?:[^"\\]|\\.)*)"'
        match = re.match(pattern, msg_text)
        if match:
            keyword = match.group(1)
            logger.debug(f"解码转义字符前: {keyword}")
            keyword = codecs.decode(keyword, "unicode_escape")
        else:
            matches = list(re.finditer(r"\s\S", msg_text))
            keyword = msg_text[:matches[0].start()] if matches[0] else msg_text
    else:
        pattern = r"\s\S"
        matches = list(re.finditer(pattern, msg_text))
        keyword = msg_text[:matches[0].start()] if matches[0] else msg_text

    return keyword

def get_part_content(msg_text: str) -> str:
    content = ""
    param_pattern = re.compile(r'\s(?:-a|--alias)\s+(?:"((?:[^"\\]|\\.)*)"|(\S+))')
    if msg_text.startswith(" "):
        pattern = r"\s\S"
        matches = list(re.finditer(pattern, msg_text))
        start_index = matches[1].start()
        sub_string = msg_text[start_index:]
        clean_content = param_pattern.sub("", sub_string)
        content = clean_content.removeprefix(" ") if clean_content.startswith(" ") else clean_content
    elif msg_text.startswith('"'):
        pattern = r'"(?:[^"\\]|\\.)*"'
        match = re.match(pattern, msg_text)
        if match:
            end_pos = match.end()
            content = msg_text[end_pos:]
            clean_content = param_pattern.sub("", content)
            content = clean_content.removeprefix(" ") if clean_content.startswith(" ") else clean_content
    else:
        matches = list(re.finditer(r"\s\S", msg_text))
        start_index = matches[0].start()
        sub_string = msg_text[start_index:]
        clean_content = param_pattern.sub("", sub_string)
        content = clean_content.removeprefix(" ") if clean_content.startswith(" ") else clean_content
    return content

def get_part_alias(msg_text: str) -> str | None:
    pattern = r'\s(?:-a|--alias)\s+(?:"((?:[^"\\]|\\.)*)"|(\S+))'
    match = re.search(pattern, msg_text)

    if not match:
        return None

    if match.group(1):
        alias = match.group(1)
        alias = codecs.decode(alias, "unicode_escape")
    else:
        alias = match.group(2)

    return alias

async def handle_main_args(msg: UniMessage, sub_command: str) -> MainArgs:
    removed_prefix_msg = msg.removeprefix(f"pe {sub_command} ")
    onebot_v11_msg = await removed_prefix_msg.export(adapter="OneBot V11")

    # 去除 alias 选项以外的其它选项
    if sub_command == "add":
        options_r = (
            r"\s(?:-m|--match|-r|--random|-c|--cron|-s|--scope|-g|--reg)\s+\S+(?=$|\s)"
        )
    elif sub_command == "del":
        options_r = (
            r"\s(?:-s|--scope)\s+\S+(?=$|\s)"
        )
    elif sub_command == "search":
        options_r = (
            r"\s(?:-s|--scope|-a|--all)\s+\S+(?=$|\s)"
        )
    elif sub_command == "edit":
        options_r = (
            r"\s(?:-m|--match|-r|--random|-c|--cron|-s|--scope|-g|--reg|-A|--del-alias|-C|--del_content|-p|--replace)\s+\S+(?=$|\s)"
        )
    matched_options = re.findall(options_r, str(onebot_v11_msg)) # pyright: ignore[reportPossiblyUnboundVariable]
    for option in matched_options:
        removed_prefix_msg = removed_prefix_msg.replace(option, "")
    clean_msg = removed_prefix_msg.replace("[", "《《《《").replace("]", "》》》》")
    msg_text = str(clean_msg)
    logger.debug(f"clean_msg: {clean_msg.dump(json=True)}")

    # 从消息中提取所有非文本消息段
    not_text_segments = clean_msg.exclude(Text)
    logger.debug(f"not_text_segments: {not_text_segments.dump(json=True)}")

    logger.debug(f"msg_text: {msg_text}")
    not_text_segment_index = 0

    keyword = get_keyword(msg_text, not_text_segments, not_text_segment_index)

    content = get_content(msg_text, not_text_segments, not_text_segment_index)

    alias = get_alias(msg_text, not_text_segments, not_text_segment_index)

    return MainArgs(keyword, content, alias)

def get_keyword(
    msg_text: str,
    not_text_segments: list,
    not_text_segment_index: int
) -> UniMessage:
    keyword = UniMessage()
    keyword_text = get_part_keyword(msg_text)
    logger.debug(f"keyword_text: {keyword_text}")
    keyword_part_text = get_part_text(keyword_text)
    for part in keyword_part_text:
        if part.startswith("["):
            keyword.append(not_text_segments[not_text_segment_index])
            not_text_segment_index += 1
        else:
            keyword.append(part)
    return keyword.replace("《《《《", "[").replace("》》》》", "]")

def get_content(
    msg_text: str,
    not_text_segments: list,
    not_text_segment_index: int
) -> UniMessage:
    content = UniMessage()
    content_text = get_part_content(msg_text)
    logger.debug(f"content_text: {content_text}")
    content_part_text = get_part_text(content_text)
    logger.debug(f"content_part_text: {content_part_text}")
    for part in content_part_text:
        if part.startswith("["):
            content.append(not_text_segments[not_text_segment_index])
            not_text_segment_index += 1
        else:
            content.append(part)
    return content.replace("《《《《", "[").replace("》》》》", "]")

def get_alias(
    msg_text: str,
    not_text_segments: list,
    not_text_segment_index: int
) -> UniMessage | None:
    alias = UniMessage()
    alias_text = get_part_alias(msg_text)
    if not alias_text:
        return None
    alias_part_text = get_part_text(alias_text)
    for part in alias_part_text:
        if part.startswith("["):
            alias.append(not_text_segments[not_text_segment_index])
            not_text_segment_index += 1
        else:
            alias.append(part)
    return alias.replace("《《《《", "[").replace("》》》》", "]")


