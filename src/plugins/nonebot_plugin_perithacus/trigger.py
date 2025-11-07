import json
import random

from arclet.alconna import Alconna, Args, Option, Arparma
from nonebot.log import logger
from nonebot.adapters import Event
from nonebot_plugin_alconna import AlconnaQuery, AlcResult, Match, Query, on_alconna, UniMessage, AlconnaMatch, Extension
from nonebot_plugin_orm import async_scoped_session

from .command import all
from .lib import uni_message_to_dumpped_data, load_media
from .database import get_entry, get_contents

@all.handle()
async def _(
    event: Event,
    session : async_scoped_session,
):
    msg = UniMessage.of(event.get_message())
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
        contents = await get_contents(existing_entry.id)
        if existing_entry.isRandom:
            content = random.choice(contents)
        else:
            content = max(contents, key=lambda x: x.timap)
        send = await UniMessage.export(load_media(content.content))
        await all.finish(send)
    else:
        await all.finish()
