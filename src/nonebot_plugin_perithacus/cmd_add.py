import json
from datetime import UTC, datetime

from apscheduler.triggers.cron import CronTrigger
from nonebot.adapters import Bot, Event  # noqa: TC002
from nonebot_plugin_alconna import AlconnaMatch, Match, UniMessage, get_target
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .apscheduler import add_cron_job, remove_cron_job
from .command import pe
from .database import Index, add_content, create_content_list, get_entry
from .lib import load_media, save_media


@pe.assign("add")
async def _(
    event: Event,
    bot: Bot,
    session : async_scoped_session,

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


    # 处理keyword
    keyword_text = await save_media(keyword.result)

    # 处理content
    content_text = await save_media(content.result)

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
    alias_text = await save_media(alias.result)


    existing_entry = await get_entry(session, keyword_text, scope_list)
    if existing_entry:
        if await add_content(existing_entry.id, content_text):
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

            if scope.available:
                # 合并到已有 JSON 列表
                try:
                    if existing_entry.scope:
                        scope_list_from_db = json.loads(existing_entry.scope)
                    else:
                        scope_list_from_db = []
                except json.JSONDecodeError:
                    scope_list_from_db = []
                if not any(item in scope_list_from_db for item in scope_list):
                    scope_list_from_db.extend(scope_list)
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
        new_entry = Index(
            keyword = keyword_text,
            match_method = match_method.result if match_method.available else "精准",
            is_random = is_random.result if is_random.available else True,
            cron = cron_expressions if cron.available else None,
            scope = json.dumps(scope_list),
            reg = reg.result if reg.available else None,
            source = this_source,
            target = json.dumps(target.dump()),
            alias = json.dumps([alias_text]) if alias.available else None,
        )
        session.add(new_entry)
        await session.commit()
        await session.refresh(new_entry)
        await create_content_list(f"Entry_{new_entry.id}")
        await add_content(new_entry.id, content_text)
        if cron_expressions:
            add_cron_job(new_entry.id, cron_expressions)

        uni_keyword = load_media(new_entry.keyword)
        await pe.finish(
            f"词条 {new_entry.id} : " + uni_keyword + " 已创建并加入了新的内容"
        )
