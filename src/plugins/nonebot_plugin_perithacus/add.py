import datetime
import json
from nonebot.adapters import Event
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage, Arparma, UniMsg
from nonebot_plugin_orm import get_session
from sqlalchemy import select

from .command import pe
from .database import index, create_content_list, add_content

@pe.assign("add")
async def _(
    event: Event,

    keyword: Match[str] = AlconnaMatch("keyword"),
    content: Match[UniMessage] = AlconnaMatch("content"),
    matchMethod: Match[str] = AlconnaMatch("matchMethod"),
    isRandom: Match[bool] = AlconnaMatch("isRandom"),
    cron: Match[str] = AlconnaMatch("cron"),
    scope: Match[str] = AlconnaMatch("scope"),
    reg: Match[str] = AlconnaMatch("reg"),
    alias: Match[str] = AlconnaMatch("alias"),
):
    """
    添加词条
    """

    # 处理content
    content_text = serialize_content(content.result)

    # 处理source
    session_id = event.get_session_id()
    # 根据 session_id 格式设置 source 变量
    if session_id.startswith("group_"):
        # group_{groupid}_{userid} 格式，提取 groupid
        group_id = session_id.split("_")[1]
        this_source = f"g{group_id}"
    else:
        # {userid} 格式，直接使用 userid
        user_id = session_id
        this_source = f"u{user_id}"
    
    # 处理scope
    if not scope.available:
        thescope = this_source
    else:
        if not (scope.result.startswith("g") or scope.result.startswith("u")):
            await pe.finish("scope参数必须以g或u开头")
        thescope = scope.result


    existing_entry_id = None
    async with get_session() as session:
        # 查询是否存在相同keyword或keyword存在于alias中的词条
        existing_entries = await session.execute(
            select(index).where(
                index.deleted == False
            )
        )
        existing_entries = existing_entries.scalars().all()

        filtered_entries = []
        for entry in existing_entries:
            try:
                scope_list = json.loads(entry.scope) if entry.scope else []
                if thescope in scope_list:
                    filtered_entries.append(entry)
            except json.JSONDecodeError:
                pass

        # 检查keyword是否已存在（作为主keyword或在alias中）
        for entry in existing_entries:
            # 检查是否直接匹配keyword
            if entry.keyword == keyword.result:
                existing_entry_id = entry.id
                break
            
            # 检查keyword是否存在于alias中
            try:
                alias_list = json.loads(entry.alias) if entry.alias else []
                if keyword.result in alias_list:
                    existing_entry_id = entry.id
                    break
            except json.JSONDecodeError:
                # 如果alias不是有效的JSON，跳过检查
                pass

    if existing_entry_id:
        add_content(f"Entry_{existing_entry_id}", content_text)
        await pe.finish(f"词条 {keyword.result} 加入了新的内容：{content_text}")
    else:
        # 构建新词条对象，只在参数被提供时使用用户输入，否则使用数据库模型的默认值
        entry_kwargs = {
            "keyword": keyword.result,
            "source": this_source,
            "deleted": False,
            "timap": datetime.datetime.now()
        }
        
        # 只有当参数被提供时才添加到entry_kwargs中，让数据库使用默认值
        if matchMethod.available:
            entry_kwargs["matchMethod"] = matchMethod.result
            
        if isRandom.available:
            entry_kwargs["isRandom"] = isRandom.result
            
        if cron.available:
            entry_kwargs["cron"] = cron.result
        else:
            entry_kwargs["cron"] = ""  # 显式设置默认值
            
        entry_kwargs["scope"] = json.dumps([thescope])
            
        if reg.available:
            entry_kwargs["reg"] = reg.result
        else:
            entry_kwargs["reg"] = ""  # 显式设置默认值
            
        if alias.available:
            entry_kwargs["alias"] = json.dumps([alias.result])
        else:
            entry_kwargs["alias"] = json.dumps([])  # 显式设置默认值

        new_entry = index(**entry_kwargs)
        
        async with get_session() as session:
            session.add(new_entry)
            await session.commit()
            await session.refresh(new_entry)
            new_entry_id = new_entry.id
            
        create_content_list(f"Entr_{new_entry_id}")
        add_content(f"Entry_{new_entry_id}", content_text)
        await pe.finish(f"词条 {keyword.result} 创建成功")


def serialize_content(content: UniMessage) -> str:
    """
    序列化 UniMessage 内容为 JSON 字符串存储
    """
    try:
        return json.dumps(content.dump(), ensure_ascii=False)
    except Exception:
        # 如果序列化失败，退化为普通字符串
        return str(content)

def deserialize_content(data: str) -> UniMessage:
    """
    从存储的 JSON 字符串反序列化为 UniMessage
    """
    try:
        segments_data = json.loads(data)
        return UniMessage.load(segments_data)
    except Exception:
        # 如果反序列化失败，创建简单的文本消息
        return UniMessage(data)