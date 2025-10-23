import datetime
import json
from nonebot_plugin_orm import Model, async_scoped_session
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, Text, DateTime, select, create_engine, MetaData, Table, Column, Integer
from typing import Optional
from nonebot_plugin_datastore import get_plugin_data

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
    alias: Mapped[Optional[str]] = mapped_column(Text, default=None, comment="别名（数组，每个数组代表一个别名）")
    dateModfied: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now, comment="词条编辑时间戳")
    dateCreate: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now, comment="词条创建时间戳")

def create_content_list(table_name: str):
    """
    在 nonebot_plugin_perithacus_replies.db 中创建一个名为 table_name 的表，
    结构为 id:int, content:text, timap:DateTime
    """
    plugin_data = get_plugin_data()
    db_path = plugin_data.data_dir / "content.db"
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
    plugin_data = get_plugin_data()
    db_path = plugin_data.data_dir / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    with engine.connect() as conn:
        ins = table.insert().values(content=content, timap=datetime.datetime.now())
        conn.execute(ins)
        conn.commit()
    engine.dispose()

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
    result = await session.execute(
        select(Index).where(Index.deleted == False)
    )
    entries = result.scalars().all()

    matches = []
    for entry in entries:
        # scope 过滤：若 entry.scope 无效或不包含指定 scope，则跳过
        try:
            scope_list = json.loads(entry.scope) if entry.scope else []
            if scope and scope not in scope_list:
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
    id : str
) -> Index:
    entry = await session.get(Index, id)
    # 检查 id 是否有效。但是，我想不出为什么会无效，因为调用方已经通过 get_id 确认了 id 的存在
    if entry is None:
        raise ValueError(f"Entry with id {id} not found")
    return entry