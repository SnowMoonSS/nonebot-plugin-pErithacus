from datetime import UTC, timedelta, timezone

from nonebot_plugin_alconna import AlconnaMatch, AlconnaQuery, Match, Query, UniMessage
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .command import pe
from .database import get_contents, get_entry_by_id
from .lib import load_media


@pe.assign("detail")
async def _(
    session : async_scoped_session,

    entry_id: Match[int] = AlconnaMatch("id"),
    page: Match[int] = AlconnaMatch("page"),
    force: Query = AlconnaQuery("force", default=False),
):
    entry = await get_entry_by_id(session, entry_id.result)
    if entry:
        if force.result.value or not entry.deleted:
            rows = await get_contents(entry_id.result)

            # 分页处理
            page_size = 5
            total_count = len(rows)
            if total_count > 0:
                total_pages = (total_count + page_size - 1) // page_size
            else:
                total_pages = 1

            # 获取当前页码
            current_page = page.result if page.available and page.result > 0 else 1
            current_page = min(current_page, total_pages)  # 确保不超过总页数

            # 计算当前页的条目范围
            start_index = (current_page - 1) * page_size
            end_index = min(start_index + page_size, total_count)

            msg = UniMessage(
                f"词条 {entry.id} : " + load_media(entry.keyword) +
                f"的内容如下（第 {current_page}/{total_pages} 页）：\n"
            )

            # 显示当前页的内容
            beijing_tz = timezone(timedelta(hours=8))
            for i in range(start_index, end_index):
                row = rows[i]
                date_modified = row.date_modified.replace(tzinfo=UTC)
                date_modified = date_modified.astimezone(beijing_tz)
                msg.extend(
                    f"{row.id}　" +
                    load_media(row.content) +
                    f"　时间: {date_modified}\n"
                )

            await pe.finish(msg)

        elif not force.result.value and entry.deleted:
            await pe.finish(
                "请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。"
            )
    else:
        await pe.finish(
            "请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。"
        )
