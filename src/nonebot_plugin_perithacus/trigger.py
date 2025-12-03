import random

from nonebot.adapters import Event  # noqa: TC002
from nonebot.log import logger
from nonebot_plugin_alconna import UniMessage, UniMsg
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .command import on_every_message
from .database import get_contents, get_entry
from .lib import load_media, uni_message_to_dumpped_data


@on_every_message.handle()
async def _(
    event: Event,
    session : async_scoped_session,
    msg: UniMsg,
):
    msg_text = uni_message_to_dumpped_data(msg)

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
    scope_list = [this_source]

    existing_entry = await get_entry(session, msg_text, scope_list)
    if existing_entry:
        logger.debug(f"找到匹配的词条 ID {existing_entry.id}")
        contents = await get_contents(existing_entry.id)
        if contents:
            logger.debug("找到匹配的词条内容")
            if existing_entry.is_random:
                content = random.choice(contents)
                logger.debug(f"随机选择内容 ID {content.id} 进行发送")
            else:
                content = max(contents, key=lambda x: x.date_modified)
                logger.debug(f"选择最新内容 ID {content.id} 进行发送")
            await UniMessage.finish(load_media(content.content))
        else:
            logger.debug("所有内容已标记为已删除")
            await on_every_message.finish()
    else:
        logger.debug("Trigger 未找到匹配的词条")
        await on_every_message.finish()
