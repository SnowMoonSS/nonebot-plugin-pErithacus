import json
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage, Query, AlconnaQuery

from .command import pe
from .database import get_entry_by_id
from .lib import load_media

@pe.assign("check")
async def _(
    session : async_scoped_session,
    
    id: Match[int] = AlconnaMatch("id"),
    force: Query[bool] = AlconnaQuery("force", False),
):
    """查看词条配置"""

    entry = await get_entry_by_id(session, id.result)
    if entry:
        if force.available or not entry.deleted:
            keyword = load_media(entry.keyword)

            aliases = UniMessage()
            if entry.alias:
                aliases_json = json.loads(entry.alias)
                for alias in aliases_json:
                    aliases.append(load_media(alias))
                
                await pe.finish(f"编号：{entry.id}\n" + 
                                f"词条名：" + keyword + "\n" + 
                                f"匹配方式：{entry.matchMethod}\n" +
                                f"随机：{entry.isRandom}\n" +
                                f"定时：{entry.cron}\n" +
                                f"作用域：{entry.scope}\n" +
                                f"正则表达式：{entry.reg}\n" +
                                f"来源：{entry.source}\n" +
                                f"删除：{entry.deleted}\n" +
                                f"创建时间：{entry.dateCreate}\n" +
                                f"修改时间：{entry.dateModified}\n" +
                                "别名：" + aliases
                                )
            else:
                aliases = None
                await pe.finish(f"编号：{entry.id}\n" + 
                                f"词条名：" + keyword + "\n" + 
                                f"匹配方式：{entry.matchMethod}\n" +
                                f"随机：{entry.isRandom}\n" +
                                f"定时：{entry.cron}\n" +
                                f"作用域：{entry.scope}\n" +
                                f"正则表达式：{entry.reg}\n" +
                                f"来源：{entry.source}\n" +
                                f"删除：{entry.deleted}\n" +
                                f"创建时间：{entry.dateCreate}\n" +
                                f"修改时间：{entry.dateModified}\n" +
                                f"别名：{aliases}"
                                )
        elif not force.available and entry.deleted:
            await pe.finish("请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。")
    elif not entry:
        await pe.finish("请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。")