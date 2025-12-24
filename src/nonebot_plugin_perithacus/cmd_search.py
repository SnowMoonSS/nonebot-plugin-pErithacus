from __future__ import annotations

import json
from typing import TYPE_CHECKING

from nonebot import logger
from nonebot.adapters import Event  # noqa: TC002
from nonebot_plugin_alconna import AlconnaMatch, AlconnaQuery, Match, Query, UniMessage
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .command import pe
from .database import Index, get_all_contents, get_entries, get_entry_by_id
from .lib import convert_media, get_scope, get_source, load_media

if TYPE_CHECKING:
    from collections.abc import Sequence


@pe.assign("search")
async def _(  # noqa: PLR0913
    event: Event,
    session : async_scoped_session,

    keyword: Match[UniMessage] = AlconnaMatch("keyword"),
    page: Match[int] = AlconnaMatch("page"),
    scope: Match[str] = AlconnaMatch("scope"),
    is_all: Query = AlconnaQuery("search.is_all", default=False)
):
    """
    搜索词条。
    - keyword <str>: 关键词。
    - page <int>: 页码，可选参数。列出指定页的词条内容。默认为第一页。
    - scope <str>: 作用域，可选参数。指定作用域以搜索该作用域下的词条。
    - is_all <bool>: 可选参数。是否忽略scope参数搜索所有词条，可选参数。默认为False。
    """

    logger.debug(f"is_all: {is_all.result}")

    this_source = get_source(event)
    scope_list = await get_scope(scope, this_source)
    key = await get_key(keyword)

    entries = await get_entries(session, scope_list, is_all=is_all.result.value)

    if entries:
        result_list = []
        result_list = await search_in_entries(entries, key, result_list)
        result_list = await search_in_contents(session, key, scope_list, result_list)

        # 分页处理
        page_size = 5
        total_count = len(result_list)
        if total_count > 0:
            total_pages = (total_count + page_size - 1) // page_size
        else:
            total_pages = 1

        # 获取当前页码
        current_page = page.result if page.available and page.result > 0 else 1
        current_page = min(current_page, total_pages)  # 确保不超过总页数

        # 计算当前页的条目范围
        start_index = (current_page - 1) * page_size
        end_index = min(start_index + page_size, total_count)

        # 构建搜索结果消息
        search_results = UniMessage(f"搜索结果（第 {current_page}/{total_pages} 页）：")

        # 显示当前页的结果
        for i in range(start_index, end_index):
            entry_id = result_list[i]
            entry = await get_entry_by_id(session, entry_id)
            if entry:
                search_results.extend(f"\n{entry.id}　" + load_media(entry.keyword))

        logger.info(f"搜索结果列表：{result_list}")
        await pe.finish(search_results)
    else:
        await pe.finish(UniMessage("搜索结果：\n无"))

async def get_key(keyword: Match) -> str:
    keyword_text = await convert_media(keyword.result)
    pe_message_list = json.loads(keyword_text)

    # 检查pe_message_list中的每个元素
    key = None
    for item in pe_message_list:
        if not isinstance(item, dict):
            continue
        if item.get("media"):
            key = item["id"]
            break
        if item.get("type") == "at":
            key = item["target"]
            break
    if not key:
        key = UniMessage(keyword.result).extract_plain_text()

    return key

async def search_in_entries(
    entries: Sequence[Index],
    key: str,
    result_list: list[int]
) -> list[int]:
    for entry in entries:
            # 检查keyword列和alias列包含key的行
            if key in entry.keyword or (entry.alias and key in entry.alias):
                result_list.append(entry.id)
                logger.info(
                    f"在 Index 中找到匹配的词条 {entry.id}，关键词 {entry.keyword}"
                )
    return result_list

async def search_in_contents(
    session: async_scoped_session,

    key: str,
    scope_list: list[str],
    result_list: list[int]
) -> list[int]:
    contents = await get_all_contents(session)
    for content in contents:
        if not content.deleted and key in content.content:
            if content.entry_id not in result_list:
                if await check_is_deleted(session, content.entry_id, scope_list):
                    result_list.append(content.entry_id)
            else:
                logger.debug(f"跳过词条 {content.entry_id}，该词条已存在搜索结果中")
        else:
            logger.debug(f"未在 {content.entry_id} 中找到包含 {key} 的内容")

    return result_list

async def check_is_deleted(
    session: async_scoped_session,
    entry_id: int,
    scope_list: list[str]
) -> bool:
    entry = await get_entry_by_id(session, entry_id)
    if entry and entry.deleted:
        try:
            scope_list_from_db = json.loads(entry.scope) if entry.scope else []
            if any(item in scope_list_from_db for item in scope_list):
                logger.debug(f"词条 {entry_id}，在作用域 {scope_list} 中，加入搜索结果")
                return True
            #logger.debug(f"词条 {entry_id}，不在作用域 {scope_list} 中")
            return False  # noqa: TRY300
        except json.JSONDecodeError:
            return False
    else:
        logger.debug(f"跳过词条 {entry_id}，该词条已标记为删除")
        return False
