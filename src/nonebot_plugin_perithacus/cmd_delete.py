import json

from nonebot.adapters import Event  # noqa: TC002
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .apscheduler import remove_cron_job
from .command import pe
from .database import get_entry
from .lib import convert_media, get_source


@pe.assign("del")
async def _(
    event: Event,
    session : async_scoped_session,

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

    # 处理scope
    if not scope.available:
        scope_list = [this_source]
    else:
        scope_list = scope.result.split(",")
        for _s in scope_list:
            if not (scope.result.startswith("g") or scope.result.startswith("u")):
                await pe.finish("scope参数必须以g或u开头")

    entry = await get_entry(session, keyword_text, scope_list)
    if entry:
        scope_list_from_db = json.loads(entry.scope)

        if any(item in scope_list_from_db for item in scope_list):
            # 从scope中删除
            scope_list_from_db = [
                item for item in scope_list_from_db
                if item not in scope_list
            ]
            # 更新scope字段或标记删除
            if scope_list_from_db != []:
                entry.scope = json.dumps(scope_list)
                session.add(entry)
                await session.commit()
                await session.refresh(entry)
                await pe.finish(
                    "已从词条 " + uni_keyword + f" 中移除作用域 {scope_list}，"
                    f"剩余作用域：{scope_list_from_db}"
                )
            else:
                entry.deleted = True
                session.add(entry)
                await session.commit()
                await session.refresh(entry)
                remove_cron_job(entry.id)
                await pe.finish(
                    "已从词条 " + uni_keyword + f" 中移除作用域 {scope_list}，"
                    "词条已标记为删除"
                )
    else:
        await pe.finish("词条 " + uni_keyword + f" 在作用域 {scope_list} 中不存在")
