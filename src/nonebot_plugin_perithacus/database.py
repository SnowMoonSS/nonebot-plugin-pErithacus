from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from datetime import timezone as tz
from typing import TYPE_CHECKING

import sqlalchemy as sa
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

async def create_content_list(table_name: str) -> None:
    """
    在 content.db 中创建一个名为 table_name 的表
    """
    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(
        table_name,
        metadata,
        Column(
            "id",
            Integer,
            primary_key=True,
            autoincrement=True
        ),
        Column(
            "content",
            Text,
            nullable=False,
        ),
        Column(
            "deleted",
            Boolean,
            default=False,
        ),
        Column(
            "date_modified",
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC)
        ),
        Column(
            "date_create",
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC)
        ),
    )
    metadata.create_all(engine, tables=[table])
    metadata.reflect(bind=engine)
    if "content_version" not in metadata.tables:
        await create_version_table()
    engine.dispose()

async def create_version_table() -> None:
    """
    在 content.db 中创建一个记录数据库版本的表
    """
    version_num = 2

    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    metadata = MetaData()
    table = Table(
        "content_version",
        metadata,
        Column(
            "version_num",
            Integer,
            nullable=False
        ),
    )
    metadata.create_all(engine, tables=[table])
    with engine.connect() as conn:
        update = table.insert().values(version_num=version_num)
        conn.execute(update)
        conn.commit()
    engine.dispose()

async def get_contents(entry_id: int) -> Sequence[Row]:
    """
    返回 Entry_{entry_id} 表中的所有 content
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
    返回 Entry_{entry_id} 表中的所有 content
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
    返回在 scpoe_list 中且与 Index 中的 keyword 或 reg 或 alias 匹配的词条。
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
    返回在 scpoe_list 中且未被删除的词条。
    - scope_list: 列表
    - is_all: 是否返回所有条目，默认为 False
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
    """
    返回 entry_id 对应的词条。
    """
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
    比较两个 content 是否相同。
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
    向 table_name 表中添加一条 content 。
    返回 True 表示添加成功，返回 False 表示添加失败。
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
    返回 True 删除成功，返回 False 删除失败
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
    返回 True 删除成功，返回 False 删除失败
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
                .values(content=new_content, date_modified=datetime.now(UTC))
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

async def upgrade_content_db_1_to_2() -> None:
    """
    升级数据库表结构：检查并升级content.db中所有以Entry_开头的表结构，
    将不带时区的北京时间转换为带UTC时区的时间
    """

    db_path = get_plugin_data_dir() / "content.db"
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        metadata = MetaData()
        metadata.reflect(bind=engine)

        # 检查是否存在content_version表
        if "content_version" in metadata.tables:
            logger.info("content.db 已经是最新版本，无需升级")
            engine.dispose()
            return

        logger.info("开始升级数据库表结构")

        # 获取所有以Entry_开头的表
        entry_tables = [
            table_name for table_name in metadata.tables
            if table_name.startswith("Entry_")
        ]

        for table_name in entry_tables:
            logger.info(f"正在升级表 {table_name}")
            try:
                # 获取旧表结构
                old_table = metadata.tables[table_name]

                # 创建新表结构
                new_metadata = MetaData()
                new_table = Table(
                    f"new_{table_name}",
                    new_metadata,
                    Column(
                        "id",
                        Integer,
                        primary_key=True,
                        autoincrement=True
                    ),
                    Column(
                        "content",
                        Text,
                        nullable=False,
                    ),
                    Column(
                        "deleted",
                        Boolean,
                        default=False,
                    ),
                    Column(
                        "date_modified",
                        DateTime(timezone=True),
                        default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC)
                    ),
                    Column(
                        "date_create",
                        DateTime(timezone=True),
                        default=lambda: datetime.now(UTC)
                    ),
                )

                # 创建新表
                new_metadata.create_all(engine)

                # 迁移数据
                with engine.connect() as conn:
                    # 查询旧表的所有数据
                    select_stmt = select(old_table)
                    result = conn.execute(select_stmt)
                    rows = result.fetchall()

                    # 转换数据并插入新表
                    for row in rows:
                        # 转换时间字段
                        date_modified = (
                            row.dateModified
                            if hasattr(row, "dateModified") else row.date_modified
                        )
                        date_create = (
                            row.dateCreate
                            if hasattr(row, "dateCreate") else row.date_create
                        )

                        # 如果是 naive datetime，假设为北京时间并转换为 UTC
                        if date_modified and date_modified.tzinfo is None:
                            # 假设原时间为北京时间
                            beijing_tz = tz(timedelta(hours=8))
                            date_modified = date_modified.replace(tzinfo=beijing_tz)
                            # 转换为 UTC
                            date_modified = date_modified.astimezone(UTC)

                        if date_create and date_create.tzinfo is None:
                            # 假设原时间为北京时间
                            beijing_tz = tz(timedelta(hours=8))
                            date_create = date_create.replace(tzinfo=beijing_tz)
                            # 转换为 UTC
                            date_create = date_create.astimezone(UTC)

                        # 插入到新表
                        insert_stmt = new_table.insert().values(
                            id=row.id,
                            content=row.content,
                            deleted=row.deleted if hasattr(row, "deleted") else False,
                            date_modified=date_modified,
                            date_create=date_create
                        )
                        conn.execute(insert_stmt)

                    conn.commit()

                # 删除旧表，重命名新表
                with engine.connect() as conn:
                    drop_stmt = sa.text(f"DROP TABLE {table_name}")
                    conn.execute(drop_stmt)
                    conn.commit()

                    rename_stmt = sa.text(
                        f"ALTER TABLE new_{table_name} RENAME TO {table_name}"
                    )
                    conn.execute(rename_stmt)
                    conn.commit()

            except SQLAlchemyError as e:
                logger.error(f"升级表 {table_name} 时出错: {e}")
                continue
    finally:
        engine.dispose()

    # 创建版本表
    await create_version_table()
    logger.info("content.db 升级完成")
