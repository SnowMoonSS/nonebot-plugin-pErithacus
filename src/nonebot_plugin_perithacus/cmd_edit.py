
from nonebot.adapters import Event  # noqa: TC002
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .command import pe
from .database import (
    delete_content,
    get_entry,
    replace_content,
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
    get_scope,
    get_source,
    load_media,
    save_media,
)


@pe.assign("edit")
async def _(  # noqa: PLR0913
    event: Event,
    session : async_scoped_session,

    keyword: Match[UniMessage] = AlconnaMatch("keyword"),
    match_method: Match[str] = AlconnaMatch("match_method"),
    is_random: Match[bool] = AlconnaMatch("is_random"),
    cron: Match[str] = AlconnaMatch("cron"),
    scope: Match[str] = AlconnaMatch("scope"),
    reg: Match[str] = AlconnaMatch("reg"),
    alias: Match[UniMessage] = AlconnaMatch("alias"),
    delete_id: Match[int] = AlconnaMatch("delete_id"),
    replace_id: Match[int] = AlconnaMatch("replace_id"),
    content: Match[UniMessage] = AlconnaMatch("content"),
):
    """
    修改词条
    """

    if not (
        match_method.available
        or is_random.available
        or cron.available
        or scope.available
        or reg.available
        or alias.available
        or delete_id.available
        or replace_id.available
    ):
        await pe.finish("未提供修改项")

    keyword_text = await save_media(keyword.result)
    content_text = await save_media(content.result)
    this_source = get_source(event)
    scope_list = await get_scope(scope, this_source)
    alias_text = await save_media(alias.result)

    existing_entry = await get_entry(session, keyword_text, scope_list)
    if existing_entry:
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
        msg = UniMessage(
            f"词条 {existing_entry.id} : " + uni_keyword + " 修改成功！"
        )

        if delete_id.available:
            # 删除指定的内容
            result = await delete_content(session, delete_id.result)
            if result:
                msg.append("\n删除内容成功！")
            else:
                msg.append("\n删除内容失败，请检查内容编号是否正确")

        if replace_id.available and content.available:
            if await replace_content(
                session,
                existing_entry.id,
                replace_id.result,
                content_text
            ):
                msg.append("\n替换内容成功！")
            else:
                msg.append("\n替换内容失败，请检查内容编号是否正确")

        await pe.finish(msg)
    else:
        await pe.finish("词条: " + UniMessage(keyword.result) + " 不存在")
