import datetime
from nonebot_plugin_orm import Model
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, Text, DateTime
from typing import Optional

class index(Model):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(Text, nullable=False, comment="词条名")
    matchMethod: Mapped[str] = mapped_column(String(8), default="精准", comment="匹配方式")
    isRandom: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否随机回复")
    cron: Mapped[Optional[str]] = mapped_column(String(64), default="", comment="定时cron表达式")
    scope: Mapped[str] = mapped_column(Text, default="", comment="作用域（数组，每个数组代表一个作用域）")
    reg: Mapped[Optional[str]] = mapped_column(Text, default="", comment="正则表达式")
    source: Mapped[str] = mapped_column(Text, default="", comment="来源")
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否删除")
    alias: Mapped[Optional[str]] = mapped_column(Text, default="", comment="别名（数组，每个数组代表一个别名）")
    timap: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now, comment="时间戳")


from sqlalchemy import create_engine, MetaData, Table, Column, Integer
from nonebot_plugin_datastore import get_plugin_data

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