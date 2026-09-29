import json
from datetime import UTC, timedelta, timezone

from nonebot_plugin_alconna import (
    AlconnaMatch,
    AlconnaQuery,
    Match,
    MsgTarget,
    Query,
    UniMessage,
)
from nonebot_plugin_orm import async_scoped_session

from .command import pe
from .database import get_entry_by_id, is_in_scope
from .lib import get_source, load_msg


@pe.assign("check")
async def _(
    target: MsgTarget,
    session : async_scoped_session,

    entry_id: Match[int] = AlconnaMatch("id"),
    force: Query = AlconnaQuery("check.force", default=False),
):
    """查看词条配置"""

    entry = await get_entry_by_id(session, entry_id.result)
    if not entry:
        await pe.finish(
            "请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。"
        )

    if not force.result.value:
        if entry.deleted:
            await pe.finish(
                "请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。"
            )
        # 默认只展示当前会话所在作用域中的词条，跨作用域查看需要 -f
        this_source = get_source(target)
        if not is_in_scope(entry, [this_source]):
            await pe.finish(
                "请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。"
            )

    keyword = load_msg(entry.keyword)
    # 将UTC时间转换为北京时间
    beijing_tz = timezone(timedelta(hours=8))
    date_create = entry.date_create.replace(tzinfo=UTC)
    date_create = entry.date_create.astimezone(beijing_tz)
    date_modified = entry.date_modified.replace(tzinfo=UTC)
    date_modified = entry.date_modified.astimezone(beijing_tz)

    msg = (
        f"编号：{entry.id}\n" +
        "词条名：" + keyword + "\n" +
        f"匹配方式：{entry.match_method}\n" +
        f"随机：{entry.is_random}\n" +
        f"定时：{entry.cron}\n" +
        f"作用域：{entry.scope}\n" +
        f"正则表达式：{entry.reg}\n" +
        f"来源：{entry.source}\n" +
        f"删除：{entry.deleted}\n" +
        f"创建时间：{date_create}\n" +
        f"修改时间：{date_modified}\n" +
        "别名：\n"
    )
    aliases_msg = UniMessage()
    aliases_json = json.loads(entry.alias) if entry.alias else []
    for idx, alias in enumerate(aliases_json, start=1):
        alias_loaded = load_msg(alias)
        aliases_msg += UniMessage(f"{idx}. {alias_loaded}\n")

    await pe.finish(msg + aliases_msg)
