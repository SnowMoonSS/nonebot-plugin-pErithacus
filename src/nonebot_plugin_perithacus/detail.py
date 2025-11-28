from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage, Query, AlconnaQuery

from .command import pe
from .database import get_entry_by_id, get_contents
from .lib import load_media

@pe.assign("detail")
async def _(
    session : async_scoped_session,
    
    id: Match[int] = AlconnaMatch("id"),
    page: Match[int] = AlconnaMatch("page"),
    force: Query[bool] = AlconnaQuery("force", False),
):
    entry = await get_entry_by_id(session, id.result)
    if entry:
        if force.available or not entry.deleted:
            rows = await get_contents(id.result)

            # 分页处理
            page_size = 5
            total_count = len(rows)
            total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
            
            # 获取当前页码
            current_page = page.result if page.available and page.result > 0 else 1
            current_page = min(current_page, total_pages)  # 确保不超过总页数
            
            # 计算当前页的条目范围
            start_index = (current_page - 1) * page_size
            end_index = min(start_index + page_size, total_count)

            msg = UniMessage(f"词条 {entry.id} : " + load_media(entry.keyword) + f"的内容如下（第 {current_page}/{total_pages} 页）：\n")

            # 显示当前页的内容
            for i in range(start_index, end_index):
                row = rows[i]
                msg.extend(f"{row.id}　" + load_media(row.content) + f"　时间: {row.dateModified}\n")

            await pe.finish(msg)
            
        elif not force.available and entry.deleted:
            await pe.finish("请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。")
    else:
        await pe.finish("请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。")