from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata, require

require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_apscheduler")

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


__plugin_meta__ = PluginMetadata(
    name="pErithacus",
    description="根据设置的关键词进行回复",
    usage="发送“pe --help”查看帮助",
    config=Config,
)

config = get_plugin_config(Config)
