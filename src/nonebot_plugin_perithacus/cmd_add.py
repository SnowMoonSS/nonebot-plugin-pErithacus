import json

from nonebot import logger
from nonebot_plugin_alconna import (
    AlconnaMatch,
    Match,
    MsgTarget,
    UniMessage,
    UniMsg,
)
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
    handle_main_args,
    handle_match_method,
    handle_reg,
    handle_scope,
)
from .lib import dump_msg, get_cron, get_scope, get_source, load_media


@pe.assign("add")
async def _(  # noqa: PLR0913
    target: MsgTarget,
    uni_msg: UniMsg,
    session: async_scoped_session,

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

    main_args = await handle_main_args(uni_msg, "add")
    keyword_text = await dump_msg(main_args.keyword)
    logger.debug(f"Keyword: {keyword_text}")
    content_text = await dump_msg(main_args.content)
    logger.debug(f"Content: {content_text}")
    this_source = get_source(target)
    cron_expressions = await get_cron(cron)
    scope_list = await get_scope(scope, this_source)
    if main_args.alias:
        alias_text = await dump_msg(main_args.alias)
        logger.debug(f"Alias: {alias_text}")
    else:
        alias_text = "" # 未提供别名时，这里无论是什么值都无所谓。此处仅防止后面出现 alisa_text 未定义的错误。

    existing_entry = await get_entry(session, keyword_text, scope_list)
    if existing_entry:
        add_content_result = await add_content(session, existing_entry.id, content_text)
        if add_content_result.success:
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
            entry_id = existing_entry.id
            await session.commit()

            uni_keyword = load_media(keyword_text)
            await pe.finish(
                f"词条 {entry_id} : " + uni_keyword + " 加入了新的内容："
                f"{add_content_result.content_id}"
            )
        else:
            uni_keyword = load_media(keyword_text)
            await pe.finish(
                f"词条 {existing_entry.id} : " + uni_keyword + " 已存在该内容："
                f"{add_content_result.content_id}",
                reply_to=True
            )
    else:
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
            alias = json.dumps([alias_text] if alias.available and alias_text else None)
        )

        await session.flush()

        add_content_result = await add_content(session, new_entry.id, content_text)

        if cron_expressions:
            add_cron_job(new_entry.id, cron_expressions)

        entry_id = new_entry.id
        await session.commit()

        uni_keyword = load_media(keyword_text)
        await pe.finish(
            f"词条 {entry_id} : " + uni_keyword + " 已创建并加入了新的内容："
            f"{add_content_result.content_id}"
        )
