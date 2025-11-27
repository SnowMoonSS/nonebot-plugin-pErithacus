from nonebot.adapters import Event
from nonebot_plugin_alconna import UniMessage, AlconnaMatch, Match
from nonebot_plugin_orm import async_scoped_session

from .command import pe
from .database import get_entries

@pe.assign("list")
async def _(
    event: Event,
    session : async_scoped_session,

    page: Match[int] = AlconnaMatch("page"),
    scope: Match[str] = AlconnaMatch("scope"),
    isAll: Match[bool] = AlconnaMatch("isAll"),
):
    """
    列出所有词条。
    - page <int>: 页码，可选参数。列出指定页的词条内容。默认为第一页。
    """

    # 处理source
    session_id = event.get_session_id()
    # 根据 session_id 格式设置 source 变量
    if session_id.startswith("group_"):
        # group_{groupid}_{userid} 格式，提取 groupid
        group_id = session_id.split("_")[1]
        this_source = f"g{group_id}"
    else:
        # {userid} 格式，直接使用 userid
        user_id = session_id
        this_source = f"u{user_id}"

    # 处理scope
    if not scope.available:
        scope_list = [this_source]
    else:
        scope_list = scope.result.split(",")
        for s in scope_list:
            if not (s.startswith("g") or s.startswith("u")):
                await pe.finish("scope参数必须以g或u开头")

    if isAll.available and isAll.result:
        entries = await get_entries(session, scope_list, isAll=True)
    else:
        entries = await get_entries(session, scope_list)

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
            id = entry.id
            uni_keyword = UniMessage.load(entry.keyword)
            message.extend(f"\n{id}：" + uni_keyword)
    else:
        message = UniMessage("尚无词条，使用 pe add 添加词条")

    await pe.finish(message)