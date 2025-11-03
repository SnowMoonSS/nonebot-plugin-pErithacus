import datetime
import json

from nonebot import logger
from nonebot.adapters import Event
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage
from nonebot_plugin_orm import async_scoped_session

from .command import pe
from .database import Index, create_content_list, add_content, get_id, get_entry
from .lib import save_media, load_media

@pe.assign("add")
async def _(
    event: Event,
    session : async_scoped_session,

    keyword: Match[UniMessage] = AlconnaMatch("keyword"),
    content: Match[UniMessage] = AlconnaMatch("content"),
    matchMethod: Match[str] = AlconnaMatch("matchMethod"),
    isRandom: Match[bool] = AlconnaMatch("isRandom"),
    cron: Match[str] = AlconnaMatch("cron"),
    scope: Match[str] = AlconnaMatch("scope"),
    reg: Match[str] = AlconnaMatch("reg"),
    alias: Match[UniMessage] = AlconnaMatch("alias"),
):
    """
    添加词条
    """

    # 处理keyword
    keyword_text = save_media(keyword.result)

    # 处理content
    content_text = save_media(content.result)

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

    # 处理alias
    alias_text = save_media(alias.result)


    existing_entry = await get_entry(session, keyword_text, thescope)
    if existing_entry:
        # 更新已有条目（只在用户提供对应参数时修改）
        if matchMethod.available:
            existing_entry.matchMethod = matchMethod.result

        if isRandom.available:
            existing_entry.isRandom = isRandom.result

        if cron.available:
            existing_entry.cron = cron.result

        # 合并到已有 JSON 列表（容错解析）
        if alias.available:
            # 解析已有别名列表
            alias_list = json.loads(existing_entry.alias) if existing_entry.alias else []
            new_alias = alias_text
            if new_alias and new_alias not in alias_list:
                alias_list.append(new_alias)
            existing_entry.alias = json.dumps(alias_list) if alias_list else None

        if reg.available:
            existing_entry.reg = reg.result

        existing_entry.dateModfied=datetime.datetime.now()

        # 提交修改并刷新实体
        session.add(existing_entry)
        await session.commit()
        await session.refresh(existing_entry)

        add_content(f"Entry_{existing_entry.id}", content_text)

        uni_keyword = load_media(existing_entry.keyword)
        uni_content = load_media(content_text)
        await pe.finish(UniMessage("词条：" + uni_keyword + "加入了新的内容：" + uni_content))
    else:
        # 构建新词条对象，只在参数被提供时使用用户输入，否则使用数据库模型的默认值
        new_entry = Index(
            keyword=keyword_text,
            matchMethod=matchMethod.result if matchMethod.available else "精准",
            isRandom=isRandom.result if isRandom.available else True,
            cron=cron.result if cron.available else None,
            scope=json.dumps([thescope]),
            reg=reg.result if reg.available else None,
            source=this_source,
            alias=json.dumps([alias_text]) if alias.available else None,
        )
        session.add(new_entry)
        await session.commit()
        await session.refresh(new_entry)
        create_content_list(f"Entry_{new_entry.id}")
        add_content(f"Entry_{new_entry.id}", content_text)

        uni_keyword = load_media(keyword_text)
        uni_content = load_media(content_text)
        await pe.finish(UniMessage("词条：" + uni_keyword + "已创建并加入了新的内容：" + uni_content))