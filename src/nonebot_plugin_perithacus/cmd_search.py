import json

from nonebot import logger
from nonebot.adapters import Event  # noqa: TC002
from nonebot_plugin_alconna import AlconnaMatch, AlconnaQuery, Match, Query, UniMessage
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002
from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.exc import SQLAlchemyError

from .command import pe
from .database import get_entries, get_entry_by_id
from .lib import convert_media, load_media


@pe.assign("search")
async def _(
    event: Event,
    session : async_scoped_session,

    keyword: Match[UniMessage] = AlconnaMatch("keyword"),
    page: Match[int] = AlconnaMatch("page"),
    scope: Match[str] = AlconnaMatch("scope"),
    is_all: Query = AlconnaQuery("search.is_all", default=False)
):
    """
    搜索词条。
    - keyword <str>: 关键词。
    - page <int>: 页码，可选参数。列出指定页的词条内容。默认为第一页。
    """

    logger.debug(f"is_all: {is_all.result}")

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
            if not s.startswith(("g", "u")):
                await pe.finish("scope参数必须以g或u开头")

    keyword_text = await convert_media(keyword.result)
    pe_message_list = json.loads(keyword_text)

    # 检查pe_message_list中的每个元素
    key = None
    for item in pe_message_list:
        if not isinstance(item, dict):
            continue
        if item.get("media"):
            key = item["id"]
            break
        if item.get("type") == "at":
            key = item["target"]
            break
    if not key:
        key = UniMessage(keyword.result).extract_plain_text()

    if is_all.result.value:
        entries = await get_entries(session, scope_list, is_all=True)
    else:
        entries = await get_entries(session, scope_list)

    if entries:
        result_list = []
        for entry in entries:
            # 检查keyword列和alias列包含key的行
            if key in entry.keyword or (entry.alias and key in entry.alias):
                result_list.append(entry.id)
                logger.info(
                    f"在 Index 中找到匹配的词条 {entry.id}，关键词 {entry.keyword}"
                )

        # 搜索content.db中所有表的content列
        db_path = get_plugin_data_dir() / "content.db"

        if db_path.exists():
            engine = create_engine(f"sqlite:///{db_path}")
            metadata = MetaData()
            # 反射获取所有表信息
            metadata.reflect(bind=engine)

            # 遍历所有表
            try:
                for table_name in metadata.tables:
                    if table_name == "content_version":
                        continue
                    # 获取表对象
                    table = Table(table_name, metadata, autoload_with=engine)
                    try:
                        with engine.connect() as conn:
                            stmt = select(table.c.id).where(
                                table.c.content.like(f"%{key}%"),
                                ~table.c.deleted
                            )
                            result = conn.execute(stmt)
                            contents = result.fetchone()
                            if contents:
                                entry_id = int(table_name.split("_")[1])
                                if entry_id not in result_list:
                                    entry = await get_entry_by_id(session, entry_id)
                                    if entry and not entry.deleted:
                                        try:
                                            scope_list_from_db = json.loads(entry.scope) if entry.scope else []
                                            if any(item in scope_list_from_db for item in scope_list):
                                                logger.debug(f"词条 {entry.id}，在作用域 {scope_list} 中，加入搜索结果")
                                                result_list.append(entry_id)
                                        except json.JSONDecodeError:
                                            continue
                                    else:
                                        logger.debug(f"跳过词条 {entry_id}，该词条已标记为删除")
                                else:
                                    logger.debug(f"跳过词条 {entry_id}，该词条已存在搜索结果中")
                            else:
                                logger.debug(f"未找到包含 {key} 的内容")
                    except SQLAlchemyError as e:
                        logger.info(f"查找内容表时发生了错误：{e}")
                        continue
            finally:
                engine.dispose()

        # 分页处理
        page_size = 5
        total_count = len(result_list)
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

        # 构建搜索结果消息
        search_results = UniMessage(f"搜索结果（第 {current_page}/{total_pages} 页）：")

        # 显示当前页的结果
        for i in range(start_index, end_index):
            entry_id = result_list[i]
            entry = await get_entry_by_id(session, entry_id)
            if entry:
                search_results.extend(f"\n{entry.id}　" + load_media(entry.keyword))

        logger.info(f"搜索结果列表：{result_list}")
        await pe.finish(search_results)
    else:
        await pe.finish(UniMessage("搜索结果：\n无"))
