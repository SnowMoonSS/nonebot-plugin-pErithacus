from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage

from .command import pe

@pe.assign("check")
async def _(
    session : async_scoped_session,
    
    id: Match[UniMessage] = AlconnaMatch("id"),
):
    """查看词条"""
    return await _(
        session
    )