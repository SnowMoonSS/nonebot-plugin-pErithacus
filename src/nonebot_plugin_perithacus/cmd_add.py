import json

from nonebot.adapters import Bot, Event  # noqa: TC002
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage, get_target
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .apscheduler import add_cron_job
from .command import pe
from .database import (
    add_content,
    add_entry,
    get_entry,
    update_entry,
)
from .handle_args import (
    handle_alias,
    handle_cron,
    handle_is_random,
    handle_match_method,
    handle_reg,
    handle_scope,
)
from .lib import (
    get_cron,
    get_scope,
    get_source,
    load_media,
    save_media,
)


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
            update_kwargs = {}
            update_kwargs = handle_match_method(update_kwargs, match_method)
            update_kwargs = handle_is_random(update_kwargs, is_random)
            update_kwargs = await handle_cron(update_kwargs, existing_entry, cron)
            update_kwargs = handle_scope(
                update_kwargs,
                scope_list,
                existing_entry,
                scope
            )
            update_kwargs = handle_reg(update_kwargs, reg)
            update_kwargs = handle_alias(
                update_kwargs,
                alias_text,
                existing_entry,
                alias
            )

            existing_entry = await update_entry(
                session,
                existing_entry,
                **update_kwargs
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

