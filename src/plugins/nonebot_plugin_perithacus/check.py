from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage

from .command import pe
from .database import Index, create_content_list, add_content, get_id, get_entry_by_id

@pe.assign("check")
async def _(
    session : async_scoped_session,
    
    id: Match[int] = AlconnaMatch("id"),
    force: Match[bool] = AlconnaMatch("force"),
):
    """查看词条配置"""

    if not force.available:
        entry = await get_entry_by_id(session, id.result)