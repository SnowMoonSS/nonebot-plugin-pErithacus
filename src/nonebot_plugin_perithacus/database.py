from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from nonebot import logger
from nonebot_plugin_alconna import Text as AlconnaText
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot_plugin_orm import AsyncSession, Model, async_scoped_session
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    select,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from .lib import get_num_list, load_media

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncEngine


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

async def get_all_entries(
    session: async_scoped_session,
    *,
    is_force: bool = False
) -> Sequence[Index]:
    """
    返回所有词条。
    - is_force: 是否返回包含已删除的所有条目
    """
    select_stmt = select(Index) if is_force else select(Index).where(~Index.deleted)
    result = await session.execute(select_stmt)
    return result.scalars().all()

def _is_in_scope(entry: Index, scope_list: list[str]) -> bool:
    """判断 entry 是否在指定的作用域内"""
    try:
        scope_list_from_db = json.loads(entry.scope) if entry.scope else []
        return any(item in scope_list_from_db for item in scope_list)
    except json.JSONDecodeError:
        return False

def _is_exact_match(entry: Index, keyword: str) -> bool:
    """判断是否满足精准匹配条件（keyword 或 alias）"""
    if not (entry.match_method == "精准" or entry.reg is not None):
        return False

    # 直接 keyword 匹配
    if entry.keyword == keyword:
        return True

    # alias 匹配
    if entry.alias:
        try:
            alias_list = json.loads(entry.alias)
            return keyword in alias_list  # noqa: TRY300
        except json.JSONDecodeError:
            pass
    return False

def _is_fuzzy_match(entry: Index, keyword_msg: UniMessage) -> bool:
    """判断是否满足模糊匹配条件（仅当 match_method='模糊' 且无 reg）"""
    if not (entry.match_method == "模糊" and entry.reg is None):
        return False

    if not UniMessage(keyword_msg).only(AlconnaText):
        return False

    key = keyword_msg.extract_plain_text()
    entry_key = load_media(entry.keyword).extract_plain_text()
    if key in entry_key:
        return True

    if entry.alias:
        try:
            alias_list = json.loads(entry.alias)
            for alias in alias_list:
                entry_alias = load_media(alias).extract_plain_text()
                if key in entry_alias:
                    return True
        except json.JSONDecodeError:
            pass
    return False

def _is_regex_match(entry: Index, keyword_msg: UniMessage) -> bool:
    """判断是否满足正则匹配条件"""
    if not entry.reg:
        return False
    if not UniMessage(keyword_msg).only(AlconnaText):
        return False

    key = keyword_msg.extract_plain_text()
    return bool(re.match(entry.reg, key))

async def matching(
    entries: Sequence[Index],
    keyword: str,
    scope_list: list[str],
) -> Sequence[Index]:
    """
    返回在 scope_list 中且与 Index 中的 keyword、reg 或 alias 匹配的词条。
    - entries: Index 对象列表
    - keyword: 经由 save_media 或者 convert_media 转换后的 JSON 字符串
    - scope_list: 列表
    """
    matches = []
    keyword_msg = load_media(keyword)

    for entry in entries:
        # 1. 作用域过滤
        if not _is_in_scope(entry, scope_list):
            continue

        # 2. 精准匹配
        if _is_exact_match(entry, keyword):
            matches.append(entry)
            logger.debug(f"匹配词条 {entry.id}, 精准匹配")
            continue

        # 3. 模糊匹配
        if _is_fuzzy_match(entry, keyword_msg):
            matches.append(entry)
            logger.debug(f"匹配词条 {entry.id}，模糊匹配")
            continue

        # 4. 正则匹配
        if _is_regex_match(entry, keyword_msg):
            matches.append(entry)
            logger.debug(f"匹配词条 {entry.id}，正则匹配 {entry.reg}")
            continue

        # 可选：记录未匹配日志（取消注释即可）
        # logger.debug(f"词条 {entry.id} 在作用域中，但未匹配")

    return matches

