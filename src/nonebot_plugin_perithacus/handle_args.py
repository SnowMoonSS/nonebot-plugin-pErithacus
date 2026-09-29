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

def get_part_text(msg_text: str | None) -> list[str]:
    if not msg_text:
        return []
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

def count_placeholders_before(msg_text: str, offset: int) -> int:
    """
    统计 msg_text 中 offset 之前出现的非文本段占位符个数。
    msg_text 中第 i 个占位符对应 not_text_segments[i]，
    因此返回值即为 offset 处第一个占位符对应的下标
    """
    return len(re.findall(r"\[[^\]]*\]", msg_text[:offset]))

def unescape_text(text: str) -> str:
    """
    解码文本中的转义字符，如 \\n、\\"。
    不能直接使用 codecs.decode(text, "unicode_escape")，
    它会先把文本当作 latin-1 编码，令中文等多字节字符变成乱码
    """
    return codecs.decode(text.encode("latin-1", "backslashreplace"), "unicode_escape")

def get_part_keyword(msg_text: str) -> str:
    logger.debug(f"输入的文本: {msg_text}")
    if msg_text.startswith(" "):
        # 命令与关键词之间有多余空格，忽略之
        msg_text = msg_text.lstrip()
    if msg_text.startswith('"'):
        pattern = r'"((?:[^"\\]|\\.)*)"'
        match = re.match(pattern, msg_text)
        if match:
            keyword = match.group(1)
            logger.debug(f"解码转义字符前: {keyword}")
            keyword = unescape_text(keyword)
        else:
            matches = list(re.finditer(r"\s\S", msg_text))
            keyword = msg_text[:matches[0].start()] if matches else msg_text
    else:
        matches = list(re.finditer(r"\s\S", msg_text))
        keyword = msg_text[:matches[0].start()] if matches else msg_text

    return keyword

def get_part_content(msg_text: str) -> tuple[str, int]:
    """
    返回 (回复内容文本, 该文本在 msg_text 中的起始位置)。
    起始位置用于推算内容中非文本段对应的下标，不能当作 0 处理
    """
    if msg_text.startswith(" "):
        # 命令与关键词之间有多余空格，忽略之
        msg_text = msg_text.lstrip()
    if msg_text.startswith('"'):
        pattern = r'"(?:[^"\\]|\\.)*"'
        match = re.match(pattern, msg_text)
        if not match:
            return "", 0
        start_index = match.end()
    else:
        matches = list(re.finditer(r"\s\S", msg_text))
        if not matches:
            return "", 0
        start_index = matches[0].start()

    param_pattern = re.compile(r'\s(?:-a|--alias)\s+(?:"((?:[^"\\]|\\.)*)"|(\S+))')
    clean_content = param_pattern.sub("", msg_text[start_index:])
    content = clean_content.removeprefix(" ") if clean_content.startswith(" ") else clean_content
    return content, start_index

def get_part_alias(msg_text: str) -> tuple[str, int] | None:
    """
    返回 (别名文本, 别名值在 msg_text 中的起始位置)，未提供别名时返回 None
    """
    pattern = r'\s(?:-a|--alias)\s+(?:"((?:[^"\\]|\\.)*)"|(\S+))'
    match = re.search(pattern, msg_text)

    if not match:
        return None

    if match.group(1):
        return unescape_text(match.group(1)), match.start(1)

    return match.group(2), match.start(2)

async def handle_main_args(msg: UniMessage, sub_command: str) -> MainArgs:
    # 去掉消息开头的「命令名 + 子命令」，例如 "pe del "、"perithacus 删除 "。
    # 不能写死为 f"pe {sub_command} "，否则命令别名（perithacus、中文子命令）解析会出错
    prefix_pattern = re.compile(r"^\S+\s+\S+\s*")
    removed_prefix_msg = msg
    if removed_prefix_msg and isinstance(removed_prefix_msg[0], Text):
        first_segment = removed_prefix_msg[0]
        matched_prefix = prefix_pattern.match(first_segment.text)
        if matched_prefix:
            segments = list(removed_prefix_msg)
            rest_text = first_segment.text[matched_prefix.end():]
            if rest_text:
                segments[0] = Text(rest_text)
            else:
                segments.pop(0)
            removed_prefix_msg = UniMessage(segments)
    logger.debug(f"{sub_command} 子命令去掉前缀后的消息: {removed_prefix_msg.dump(json=True)}")
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
            r"\s(?:-m|--match|-r|--random|-c|--cron|-s|--scope|-g|--regex|-A|--del-alias|-C|--del_content)\s+\S+(?=$|\s)"
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

    keyword = get_keyword(msg_text, not_text_segments)

    content = get_content(msg_text, not_text_segments)

    alias = get_alias(msg_text, not_text_segments)

    return MainArgs(keyword, content, alias)

def get_keyword(
    msg_text: str,
    not_text_segments: list
) -> UniMessage:
    keyword = UniMessage()
    keyword_text = get_part_keyword(msg_text)
    logger.debug(f"keyword_text: {keyword_text}")
    keyword_part_text = get_part_text(keyword_text)
    # 关键词位于消息开头，其占位符从下标 0 开始
    not_text_segment_index = 0
    for part in keyword_part_text:
        if part.startswith("["):
            keyword.append(not_text_segments[not_text_segment_index])
            not_text_segment_index += 1
        else:
            keyword.append(part)
    return keyword.replace("《《《《", "[").replace("》》》》", "]")

def get_content(
    msg_text: str,
    not_text_segments: list
) -> UniMessage:
    content = UniMessage()
    content_text, content_offset = get_part_content(msg_text)
    logger.debug(f"content_text: {content_text}")
    content_part_text = get_part_text(content_text)
    logger.debug(f"content_part_text: {content_part_text}")
    # 关键词里可能已经用掉了一些非文本段，下标需要从内容开头处推算
    not_text_segment_index = count_placeholders_before(msg_text, content_offset)
    for part in content_part_text:
        if part.startswith("["):
            content.append(not_text_segments[not_text_segment_index])
            not_text_segment_index += 1
        else:
            content.append(part)
    return content.replace("《《《《", "[").replace("》》》》", "]")

def get_alias(
    msg_text: str,
    not_text_segments: list
) -> UniMessage | None:
    alias = UniMessage()
    alias_info = get_part_alias(msg_text)
    if not alias_info:
        return None
    alias_text, alias_offset = alias_info
    # 别名里的非文本段位于消息靠后的位置，下标同样不能从 0 开始
    not_text_segment_index = count_placeholders_before(msg_text, alias_offset)
    alias_part_text = get_part_text(alias_text)
    for part in alias_part_text:
        if part.startswith("["):
            alias.append(not_text_segments[not_text_segment_index])
            not_text_segment_index += 1
        else:
            alias.append(part)
    return alias.replace("《《《《", "[").replace("》》》》", "]")


