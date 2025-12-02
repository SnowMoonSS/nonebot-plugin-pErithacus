import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from nonebot import logger
from nonebot_plugin_alconna import Text as AlconnaText
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot_plugin_orm import Model, async_scoped_session
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    select,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Mapped, mapped_column

from .lib import load_media

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.engine import Row


class Index(Model):
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )
    keyword: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="词条名"
    )
    match_method: Mapped[str] = mapped_column(
        String(8),
        default="精准",
        comment="匹配方式"
    )
    is_random: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="是否随机回复"
    )
    cron: Mapped[str | None] = mapped_column(
        String(64),
        default=None,
        comment="定时cron表达式"
    )
    scope: Mapped[str] = mapped_column(
        Text,
        default="[]",
        comment="作用域（数组，每个数组代表一个作用域）"
    )
    reg: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="正则表达式"
    )
    source: Mapped[str] = mapped_column(
        Text,
        comment="来源"
    )
    target: Mapped[str] = mapped_column(
        Text,
        default=None,
        comment="json.dumps(Target.dump())"
    )
    deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="是否删除"
    )
    alias: Mapped[str | None] = mapped_column(
        Text,
        default=None,
        comment="别名（数组，每个数组代表一个别名，每个别名都是一个UniMessage对象dump出来的JSON数组）"
    )
    date_modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        comment="词条编辑时间戳"
    )
    date_create: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        comment="词条创建时间戳"
    )

