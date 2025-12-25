from nonebot import get_driver, logger
from nonebot.plugin import PluginMetadata, require

require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_orm")
require("nonebot_plugin_apscheduler")

from sqlalchemy.exc import OperationalError, ProgrammingError

from . import apscheduler as apscheduler
from . import cmd_add as cmd_add
from . import cmd_check as cmd_check
from . import cmd_delete as cmd_delete
from . import cmd_detail as cmd_detail
from . import cmd_edit as cmd_edit
from . import cmd_list as cmd_list
from . import cmd_search as cmd_search
from . import command as command
from . import database as database
from . import handle_args as handle_args
from . import lib as lib
from . import trigger as trigger
from .apscheduler import load_cron_tasks
from .upgrade_database import upgrade_content_db

driver = get_driver()

__version__ = "1.2.0"
__plugin_meta__ = PluginMetadata(
    name="pErithacus",
    description=("pErithacus 是一个基于 NoneBot2 框架的聊天插件，"
                "可以根据用户设定的关键词自动回复相关内容。"
                "该插件提供了完整的词条管理功能，让用户能够轻松创建、编辑和管理自定义回复内容。"),
    usage="发送“pe --help”查看帮助",
    type="application",
    homepage="https://github.com/SnowMoonSS/nonebot-plugin-pErithacus",
    supported_adapters=None,
)

@driver.on_startup
async def _load_perithacus():
    try:
        await load_cron_tasks()
    except (OperationalError, ProgrammingError) as e:
        logger.exception("数据库操作失败，无法加载定时任务: %s", e)
    except ValueError as e:
        logger.exception("发现无效的 cron 表达式: %s", e)
    except RuntimeError as e:
        logger.exception("运行时错误（如调度器未初始化）: %s", e)

    await upgrade_content_db()
