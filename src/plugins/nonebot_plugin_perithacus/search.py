import os
import json

from sqlalchemy import select, create_engine, MetaData, Table
from nonebot import logger
from nonebot_plugin_orm import async_scoped_session
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage
from nonebot_plugin_localstore import get_plugin_data_dir

from .command import pe
from .database import Index, get_entry_by_id
from .lib import load_media

@pe.assign("search")
async def _(
    session : async_scoped_session,

    keyword: Match[UniMessage] = AlconnaMatch("keyword"),
):
    uni_keyword = UniMessage(keyword.result)
    dumped_keyword = uni_keyword.dump(media_save_dir=False, json=True)
    json_keyword = json.loads(dumped_keyword)
    for item in json_keyword:
        if 'url' in item:
            key = os.path.splitext(item['id'])[0]
        else:
            key = uni_keyword.extract_plain_text()
    
    # 搜索结果列表
    search_results = UniMessage("搜索结果：\n")
    
    # 在Index表中搜索keyword列或alias列包含key的行
    result = await session.execute(
        select(Index).where(Index.deleted == False)
    )
    entries = result.scalars().all()
    
    for entry in entries:
        # 检查keyword列
        if key in entry.keyword:
            search_results.extend(f"{entry.id}　" + load_media(entry.keyword) + "\n")
        
        # 检查alias列
        if entry.alias and key in entry.alias:
            search_results.extend(f"{entry.id}　" + load_media(entry.keyword) + "\n")
    
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
                            entry = await get_entry_by_id(session, entry_id)
                            if entry and not entry.deleted:
                                search_results.extend(f"{entry_id}　" + load_media(entry.keyword) + "\n")
                        else:
                            continue
                except Exception as e:
                    logger.info(f"查找内容表时发生了错误：{e}")
                    continue
        finally:
            engine.dispose()
    
    await pe.finish(search_results)