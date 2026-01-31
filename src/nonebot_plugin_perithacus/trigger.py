import random

from nonebot.log import logger
from nonebot_plugin_alconna import MsgTarget, UniMessage, UniMsg
from nonebot_plugin_orm import async_scoped_session  # noqa: TC002

from .command import on_every_message
from .database import get_contents, get_entry
from .lib import dump_msg, get_source, load_msg


@on_every_message.handle()
async def _(
    target: MsgTarget,
    session: async_scoped_session,
    uni_msg: UniMsg,
):
    msg_text = await dump_msg(uni_msg, media_save_dir=False)
    logger.debug(f"收到消息: {msg_text}")

    this_source = get_source(target)
    scope_list = [this_source]

    existing_entry = await get_entry(session, msg_text, scope_list)
    if existing_entry:
        logger.debug(f"找到匹配的词条 ID {existing_entry.id}")
        contents = await get_contents(session, existing_entry.id)
        if contents:
            logger.debug("找到匹配的词条内容")
            if existing_entry.is_random:
                content = random.choice(contents)
                logger.debug(f"随机选择内容 ID {content.id} 进行发送")
            else:
                content = max(contents, key=lambda x: x.date_modified)
                logger.debug(f"选择最新内容 ID {content.id} 进行发送")
            await UniMessage.finish(load_msg(content.content))
        else:
            logger.debug("所有内容已标记为已删除")
            await on_every_message.finish()
    else:
        logger.debug("Trigger 未找到匹配的词条")
        await on_every_message.finish()
