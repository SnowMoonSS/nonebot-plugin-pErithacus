from nonebot_plugin_orm import async_scoped_session
from nonebot.adapters import Event
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage

from .command import pe
from .database import get_entry_by_id, get_contents

@pe.assign("detail")
async def _(
    session : async_scoped_session,
    
    id: Match[int] = AlconnaMatch("id"),
    force: Match[bool] = AlconnaMatch("force"),
):
    entry = await get_entry_by_id(session, id.result)
    if entry:
        if force.available or not entry.deleted:
            msg = UniMessage("词条" + UniMessage.load(entry.keyword) + "的内容如下：\n")
            rows = await get_contents(id.result)
            for row in rows:
                msg.extend(f"{id}" + UniMessage.load(row.content) + f"时间: {row.timap.strftime('%Y-%m-%d %H:%M:%S') if row.timap else 'N/A'}\n")
            await pe.finish(msg)
        elif not force.available and entry.deleted:
            await pe.finish("请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。")
    else:
        await pe.finish("请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。")