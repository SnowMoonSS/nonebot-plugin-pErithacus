from nonebot_plugin_alconna import AlconnaMatch, Match, MsgTarget, UniMessage
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .command import pe
from .database import (
    delete_contents,
    get_contents,
    get_entry,
    replace_content,
    update_entry,
)
from .handle_args import (
    handle_alias,
    handle_cron,
    handle_del_alias,
    handle_is_random,
    handle_match_method,
    handle_reg,
    handle_scope,
)
from .lib import get_num_list, get_scope, get_source, load_media, save_media


@pe.assign("edit")
async def _(  # noqa: PLR0913
    target: MsgTarget,
    session : async_scoped_session,

    keyword: Match[UniMessage] = AlconnaMatch("keyword"),
    match_method: Match[str] = AlconnaMatch("match_method"),
    is_random: Match[bool] = AlconnaMatch("is_random"),
    cron: Match[str] = AlconnaMatch("cron"),
    scope: Match[str] = AlconnaMatch("scope"),
    reg: Match[str] = AlconnaMatch("reg"),
    alias: Match[UniMessage] = AlconnaMatch("alias"),
    del_alias_id: Match[str] = AlconnaMatch("del_alias_id"),
    del_content_id: Match[str] = AlconnaMatch("del_content_id"),
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
        or del_alias_id.available
        or del_content_id.available
        or replace_id.available
    ):
        await pe.finish("未提供修改项")

    keyword_text = await save_media(keyword.result)
    content_text = await save_media(content.result)
    this_source = get_source(target)
    scope_list = await get_scope(scope, this_source)
    alias_text = await save_media(alias.result)

    uni_keyword = load_media(keyword_text)

    existing_entry = await get_entry(session, keyword_text, scope_list)
    if not existing_entry:
        await pe.finish("词条: " + UniMessage(keyword.result) + " 不存在")

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
    update_kwargs = await handle_del_alias(update_kwargs, del_alias_id, existing_entry)
    update_kwargs = handle_alias(
        update_kwargs,
        alias_text,
        existing_entry,
        alias
    )

    msg = UniMessage()

    if del_content_id.available:
        # 检查 del_content_id.result 中的所有 id 是否存在于 existing_entry 中
        content_ids = await get_num_list(del_content_id.result)
        existing_content_ids = [
            content.id for content in await get_contents(session, existing_entry.id)
        ]
        invalid_ids = [cid for cid in content_ids if cid not in existing_content_ids]
        if invalid_ids:
            await pe.finish(
                f"编号 {invalid_ids} 的内容不存在于 {uni_keyword} 中，请检查后重试"
            )
        # 删除指定的内容
        result = await delete_contents(session, del_content_id.result)
        if result.success:
            msg.append("删除内容成功！\n")
        else:
            msg.append(f"删除内容失败，失败的内容编号有：{result.failed_ids}，请检查内容编号是否正确\n")

    if replace_id.available and content.available:
        existing_content_ids = [
            content.id for content in await get_contents(session, existing_entry.id)
        ]
        if replace_id.result not in existing_content_ids:
            await pe.finish(
                f"内容编号 {replace_id.result} 不存在于词条 {uni_keyword} 中，"
                "请检查后重试"
            )
        if await replace_content(
            session,
            existing_entry.id,
            replace_id.result,
            content_text
        ):
            msg.append("替换内容成功！\n")
        else:
            msg.append("替换内容失败，请检查内容编号是否正确\n")

    existing_entry = await update_entry(
        session,
        existing_entry,
        **update_kwargs
    )

    msg.append(f"词条 {existing_entry.id} : " + uni_keyword + " 修改成功！")

    await session.commit()
    await pe.finish(msg)
