from nonebot import get_plugin_config, get_driver, logger
from nonebot.plugin import PluginMetadata, require

driver = get_driver()

require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_apscheduler")

from nonebot_plugin_orm import get_session

from .config import Config

from . import database
from . import lib
from . import command
from . import add
from . import delete
from . import edit
from . import list
from . import detail
from . import search
from . import trigger
from . import check
from . import apscheduler

from .apscheduler import load_cron_tasks


__plugin_meta__ = PluginMetadata(
    name="pErithacus",
    description="根据设置的关键词进行回复",
    usage="发送“pe --help”查看帮助",
    config=Config,
)

config = get_plugin_config(Config)

@driver.on_startup
async def _perithacus_load_cron_tasks():
    try:
        await load_cron_tasks()
    except Exception:
        logger.exception("加载定时任务时发生错误")