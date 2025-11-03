from sqlalchemy import select
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_orm import async_scoped_session

from .command import pe
from .database import Index

@pe.assign("list")
async def _(
    session : async_scoped_session,
):
    """列出所有条目"""
    result = await session.execute(
        select(Index).where(Index.deleted == False)
    )
    # 获取所有未删除的条目
    entries = result.scalars().all()

    message = UniMessage("全部词条：")
    for entry in entries:
        id = entry.id
        uni_keyword = UniMessage.load(entry.keyword)
        message.extend(f"\n{id}、" + uni_keyword)

    await pe.finish(message)