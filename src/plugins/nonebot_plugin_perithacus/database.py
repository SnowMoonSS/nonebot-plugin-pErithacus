import datetime
import json
import re

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, Text, DateTime, select, create_engine, MetaData, Table, Column, Integer
from typing import Optional

from nonebot import logger
from nonebot_plugin_orm import Model, async_scoped_session
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot_plugin_alconna import UniMessage, Text as AlconnaText

from .lib import load_media


class Index(Model):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(Text, nullable=False, comment="词条名")
    matchMethod: Mapped[str] = mapped_column(String(8), default="精准", comment="匹配方式")
    isRandom: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否随机回复")
    cron: Mapped[Optional[str]] = mapped_column(String(64), default=None, comment="定时cron表达式")
    scope: Mapped[str] = mapped_column(Text, default=None, comment="作用域（数组，每个数组代表一个作用域）")
    reg: Mapped[Optional[str]] = mapped_column(Text, default=None, comment="正则表达式")
    source: Mapped[str] = mapped_column(Text, default=None, comment="来源")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否删除")
    alias: Mapped[Optional[str]] = mapped_column(Text, default=None, comment="别名（数组，每个数组代表一个别名，每个别名都是一个UniMessage对象dump出来的JSON数组）")
    dateModfied: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment="词条编辑时间戳")
    dateCreate: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now, comment="词条创建时间戳")

def create_content_list(table_name: str):
    """
    在 nonebot_plugin_perithacus_replies.db 中创建一个名为 table_name 的表，
    结构为 id:int, content:text, timap:DateTime
    """
    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(
        table_name,
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("content", Text, nullable=False),
        Column("timap", DateTime, default=datetime.datetime.now),
    )
    metadata.create_all(engine, tables=[table])
    engine.dispose()

def add_content(table_name: str, content: str):
    """
    向 table_name 表中添加一条 content 记录
    """
    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    with engine.connect() as conn:
        ins = table.insert().values(content=content, timap=datetime.datetime.now())
        conn.execute(ins)
        conn.commit()
    engine.dispose()

async def get_contents(id: int):
    """
    返回 table_name 表中的所有 content
    """
    table_name = f"Entry_{id}"
    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    with engine.connect() as conn:
        result = conn.execute(select(table))
        rows = result.fetchall()
    engine.dispose()
    return rows

async def get_id(
    session : async_scoped_session,
    keyword : str,
    scope : str,
):
    """
    返回匹配 keyword 且在 scope 中（如果 scope 非空）的词条 id。
    - 先筛选未删除的条目
    - 再按 scope 过滤（scope 字段为 JSON 数组）
    - 检查 keyword 是否为主 keyword 或出现在 alias（JSON 数组）中
    - 若匹配到多条，返回 dateModfied 最新的那条的 id
    - 未命中返回 None
    """
    # 筛选未删除的条目
    result = await session.execute(
        select(Index).where(Index.deleted == False)
    )
    # 获取所有未删除的条目
    entries = result.scalars().all()

    # 进行匹配
    matches = []
    for entry in entries:
        # scope 过滤：若 entry.scope 无效或不包含指定 scope，则跳过
        try:
            scope_list = json.loads(entry.scope) if entry.scope else []
            if scope not in scope_list:
                continue
        except json.JSONDecodeError:
            continue

        # 直接匹配 keyword
        if entry.keyword == keyword:
            matches.append(entry)
            continue

        # 检查 alias（JSON）
        try:
            alias_list = json.loads(entry.alias) if entry.alias else []
            if keyword in alias_list:
                matches.append(entry)
        except json.JSONDecodeError:
            pass

    if not matches:
        return None

    if len(matches) == 1:
        return matches[0].id

    # 多条时按 dateModfied 最新的返回
    best = max(matches, key=lambda e: e.dateModfied or e.dateCreate or datetime.datetime.min)
    return best.id

async def get_entry(
    session : async_scoped_session,
    keyword : str,
    scope_list : list[str],
) -> Index | None:
    """
    返回匹配 keyword 且在 scope 中（如果 scope 非空）的词条 id。
    - 先筛选未删除的条目
    - 再按 scope 过滤（scope 字段为 JSON 数组）
    - 检查 keyword 是否为主 keyword 或出现在 alias（JSON 数组）中
    - 若匹配到多条，返回 dateModfied 最新的那条的 id
    - 未命中返回 None
    """
    # 筛选未删除的条目
    result = await session.execute(
        select(Index).where(Index.deleted == False)
    )
    # 获取所有未删除的条目
    entries = result.scalars().all()

    # 进行匹配
    matches = []
    for entry in entries:
        # scope 过滤：若 entry.scope 无效或不包含指定 scope，则跳过
        try:
            scope_list_from_db = json.loads(entry.scope) if entry.scope else []
            if not any(item in scope_list_from_db for item in scope_list):
                continue
        except json.JSONDecodeError:
            continue

        # 直接匹配 keyword
        if entry.keyword == keyword:
            matches.append(entry)
            continue

        # 检查正则表达式
        if entry.reg and UniMessage(load_media(keyword)).only(AlconnaText):
            key = load_media(keyword).extract_plain_text()
            if re.match(entry.reg, key):
                matches.append(entry)

        # 检查 alias（JSON）
        try:
            alias_list = json.loads(entry.alias) if entry.alias else []
            if keyword in alias_list:
                matches.append(entry)
        except json.JSONDecodeError:
            pass

    if not matches:
        return None

    if len(matches) == 1:
        return matches[0]

    # 多条时按 dateModfied 最新的返回
    best = max(matches, key=lambda e: e.dateModfied or e.dateCreate or datetime.datetime.min)
    return best

async def get_entry_by_id(
    session : async_scoped_session,
    id : int
) -> Index | None:
    entry = await session.get(Index, id)
    return entry

async def delete_content(table_id: int, id: int):
    """
    删除 table_id 表中的 id 记录
    """
    table_name = f"Entry_{table_id}"

    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    with engine.connect() as conn:
        delete_stmt = table.delete().where(table.c.id == id)
        result = conn.execute(delete_stmt)
        conn.commit()
    engine.dispose()
    return result.rowcount > 0

async def replace_content(table_id: int, id: int, new_content: str):
    """
    替换 table_id 表中的 id 记录的 content 为 new_content
    """
    table_name = f"Entry_{table_id}"

    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    with engine.connect() as conn:
        update_stmt = table.update().where(table.c.id == id).values(content=new_content, timap=datetime.datetime.now())
        result = conn.execute(update_stmt)
        conn.commit()
    engine.dispose()
    return result.rowcount > 0