async def get_entry(
    session: async_scoped_session,

    keyword: str,
    scope_list: list[str],
) -> Index | None:
    """
    返回在 scpoe_list 中且与 Index 中的 keyword 或 reg 或 alias 匹配的词条。
    - keyword: 经由 save_media 或者 convert_media 转换后的 JSON 字符串
    - scope_list: 字符串列表
    """

    entries = await get_all_entries(session)
    matches = await matching(entries, keyword, scope_list)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # 多条时按 date_modified 最新的返回
    return max(matches, key=(lambda entry: entry.date_modified))

async def get_entries(
    session: async_scoped_session,

    scope_list: list[str],
    *,
    is_all: bool = False,
    is_force: bool = False
) -> Sequence[Index] | None:
    """
    返回在 scpoe_list 中且未被删除的词条。
    - scope_list: 列表
    - is_all: 是否无视 scope_list 返回所有条目，默认为 False
    - is_force: 是否返回包含已删除的所有条目，默认为 False
    """

    entries = await get_all_entries(session, is_force=is_force)

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

async def update_entry(
    # AI 寻思这个未被使用的参数不应该删除，所以保留
    # Note: session is required to ensure `entry` is in the correct persistence context,
    # even though we don't explicitly call session methods here.
    session: async_scoped_session,  # noqa: ARG001

    entry: Index,
    **kwargs: Any
) -> Index:
    """
    更新 entry。
    """

    fields_to_update = {
        "match_method",
        "is_random",
        "cron",
        "scope",
        "reg",
        "deleted",
        "alias",
        "date_modified",
    }

    for field in fields_to_update:
        if field in kwargs:
            setattr(entry, field, kwargs[field])

    entry.date_modified = datetime.now(UTC)

    return entry

async def add_entry(
    session: async_scoped_session,

    **kwargs: Any
) -> Index:
    """
    添加一个新的词条。
    """

    new_entry = Index(
        **kwargs
    )
    session.add(new_entry)
    logger.debug(f"添加新词条 {new_entry.id} : {new_entry.keyword} 到 Index")
    return new_entry

async def get_entry_by_id(
    session: async_scoped_session,
    entry_id: int
) -> Index | None:
    """
    返回 entry_id 对应的词条。
    """
    return await session.get(Index, entry_id)

async def get_cron_entries(session: AsyncSession) -> Sequence[Index]:
    select_stmt = select(Index).where(Index.cron.isnot(None)).where(~Index.deleted)
    result = await session.execute(select_stmt)
    return result.scalars().all()

class Content(Model):
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True
    )
    entry_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="词条 ID"
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="内容"
    )
    deleted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        comment="是否删除"
    )
    date_modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        comment="内容编辑时间戳"
    )
    date_create: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        comment="内容创建时间戳"
    )

async def create_content_list(table_name: str) -> None:
    """
    在 content.db 中创建一个名为 table_name 的表
    """
    db_path = get_plugin_data_dir() / "content.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
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
        async with engine.begin() as conn:
            await conn.run_sync(metadata.create_all, tables=[table])

        await create_version_table(engine)
    finally:
        await engine.dispose()

async def create_version_table(engine: AsyncEngine, version_num: int = 2) -> None:
    """
    在 content.db 中创建 content_version 表并插入初始版本号
    """
    metadata = MetaData()
    version_table = Table(
        "content_version",
        metadata,
        Column("version_num", Integer, nullable=False),
    )

    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all, tables=[version_table])
        # 检查是否已有数据
        result = await conn.execute(version_table.select().limit(1))
        if result.fetchone() is None:
            insert_stmt = version_table.insert().values(version_num=version_num)
            await conn.execute(insert_stmt)

