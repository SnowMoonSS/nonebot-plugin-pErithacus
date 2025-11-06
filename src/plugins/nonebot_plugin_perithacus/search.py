import os
import json
import sqlite3
from sqlalchemy import select
from nonebot_plugin_orm import async_scoped_session
from nonebot.adapters import Event
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage
from nonebot_plugin_localstore import get_plugin_data_dir

from .command import pe
from .database import Index
from .lib import convert_media, load_media

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
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            try:
                # 查询每个表中content列包含key的行
                cursor.execute(f"SELECT id FROM {table_name} WHERE content LIKE ?", (f"%{key}%",))
                rows = cursor.fetchall()
                
                for row in rows:
                    entry_id = row[0]
                    search_results.extend(f"{entry_id}　" + load_media(entry.keyword) + "\n")
            except sqlite3.Error:
                # 如果查询出错，跳过该表
                pass
        
        conn.close()
    
    await pe.finish(search_results)