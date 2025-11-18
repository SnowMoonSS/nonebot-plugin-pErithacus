from sqlalchemy import select
from nonebot_plugin_alconna import UniMessage, AlconnaMatch, Match
from nonebot_plugin_orm import async_scoped_session

from .command import pe
from .database import Index, get_entry_by_id, get_contents
from .lib import load_media

@pe.assign("list")
async def _(
    session : async_scoped_session,

    entry_id: Match[int] = AlconnaMatch("entry_id"),
):
    """
    列出所有词条
    - entry_id <int>: 可选参数。列出指定 ID 的词条内筒
    """
    if entry_id.available:
        entry = await get_entry_by_id(session, entry_id.result)
        if not entry or entry.deleted:
            await pe.finish("请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。")
        elif entry and not entry.deleted:
            msg = UniMessage("词条" + load_media(entry.keyword) + "的内容如下：\n")
            rows = await get_contents(entry_id.result)
            for row in rows:
                msg.extend(f"{row.id}　" + load_media(row.content) + f"　时间: {row.dateModified}\n")
            await pe.finish(msg)
    else:
        result = await session.execute(
            select(Index).where(Index.deleted == False)
        )
        # 获取所有未删除的条目
        entries = result.scalars().all()

        message = UniMessage("全部词条：")
        for entry in entries:
            id = entry.id
            uni_keyword = UniMessage.load(entry.keyword)
            message.extend(f"\n{id}：" + uni_keyword)

    await pe.finish(message)