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
    is_all: Query = AlconnaQuery("detail.is_all", default=False),
    is_force: Query = AlconnaQuery("detail.is_force", default=False),
):
    """
    查看指定词条的详细信息。
    - id <int>: 词条 ID，必填参数。查看指定 ID 的词条的详细信息。
    - page <int>: 页码，可选参数。查看指定页的词条内容。默认为第一页。
    - is_force <bool>: 可选参数。是否查看包含已删除词条的内容，默认为False。
    - is_all <bool>: 可选参数。是否忽略scope参数查看所有词条
    """

    entry = await get_entry_by_id(session, entry_id.result)
    if entry:
        if is_force.result.value or not entry.deleted:
            rows = await get_contents(
                session,
                entry_id.result,
                is_all=is_all.result.value
            )

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

        elif entry.deleted:
            await pe.finish(
                "请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。"
            )
    else:
        await pe.finish(
            "请输入有效的词条 ID 。使用 search 或 list 命令查看词条列表。"
        )
