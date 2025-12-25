import re
from datetime import UTC, datetime, timedelta
from datetime import timezone as tz

import sqlalchemy as sa
from nonebot import logger
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot_plugin_orm import get_session
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    Text,
    select,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from .database import Content, create_version_table


async def upgrade_content_db() -> bool:
    """
    获取 centent.db 的版本
    返回 True 表示成功，返回 False 表示失败
    """
    content_version_2 = 2
    content_version_3 = 3

    db_path = get_plugin_data_dir() / "content.db"

    if not db_path.exists():
        logger.info("无旧库，视为第一次启动，无需升级")
        return True  # 无旧库，视为成功

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    sucess = False

    try:
        metadata = MetaData()
        version_table = Table(
            "content_version",
            metadata,
            Column("version_num", Integer)
        )
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            result = await session.execute(select(version_table.c.version_num).limit(1))
            row = result.fetchone()

            if row is None:
                success_v12 = await upgrade_content_db_1_to_2(engine)
                if not success_v12:
                    sucess = False
                else:
                    sucess = await upgrade_content_db_2_to_3(engine)
            elif row[0] == content_version_2:
                sucess = await upgrade_content_db_2_to_3(engine)
            elif row[0] == content_version_3:
                logger.info("数据库已是最新版本")
                sucess = True
            else:
                logger.warning(f"数据库版本 {row[0]} 不支持")
                sucess = False

    except SQLAlchemyError as e:
        logger.exception(f"检查版本时出错: {e}")
        return False
    finally:
        await engine.dispose()

    return sucess

async def upgrade_content_db_1_to_2(engine: AsyncEngine) -> bool:
    """
    升级数据库表结构：检查并升级content.db中所有以Entry_开头的表结构，
    将不带时区的北京时间转换为带UTC时区的时间
    返回 True 表示成功，返回 False 表示失败
    """

    logger.info("升级数据库 1 -> 2")

    try:
        metadata = MetaData()
        async with engine.connect() as conn:
            await conn.run_sync(metadata.reflect)

        # 获取所有以Entry_开头的表
        entry_tables = [
            table_name for table_name in metadata.tables
            if table_name.startswith("Entry_")
        ]

        for table_name in entry_tables:
            logger.info(f"正在升级表 {table_name}")
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
            async with engine.begin() as conn:
                await conn.run_sync(new_metadata.create_all)

            # 迁移数据
            async with engine.begin() as conn:
                result = await conn.execute(select(old_table))
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
                    await conn.execute(insert_stmt)

            # 删除旧表，重命名新表
            async with engine.begin() as conn:
                drop_stmt = sa.text(f"DROP TABLE {table_name}")
                await conn.execute(drop_stmt)

                rename_stmt = sa.text(
                    f"ALTER TABLE new_{table_name} RENAME TO {table_name}"
                )
                await conn.execute(rename_stmt)
        await create_version_table(engine, version_num=2)
        logger.info("content.db 升级完成")
        return True  # noqa: TRY300

    except SQLAlchemyError as e:
        logger.error(f"数据库升级出错: {e}")
        return False

async def upgrade_content_db_2_to_3(engine: AsyncEngine) -> bool:
    try:
        logger.info("开始迁移旧数据...")

        # 反射所有表
        metadata = MetaData()
        async with engine.connect() as conn:
            await conn.run_sync(metadata.reflect)

        entry_pattern = re.compile(r"^Entry_(\d+)$")
        async_session = async_sessionmaker(engine, expire_on_commit=False)

        async with async_session() as session:
            for table_name in metadata.tables:
                match = entry_pattern.match(table_name)
                if not match:
                    continue

                entry_id = int(match.group(1))
                old_table = metadata.tables[table_name]

                # 直接 SELECT * 并插入新模型
                result = await session.execute(select(old_table))
                rows = result.fetchall()

                async with get_session() as content_session:
                    for row in rows:
                        # ⚠️ 直接使用原始值，不做任何 parse 或 default
                        new_content = Content(
                            entry_id=entry_id,
                            content=row.content,
                            deleted=row.deleted,
                            date_modified=row.date_modified,
                            date_create=row.date_create,
                        )
                        content_session.add(new_content)

                    await content_session.commit()
                    logger.info(f"已迁移 {len(rows)} 条记录 from {table_name}")

            # 更新 version_num 为 3
            version_table = Table(
                "content_version",
                MetaData(),
                Column("version_num", Integer)
            )
            await session.execute(update(version_table).values(version_num=3))
            await session.commit()
            logger.info("迁移完成，version_num 已设为 3")

        return True  # noqa: TRY300

    except SQLAlchemyError as e:
        logger.exception(f"迁移失败: {e}")
        return False
    finally:
        await engine.dispose()