async def get_contents(
    session: async_scoped_session | AsyncSession,

    entry_id: int,
    *,
    is_all: bool = False
) -> Sequence[Content]:
    """
    返回 {entry_id} 词条中的所有 content
    is_all 为 True 时返回包含已删除的所有 content
    """
    if is_all:
        select_stmt = select(Content).where(Content.entry_id == entry_id)
    else:
        select_stmt = (
            select(Content)
            .where(~Content.deleted)
            .where(Content.entry_id == entry_id)
        )
    result = await session.execute(select_stmt)
    return result.scalars().all()

async def get_all_contents(
    session: async_scoped_session,
) -> Sequence[Content]:
    """
    返回数据库中的所有 content
    包含被标记为删除的 content
    """
    select_stmt = select(Content)
    result = await session.execute(select_stmt)
    return result.scalars().all()

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

async def restore_deleted_content(
    session: async_scoped_session | AsyncSession,

    content_id: int
) -> None:
    """
    将 table_name 表中 id 为 row_id 的 content 的 deleted 字段设置为 False
    """

    update_stmt = (
        update(Content)
        .where(Content.id == content_id)
        .values(deleted=False)
    )
    await session.execute(update_stmt)

@dataclass
class AddContentResult:
    success: bool
    content_id: int

async def add_content(
    session: async_scoped_session | AsyncSession,

    entry_id: int,
    content: str,
    date_modified: datetime | None = None,
    date_create: datetime | None = None
) -> AddContentResult:
    """
    添加一条 content 。
    返回 True 表示添加成功，返回 False 表示内容已存在。
    """
    if date_modified is None:
        date_modified = datetime.now(UTC)
    if date_create is None:
        date_create = datetime.now(UTC)

    rows = await get_contents(session, entry_id)
    for row in rows:
        if compare_contents(row.content, content):
            if not row.deleted:
                return AddContentResult(success=False, content_id=row.id)
            await restore_deleted_content(session, row.id)
            return AddContentResult(success=True, content_id=row.id)

    logger.debug(f"添加内容 {content} 到 Content")
    new_content = Content(
        entry_id=entry_id,
        content=content,
        date_modified=date_modified,
        date_create=date_create
    )
    session.add(new_content)
    await session.flush()
    return AddContentResult(success=True, content_id=new_content.id)

async def delete_content(session: async_scoped_session, content_id: int) -> bool:
    """
    将 content_id 标记为已删除
    """
    update_stmt = (
        update(Content)
        .where(Content.id == content_id)
        .values(deleted=True, date_modified=datetime.now(UTC))
    )
    try:
        await session.execute(update_stmt)
        return True  # noqa: TRY300
    except SQLAlchemyError as e:
        logger.error(f"删除内容 {content_id} 失败: {e}")
        return False

@dataclass
class DeleteContentsResult:
    success: bool
    failed_ids: list[int]

async def delete_contents(
    session: async_scoped_session,
    content_list: str
) -> DeleteContentsResult:
    """
    将 content_list 中的所有内容标记为已删除

    返回:
    DeleteContentsResult:
        - 如果全部成功，返回 (True, [])
        - 如果有失败，返回 (False, [failed_id1, failed_id2, ...])
    """
    content_ids = await get_num_list(content_list)
    failed_ids: list[int] = []

    for content_id in content_ids:
        success = await delete_content(session, content_id)
        if not success:
            failed_ids.append(content_id)

    if failed_ids:
        return DeleteContentsResult(success=False, failed_ids=failed_ids)
    return DeleteContentsResult(success=True, failed_ids=[])

async def replace_content(
    session: async_scoped_session,

    entry_id: int,
    content_id: int,
    content: str
) -> bool:
    """
    替换 entry_id 中 content_id 记录的 content 为 new_content
    返回 True 删除成功，返回 False 删除失败
    """

    # 若有相同内容，则无需替换，返回 False
    rows = await get_contents(session, entry_id)
    for row in rows:
        if compare_contents(row.content, content):
            return False

    logger.debug(f"删除旧内容：{content_id}")
    await delete_content(session, content_id)

    logger.debug(f"添加新内容：{content}")
    await add_content(session, entry_id, content)
    return True
