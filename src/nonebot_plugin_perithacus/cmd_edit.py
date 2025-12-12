import json
from datetime import UTC, datetime

from apscheduler.triggers.cron import CronTrigger
from nonebot import logger
from nonebot.adapters import Event  # noqa: TC002
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .apscheduler import add_cron_job, remove_cron_job
from .command import pe
from .database import add_content, delete_content, get_entry
from .lib import convert_media, save_media


@pe.assign("edit")
async def _(
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

    # 处理keyword
    keyword_text = await convert_media(keyword.result)

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

    # 验证 cron 表达式的基本格式，
    # 当用户提供的 cron 参数为 "None" 字符串时，将 cron 设置为 None
    if cron.available:
        if cron.result != "None":
            cron_expressions = cron.result.replace("#", " ")
            try:
                CronTrigger.from_crontab(cron_expressions)
            except ValueError:
                await pe.finish("cron参数格式错误")
        else:
            cron_expressions = None
    else:
        cron_expressions = None

    # 处理scope
    if not scope.available:
        scope_list = [this_source]
    else:
        scope_list = scope.result.split(",")
        for s in scope_list:
            if not s.startswith(("g", "u")):
                await pe.finish("scope参数必须以g或u开头")

    # 处理alias
    alias_text = convert_media(alias.result)


    existing_entry = await get_entry(session, keyword_text, scope_list)
    if existing_entry:
        # 更新已有条目（只在用户提供对应参数时修改）
        if match_method.available:
            existing_entry.match_method = match_method.result

        if is_random.available:
            existing_entry.is_random = is_random.result

        if cron.available:
            existing_entry.cron = cron_expressions
            if cron_expressions:
                add_cron_job(existing_entry.id, cron_expressions)
            else:
                remove_cron_job(existing_entry.id)

        # 将新作用域合并到已有 JSON 列表
        # 在作用域内执行del命令移除指定作用域
        if scope.available:
            try:
                if existing_entry.scope:
                    scope_list_from_db = json.loads(existing_entry.scope)
                else:
                    scope_list_from_db = []
            except json.JSONDecodeError:
                scope_list_from_db = []
            for item in scope_list:
                if item not in scope_list_from_db:
                    scope_list_from_db.append(item)
                    logger.debug(f"添加新的作用域：{item}")
            existing_entry.scope = json.dumps(scope_list_from_db)

        # 合并到已有 JSON 列表
        if alias.available:
            # 解析已有别名列表
            if existing_entry.alias:
                alias_list = json.loads(existing_entry.alias)
            else:
                alias_list = []
            new_alias = alias_text
            if new_alias and new_alias not in alias_list:
                alias_list.append(new_alias)
            existing_entry.alias = json.dumps(alias_list) if alias_list else None

        if reg.available:
            existing_entry.reg = reg.result

        existing_entry.date_modified=datetime.now(UTC)

        # 提交修改并刷新实体
        session.add(existing_entry)
        await session.commit()
        await session.refresh(existing_entry)
        msg = UniMessage(
            f"词条 {existing_entry.id} : " + UniMessage(keyword.result) + " 修改成功！"
        )

        if delete_id.available:
            # 删除指定的内容
            result = await delete_content(existing_entry.id, delete_id.result)
            if result:
                msg.append("\n删除内容成功！")
            else:
                msg.append("\n删除内容失败，请检查内容编号是否正确")

        if replace_id.available and content.available:
            # 将被替换的内容标记为已删除
            delete = await delete_content(existing_entry.id, replace_id.result)

            # 添加新的内容
            content_text = await save_media(content.result)
            add = await add_content(existing_entry.id, content_text)
            if delete and add:
                msg.append("\n替换内容成功！")
            else:
                msg.append("\n替换内容失败，请检查内容编号是否正确")

        await pe.finish(msg)
    else:
        await pe.finish("词条: " + UniMessage(keyword.result) + " 不存在")
