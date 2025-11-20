import os
import json

from sqlalchemy import select, create_engine, MetaData, Table
from nonebot import logger
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage
from nonebot_plugin_localstore import get_plugin_data_dir

from .command import pe
from .database import Index, get_entry_by_id
from .lib import load_media, convert_media

@pe.assign("search")
async def _(
    session : async_scoped_session,

    keyword: Match[UniMessage] = AlconnaMatch("keyword"),
):
    keyword_text = await convert_media(keyword.result)
    pe_message_list = json.loads(keyword_text)
    # 检查pe_message_list中的每个元素
    has_media = any(item.get("media") for item in pe_message_list if isinstance(item, dict))
    has_at = any(item.get("type") == "at" for item in pe_message_list if isinstance(item, dict))
    
    if has_media:
        # 如果有一个或多个元素中存在"media": True
        # 使用第一个含有media的项的id作为key
        key = next((item['id'] for item in pe_message_list if isinstance(item, dict) and item.get("media")))
    elif has_at:
        # elif有一个或多个元素中的"type"为"at"
        # 使用第一个type为at的项的target作为key
        key = next((item['target'] for item in pe_message_list if isinstance(item, dict) and item.get("type") == "at"))
    else:
        # 其他情况使用纯文本
        key = UniMessage(keyword.result).extract_plain_text()
    
    # 搜索结果列表
    search_results = UniMessage("搜索结果：\n")
    
    # 在Index表中搜索keyword列或alias列包含key的行
    result = await session.execute(
        select(Index).where(Index.deleted == False)
    )
    entries = result.scalars().all()
    
    result_list = []
    for entry in entries:
        # 检查keyword列和alias列包含key的行
        if key in entry.keyword or (entry.alias and key in entry.alias):
            search_results.extend(f"{entry.id}　" + load_media(entry.keyword) + "\n")
            result_list.append(entry.id)
            logger.info(f"在 Index 中找到匹配的词条 {entry.id}，关键词 {entry.keyword}")
    
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
                # 获取表对象
                table = Table(table_name, metadata, autoload_with=engine)
                try:
                    with engine.connect() as conn:
                        stmt = select(table.c.id).where(
                            table.c.content.like(f"%{key}%"),
                            table.c.deleted == False
                        )
                        result = conn.execute(stmt)
                        contents = result.fetchone()
                        if contents:
                            entry_id = int(table_name.split("_")[1])
                            if entry_id not in result_list:
                                entry = await get_entry_by_id(session, entry_id)
                                if entry and not entry.deleted:
                                    result_list.append(entry_id)
                                    search_results.extend(f"{entry_id}　" + load_media(entry.keyword) + "\n")
                        else:
                            continue
                except Exception as e:
                    logger.info(f"查找内容表时发生了错误：{e}")
                    continue
        finally:
            engine.dispose()
    logger.info(f"搜索结果列表：{result_list}")
    await pe.finish(search_results)