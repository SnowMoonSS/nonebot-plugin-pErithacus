from loguru import logger
from nonebot_plugin_alconna import (
    AlconnaMatch,
    AlconnaQuery,
    Match,
    MsgTarget,
    Query,
    UniMessage,
)
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .command import pe
from .database import get_entries
from .lib import get_scope, get_source, load_msg


@pe.assign("list")
async def _(  # noqa: PLR0913
    target: MsgTarget,
    session: async_scoped_session,

    page: Match[int] = AlconnaMatch("page"),
    scope: Match[str] = AlconnaMatch("scope"),
    is_all: Query = AlconnaQuery("list.is_all", default=False),
    is_force: Query = AlconnaQuery("list.is_force", default=False)
):
    """
    列出所有词条。
    - page <int>: 页码，可选参数。列出指定页的词条内容。默认为第一页。
    - scope <str>: 作用域，可选参数。指定作用域以列出该作用域下的词条。
    - is_all <bool>: 可选参数。是否忽略scope参数列出所有词条，可选参数。默认为False。
    - is_force <bool>: 可选参数。是否列出包括被删除的所有词条，可选参数。默认为False。
    """

    logger.debug(f"is_all: {is_all.result}")

    this_source = get_source(target)
    scope_list = await get_scope(scope, this_source)

    entries = await get_entries(
        session,
        scope_list,
        is_all=is_all.result.value,
        is_force=is_force.result.value
    )

    if entries:
        # 分页处理
        page_size = 5
        total_count = len(entries)
        total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

        # 获取当前页码
        current_page = page.result if page.available and page.result > 0 else 1
        current_page = min(current_page, total_pages)  # 确保不超过总页数

        # 计算当前页的条目范围
        start_index = (current_page - 1) * page_size
        end_index = min(start_index + page_size, total_count)

        message = UniMessage(f"全部词条（第 {current_page}/{total_pages} 页）：")

        # 显示当前页的条目
        for i in range(start_index, end_index):
            entry = entries[i]
            entry_id = entry.id
            uni_keyword = load_msg(entry.keyword)
            message.extend(f"\n{entry_id}：" + uni_keyword)
    else:
        message = UniMessage("尚无词条，使用 pe add 添加词条")

    await pe.finish(message)
