from nonebot import get_plugin_config, get_driver, logger
from nonebot.plugin import PluginMetadata, require

require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_apscheduler")

from .config import Config                    # noqa: E402

from . import database as database            # noqa: E402
from . import lib as lib                      # noqa: E402
from . import command as command              # noqa: E402
from . import add as add                      # noqa: E402
from . import delete as delete                # noqa: E402
from . import edit as edit                    # noqa: E402
from . import list as list                    # noqa: E402
from . import detail as detail                # noqa: E402
from . import search as search                # noqa: E402
from . import trigger as trigger              # noqa: E402
from . import check as check                  # noqa: E402
from . import apscheduler as apscheduler      # noqa: E402

from .apscheduler import load_cron_tasks      # noqa: E402
driver = get_driver()

__version__ = "1.0.8"
__plugin_meta__ = PluginMetadata(
    name="pErithacus",
    description="pErithacus 是一个基于 NoneBot2 框架的聊天插件，可以根据用户设定的关键词自动回复相关内容。该插件提供了完整的词条管理功能，让用户能够轻松创建、编辑和管理自定义回复内容。",
    usage="发送“pe --help”查看帮助",
    type="application",
    homepage="https://github.com/SnowMoonSS/nonebot-plugin-pErithacus",
    supported_adapters={"~onebot.v11"},
)

config = get_plugin_config(Config)

@driver.on_startup
async def _perithacus_load_cron_tasks():
    try:
        await load_cron_tasks()
    except Exception:
        logger.exception("加载定时任务时发生错误")