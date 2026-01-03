import json
from datetime import UTC, datetime

from nonebot.adapters import Event  # noqa: TC002
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .apscheduler import remove_cron_job
from .command import pe
from .database import get_entry, update_entry
from .lib import convert_media, get_scope, get_source


@pe.assign("del")
async def _(
    event: Event,
    session: async_scoped_session,

    keyword: Match[UniMessage] = AlconnaMatch("keyword"),
    scope: Match[str] = AlconnaMatch("scope"),
):
    """
    删除词条
    get_id，然后从scope中删除这个scope，如果删除后scope为空则标记deleted=True
    """

    keyword_text = await convert_media(keyword.result)
    uni_keyword = UniMessage(keyword.result)
    this_source = get_source(event)
    scope_list = await get_scope(scope, this_source)

    entry = await get_entry(session, keyword_text, scope_list)
    if not entry:
        await pe.finish("词条 " + uni_keyword + f" 在作用域 {scope_list} 中不存在")

    scope_list_from_db = json.loads(entry.scope)

    # 检查是否有交集（即要删除的 scope 是否存在于当前词条中）
    if not any(item in scope_list_from_db for item in scope_list):
        await pe.finish("词条" + uni_keyword + " 在指定作用域中未启用，无需删除")

    # 从scope中删除
    new_scope_list = [
        item for item in scope_list_from_db
        if item not in scope_list
    ]
    # 更新scope字段或标记删除
    if new_scope_list:
        await update_entry(
            session,
            entry,
            scope = json.dumps(new_scope_list),
            date_modified = datetime.now(UTC)
        )
        msg = (
            "已从词条 " + uni_keyword + f" 中移除作用域 {scope_list}，"
            + f"剩余作用域：{new_scope_list}"
        )
    else:
        await update_entry(
            session,
            entry,
            scope = json.dumps([]),
            deleted = True,
            date_modified = datetime.now(UTC)
        )
        remove_cron_job(entry.id)
        msg = (
            "已从词条 " + uni_keyword + f" 中移除作用域 {scope_list}，"
            "词条已标记为删除"
        )

    await session.commit()
    await pe.finish(msg)
