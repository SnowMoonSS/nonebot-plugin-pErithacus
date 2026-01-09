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

@dataclass
class NotTextSegmentIndex:
    parts: dict
    indices: list

def find_bracket_positions(msg_text: str) -> NotTextSegmentIndex:
    pattern = r"\[[^\]]*\]"
    matches = list(re.finditer(pattern, msg_text))

    parts = {}
    indices = []
    last_end = 0
    i = 0

    for match in matches:
        start, end = match.start(), match.end()
        if start > last_end:  # 有非空的[]前部分
            parts[i] = msg_text[last_end:start]
            i += 1
        parts[i] = match.group()
        indices.append(i)
        i += 1
        last_end = end

    if last_end < len(msg_text):  # 最后还有剩余部分
        parts[i] = msg_text[last_end:]

    return NotTextSegmentIndex(parts, indices)

@dataclass
class PartText:
    start_at: int
    end_at: int
    text: str

@dataclass
class PartNotText:
    start_at: int
    end_at: int
    not_text: str

@dataclass
class PartKeyword:
    start_at: int
    end_at: int
    keyword: str

@dataclass
class PartContent:
    start_at: int
    end_at: int
    content: str

@dataclass
class PartAlias:
    start_at: int
    end_at: int
    alias: str

def get_part_text(msg_text: str) -> list[PartText]:
    pattern = r"\[[^\]]*\]"
    matches = list(re.finditer(pattern, msg_text))

    parts = []
    last_end = 0

    for match in matches:
        start, end = match.start(), match.end()
        if start > last_end:  # 有非空的[]前部分
            parts.append(PartText(last_end, start, msg_text[last_end:start]))
        last_end = end

    if last_end < len(msg_text):  # 最后还有剩余部分
        parts.append(PartText(last_end, len(msg_text), msg_text[last_end:]))

    return parts

def get_part_not_text(msg_text: str) -> list[PartNotText]:
    pattern = r"\[[^\]]*\]"
    matches = list(re.finditer(pattern, msg_text))

    parts = []

    for match in matches:
        start, end = match.start(), match.end()
        parts.append(PartNotText(start, end, match.group()))

    return parts

def get_part_keyword(msg_text: str) -> PartKeyword:
    pattern = r'^(?:"((?:[^"\\]|\\.)*)"|(\S+))\s+(?:"((?:[^"\\]|\\.)*)"|(\S+))$'
    match = re.match(pattern, msg_text)

    if not match:
        raise ValueError("参数格式错误")

    start_at = match.start(1) or match.start(2)
    end_at = match.end(1) or match.end(2)
    keyword = codecs.decode(match.group(1), "unicode_escape") or match.group(2)

    return PartKeyword(start_at, end_at, keyword)

def get_part_content(msg_text: str) -> PartContent:
    pattern = r'^(?:"((?:[^"\\]|\\.)*)"|(\S+))\s+(?:"((?:[^"\\]|\\.)*)"|(\S+))$'
    match = re.match(pattern, msg_text)

    if not match:
        raise ValueError("参数格式错误")

    start_at = match.start(3) or match.start(4)
    end_at = match.end(3) or match.end(4)
    content = codecs.decode(match.group(3), "unicode_escape") or match.group(4)

    return PartContent(start_at, end_at, content)

async def handle_main_args(msg: UniMessage, sub_command: str) -> MainArgs:
    removed_prefix_msg = msg.removeprefix(f"pe {sub_command} ")
    onebot_v11_msg = await removed_prefix_msg.export(adapter="OneBot V11")

    # 去除 alias 选项以外的其它选项
    options_r = (
        r"\s(?:-m|--match|-r|--random|-c|--cron|-s|--scope|-g|--reg)\s+\S+(?=$|\s)"
    )
    matched_options = re.findall(options_r, str(onebot_v11_msg))
    for option in matched_options:
        removed_prefix_msg = removed_prefix_msg.replace(option, "")
    clean_msg = removed_prefix_msg.replace("[", "《《《《").replace("]", "》》》》")

    # 从消息中提取所有非文本消息段
    not_text_segments = clean_msg.exclude(Text)

    msg_text = str(clean_msg)
    not_text_segment_index = 0

    keyword = get_keyword(msg_text, not_text_segments, not_text_segment_index)

    content = get_content(msg_text, not_text_segments, not_text_segment_index)

    alias = get_alias(msg_text, not_text_segments, not_text_segment_index)

    return MainArgs(keyword, content, alias)

def get_part_alias(msg_text: str) -> PartAlias | None:
    pattern = r'\s(?:-a|--alias)\s+(?:"((?:[^"\\]|\\.)*)"|(\S+))'
    match = re.search(pattern, msg_text)

    if not match:
        return None

    start_at = match.start()
    end_at = match.end()
    alias = codecs.decode(match.group(1), "unicode_escape") or match.group(2)

    return PartAlias(start_at, end_at, alias)

def get_keyword(
    msg_text: str,
    not_text_segments: list,
    not_text_segment_index: int
) -> UniMessage:
    keyword = UniMessage()
    keyword_text = get_part_keyword(msg_text)
    keyword_part_text = get_part_text(keyword_text.keyword)
    for part in keyword_part_text:
        if part.text.startswith("["):
            keyword.append(part.text)
        else:
            keyword.append(not_text_segments[not_text_segment_index])
            not_text_segment_index += 1
    return keyword.replace("《《《《", "[").replace("》》》》", "]")

def get_content(
    msg_text: str,
    not_text_segments: list,
    not_text_segment_index: int
) -> UniMessage:
    content = UniMessage()
    content_text = get_part_content(msg_text)
    content_part_text = get_part_text(content_text.content)
    for part in content_part_text:
        if part.text.startswith("["):
            content.append(part.text)
        else:
            content.append(not_text_segments[not_text_segment_index])
            not_text_segment_index += 1
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
    alias_part_text = get_part_text(alias_text.alias)
    for part in alias_part_text:
        if part.text.startswith("["):
            alias.append(part.text)
        else:
            alias.append(not_text_segments[not_text_segment_index])
            not_text_segment_index += 1
    return alias.replace("《《《《", "[").replace("》》》》", "]")
