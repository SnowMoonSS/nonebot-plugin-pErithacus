import datetime
import json

from nonebot.adapters import Event
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage, Query, AlconnaQuery
from nonebot_plugin_orm import async_scoped_session

from .command import pe
from .database import Index, create_content_list, add_content, get_entry, delete_content, replace_content
from .lib import save_media, load_media, convert_media

@pe.assign("edit")
async def _(
    event: Event,
    session : async_scoped_session,

    keyword: Match[UniMessage] = AlconnaMatch("keyword"),
    matchMethod: Match[str] = AlconnaMatch("matchMethod"),
    isRandom: Match[bool] = AlconnaMatch("isRandom"),
    cron: Match[str] = AlconnaMatch("cron"),
    scope: Match[str] = AlconnaMatch("scope"),
    reg: Match[str] = AlconnaMatch("reg"),
    alias: Match[UniMessage] = AlconnaMatch("alias"),
    delete_id: Query[int] = AlconnaQuery("delete.id", 0),
    replace_id: Query[int] = AlconnaQuery("replace.id", 0),
    content: Query[UniMessage] = AlconnaQuery("replace.content", UniMessage()),
):
    """
    修改词条
    """

    # 处理keyword
    keyword_text = convert_media(keyword.result)
    
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
        scope_list = [this_source]
    else:
        scope_list = scope.result.split(",")
        for s in scope_list:
            if not (scope.result.startswith("g") or scope.result.startswith("u")):
                await pe.finish("scope参数必须以g或u开头")

    # 处理alias
    alias_text = convert_media(alias.result)


    existing_entry = await get_entry(session, keyword_text, scope_list)
    if existing_entry:
        # 更新已有条目（只在用户提供对应参数时修改）
        if matchMethod.available:
            existing_entry.matchMethod = matchMethod.result

        if isRandom.available:
            existing_entry.isRandom = isRandom.result

        if cron.available:
            existing_entry.cron = cron.result

        if scope.available:
            # 合并到已有 JSON 列表（容错解析）
            try:
                scope_list_from_db = json.loads(existing_entry.scope) if existing_entry.scope else []
            except json.JSONDecodeError:
                scope_list_from_db = []
            if not any(item in scope_list_from_db for item in scope_list):
                scope_list_from_db.extend(scope_list)
            existing_entry.scope = json.dumps(scope_list_from_db)

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

        if delete_id.available:
            # 删除指定的内容
            try:
                await delete_content(existing_entry.id, delete_id.result)
            except:
                await pe.finish("删除内容失败，请检查内容编号是否正确")
        
        if replace_id.available and content.available:
            # 替换指定的内容
            try:
                content_text = await save_media(replace_content.result)
                await replace_content(existing_entry.id, replace_id.result, content_text)
                await pe.finish("替换内容成功")
            except:
                await pe.finish("替换内容失败，请检查内容编号是否正确")
        
        await pe.finish("修改词条成功")
    else:
        await pe.finish("词条 " + UniMessage(keyword.result) + " 不存在")