def create_content_list(table_name: str) -> None:
    """
    在 content.db 中创建一个名为 table_name 的表，
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
        Column("deleted", Boolean, default=False),
        Column("date_modified", DateTime, default=datetime.now, onupdate=datetime.now),
        Column("date_create", DateTime, default=datetime.now),
    )
    metadata.create_all(engine, tables=[table])
    engine.dispose()

async def get_contents(entry_id: int) -> Sequence[Row]:
    """
    返回 table_name 表中的所有 content
    """
    table_name = f"Entry_{entry_id}"
    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    with engine.connect() as conn:
        result = conn.execute(select(table).where(~table.c.deleted))
        rows = result.fetchall()
    engine.dispose()
    return rows

async def get_all_contents(entry_id: int) -> Sequence[Row]:
    """
    返回 table_name 表中的所有 content
    包含被标记为删除的 content
    """
    table_name = f"Entry_{entry_id}"
    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    with engine.connect() as conn:
        result = conn.execute(select(table))
        rows = result.fetchall()
    engine.dispose()
    return rows


async def get_entry(
    session : async_scoped_session,

    keyword : str,
    scope_list : list[str],
) -> Index | None:
    """
    返回在 scpoe_list 中且与 Index 中的 keyword 或 reg 或 alias 匹配的词条实体。
    - keyword: 经由 save_media 或者 convert_media 转换后的 JSON 字符串
    - scope_list: 字符串列表
    """
    # 筛选未删除的条目
    result = await session.execute(
        select(Index).where(~Index.deleted)
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
                logger.debug(f"跳过词条 {entry.id}，不在作用域 {scope_list} 中")
                continue
        except json.JSONDecodeError:
            continue

        # 直接匹配 keyword
        if entry.keyword == keyword and entry.match_method == "精准":
            matches.append(entry)
            logger.debug(f"匹配词条 {entry.id}, 精准匹配")
            continue
        # 模糊匹配 keyword
        keyword_msg = load_media(keyword)
        if (
            entry.match_method == "模糊"
            and UniMessage(keyword_msg).only(AlconnaText)
            and entry.reg is None
        ):
            key = keyword_msg.extract_plain_text()
            entry_key = load_media(entry.keyword).extract_plain_text()
            if key in entry_key:
                matches.append(entry)
                logger.debug(f"匹配词条 {entry.id}，模糊匹配")
                continue
        # 检查正则表达式
        elif entry.reg and UniMessage(keyword_msg).only(AlconnaText):
            key = keyword_msg.extract_plain_text()
            if re.match(entry.reg, key):
                matches.append(entry)
                logger.debug(f"匹配词条 {entry.id}，正则匹配 {entry.reg}")
                continue
        # 检查 alias（JSON）
        elif entry.alias and keyword in json.loads(entry.alias):
            matches.append(entry)
            logger.debug(f"匹配词条 {entry.id}，别名匹配 {entry.alias}")
            continue
        else:
            logger.debug(f"词条 {entry.id} 在作用域中，但未匹配")

    if not matches:
        return None

    if len(matches) == 1:
        return matches[0]

    # 多条时按 date_modified 最新的返回
    min_datetime = datetime.min.replace(tzinfo=UTC)
    def _get_sort_key(entry: Index):
        return entry.date_modified or entry.date_create or min_datetime

    return max(matches, key=_get_sort_key)

async def get_entries(
    session : async_scoped_session,

    scope_list : list[str],
    *,
    is_all : bool = False
) -> Sequence[Index] | None:
    """
    返回在 scpoe_list 中且未被删除的词条实体。
    """
    # 筛选未删除的条目
    result = await session.execute(
        select(Index).where(~Index.deleted)
    )
    # 获取所有未删除的条目
    entries = result.scalars().all()

    if is_all:
        return entries

    matches = []
    for entry in entries:
        # scope 过滤：若 entry.scope 无效或不包含指定 scope，则跳过
        try:
            scope_list_from_db = json.loads(entry.scope) if entry.scope else []
            if not any(item in scope_list_from_db for item in scope_list):
                continue
        except json.JSONDecodeError:
            continue
        matches.append(entry)

    if not matches:
        return None

    return matches

async def get_entry_by_id(
    session : async_scoped_session,
    entry_id : int
) -> Index | None:
    return await session.get(Index, entry_id)

def remove_sticker_info(content_str: str) -> str:
    """
    从 content 字符串中移除 sticker 信息。
    """
    # 将字符串转换为 Python 对象
    content_list = json.loads(content_str)

    # 遍历列表中的每个字典，并删除 "sticker" 键
    for item in content_list:
        item.pop("sticker", None)

    # 将处理后的对象转换回字符串格式
    return json.dumps(content_list)

def compare_contents(content1: str, content2: str) -> bool:
    """
    比较两个 content 是否相等。
    """
    clean_content1 = remove_sticker_info(content1)
    clean_content2 = remove_sticker_info(content2)
    return clean_content1 == clean_content2

async def restore_deleted_content(table_id: int, row_id: int) -> None:
    """
    将 table_name 表中 id 为 row_id 的 content 的 deleted 字段设置为 False
    """
    table_name = f"Entry_{table_id}"
    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)

    with engine.connect() as conn:
        update = (
            table.update()
            .where(table.c.id == row_id)
            .values(deleted=False, date_modified=datetime.now(UTC))
        )
        conn.execute(update)
        conn.commit()
    engine.dispose()

async def add_content(table_id: int, content: str) -> bool:
    """
    向 table_name 表中添加一条 content 记录
    """
    table_name = f"Entry_{table_id}"
    # 提取所有的 content
    rows = await get_all_contents(table_id)
    for row in rows:
        if compare_contents(row.content, content):
            if not row.deleted:
                return False
            await restore_deleted_content(table_id, row.id)
        else:
            continue

    logger.debug(f"添加内容 {content} 到表 {table_name}")
    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)

    with engine.connect() as conn:
        ins = (
            table.insert()
            .values(
                content=content,
                deleted=False,
                date_modified=datetime.now(UTC),
                date_create=datetime.now(UTC)
            )
        )
        conn.execute(ins)
        conn.commit()
    engine.dispose()
    return True

async def delete_content(table_id: int, content_id: int) -> bool:
    """
    将 table_id 表中的 content_id 记录标记为已删除
    """
    table_name = f"Entry_{table_id}"

    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    try:
        with engine.connect() as conn:
            update_stmt = (
                table.update()
                .where(table.c.id == content_id)
                .values(deleted=True, date_modified=datetime.now(UTC))
            )
            conn.execute(update_stmt)
            conn.commit()
    except SQLAlchemyError as e:
        logger.error(f"删除内容 {content_id} 时出错：{e}")
        return False
    else:
        logger.debug(f"内容 {content_id} 标记为已删除")
        return True
    finally:
        engine.dispose()

async def replace_content(
        table_id: int,
        content_id: int,
        new_content: str
) -> bool:
    """
    替换 table_id 表中的 id 记录的 content 为 new_content
    """
    table_name = f"Entry_{table_id}"
    # 提取所有的 content
    rows = await get_contents(table_id)
    for row in rows:
        if compare_contents(row.content, new_content):
            return False

    logger.debug(f"替换内容 {new_content} 到表 {table_name}")
    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(table_name, metadata, autoload_with=engine)
    try:
        with engine.connect() as conn:
            update_stmt = (
                table.update()
                .where(table.c.id == content_id)
                .values(content=new_content, dete_modified=datetime.now(UTC))
            )
            conn.execute(update_stmt)
            conn.commit()
    except SQLAlchemyError as e:
        logger.error(f"替换内容 {content_id} 时出错：{e}")
        return False
    else:
        logger.debug(f"内容 {content_id} 已被替换")
        return True
    finally:
        engine.dispose()
