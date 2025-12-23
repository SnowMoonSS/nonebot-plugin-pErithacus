import json

from nonebot.adapters import Bot, Event  # noqa: TC002
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage, get_target
from nonebot_plugin_orm import AsyncSession, async_scoped_session  # noqa: TC002

from .apscheduler import add_cron_job, remove_cron_job
from .command import pe
from .database import (
    Index,
    add_content,
    add_entry,
    get_entry,
    update_entry,
)
from .lib import get_cron, get_scope, get_source, load_media, save_media

call_kwargs = {}

@pe.assign("add")
async def _(  # noqa: PLR0913
    event: Event,
    bot: Bot,
    session: async_scoped_session,

    keyword: Match[UniMessage] = AlconnaMatch("keyword"),
    content: Match[UniMessage] = AlconnaMatch("content"),
    match_method: Match[str] = AlconnaMatch("match_method"),
    is_random: Match[bool] = AlconnaMatch("is_random"),
    cron: Match[str] = AlconnaMatch("cron"),
    scope: Match[str] = AlconnaMatch("scope"),
    reg: Match[str] = AlconnaMatch("reg"),
    alias: Match[UniMessage] = AlconnaMatch("alias"),
):
    """
    添加词条
    """


    keyword_text = await save_media(keyword.result)
    content_text = await save_media(content.result)
    this_source = get_source(event)
    cron_expressions = await get_cron(cron)
    scope_list = await get_scope(scope, this_source)
    alias_text = await save_media(alias.result)

    existing_entry = await get_entry(session, keyword_text, scope_list)
    if existing_entry:
        if await add_content(session, existing_entry.id, content_text):
            handle_match_method(match_method)
            handle_is_random(is_random)
            await handle_cron(existing_entry, cron)
            handle_scope(scope_list, existing_entry, scope)
            handle_reg(reg)
            handle_alias(alias_text, existing_entry, alias)

            existing_entry = await update_entry(
                session,
                existing_entry,
                **call_kwargs
            )

            uni_keyword = load_media(existing_entry.keyword)
            await pe.finish(
                f"词条 {existing_entry.id} : " + uni_keyword + " 加入了新的内容"
            )
        else:
            uni_keyword = load_media(existing_entry.keyword)
            await pe.finish(
                f"词条 {existing_entry.id} : " + uni_keyword + " 已存在该内容",
                reply_to=True
            )
    else:
        target = get_target(event, bot)
        # 构建新词条对象，只在参数被提供时使用用户输入，否则使用数据库模型的默认值
        new_entry = await add_entry(
            session,
            keyword = keyword_text,
            match_method = match_method.result if match_method.available else "精准",
            is_random = is_random.result if is_random.available else True,
            cron = cron_expressions if cron.available else None,
            scope = json.dumps(scope_list),
            reg = reg.result if reg.available else None,
            source = this_source,
            target = json.dumps(target.dump()),
            alias = (
                json.dumps([alias_text])
                if (alias.available and alias_text)
                else None)
        )
        await add_content(session, new_entry.id, content_text)
        if cron_expressions:
            add_cron_job(new_entry.id, cron_expressions)

        uni_keyword = load_media(new_entry.keyword)
        await pe.finish(
            f"词条 {new_entry.id} : " + uni_keyword + " 已创建并加入了新的内容"
        )

def handle_match_method(match_method: Match) -> None:
    if match_method.available:
        call_kwargs["match_method"] = match_method.result

def handle_is_random(is_random: Match) -> None:
    if is_random.available:
        call_kwargs["is_random"] = is_random.result

async def handle_cron(
    entry: Index,
    cron: Match
) -> None:
    if cron.available:
        cron_expressions = await get_cron(cron)
        call_kwargs["cron"] = cron_expressions
        if cron_expressions:
            add_cron_job(entry.id, cron_expressions)
        else:
            remove_cron_job(entry.id)

def handle_scope(scope_list: list, entry: Index, scope: Match) -> None:
    if scope.available:
        try:
            scope_list_from_db = json.loads(entry.scope) if entry.scope else []
        except json.JSONDecodeError:
            scope_list_from_db = []
        if not any(item in scope_list_from_db for item in scope_list):
            scope_list_from_db.extend(scope_list)
        call_kwargs["scope"] = json.dumps(scope_list_from_db)

def handle_alias(alias_text: str, entry: Index, alias: Match) -> None:
    if alias.available:
        # 解析已有别名列表
        alias_list = json.loads(entry.alias) if entry.alias else []
        new_alias = alias_text
        if new_alias and new_alias not in alias_list:
            alias_list.append(new_alias)
        call_kwargs["alias"] = json.dumps(alias_list) if alias_list else None

def handle_reg(reg: Match) -> None:
    if reg.available:
        call_kwargs["reg"] = reg.result
