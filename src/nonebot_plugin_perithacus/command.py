from typing import Any

from arclet.alconna import (
    Alconna,
    Args,
    CommandMeta,
    MultiVar,
    Option,
    Subcommand,
    store_true,
)
from nonebot import on_message
from nonebot_plugin_alconna import on_alconna

perithacus = Alconna(
    "perithacus",
    Subcommand(
        "add|添加",
        Args["keyword#词条名", Any]["content#回复内容", MultiVar(Any)],
        Option(
            "-m|--match",
            Args["match_method#匹配方式（精准/模糊）", "精准|模糊"],
            default="精准"
        ),
        Option("-r|--random", Args["is_random#是否随机回复", bool], default=True),
        Option("-c|--cron", Args["cron#定时触发的cron表达式", str], default=""),
        Option("-s|--scope", Args["scope#作用域", str], default=""),
        Option("-g|--reg", Args["reg#正则匹配的正则表达式", str], default=""),
        Option("-a|--alias", Args["alias#为词条添加别名", Any], default=""),
        help_text="添加词条",
    ),
    Subcommand(
        "del|删除",
        Args["keyword#词条名", Any],
        Option("-s|--scope", Args["scope#作用域", str], default=""),
        help_text="删除词条。从作用域中删除指定的词条。未指定作用域时，删除当前会话所在的作用域。",
    ),
    Subcommand(
        "list",
        Args["page?#页码，列出指定页的词条", int],
        Option("-s|--scope", Args["scope#作用域", str], default=""),
        Option("-a|--all", dest="is_all", default=False, action=store_true),
        Option("-f|--force", dest="is_force", default=False, action=store_true),
        help_text="列出词条",
    ),
    Subcommand(
        "search|搜索",
        Args["keyword#关键词", Any]["page?#页码，列出指定页的搜索结果", int],
        Option("-s|--scope", Args["scope#作用域", str], default=""),
        Option("-a|--all", dest="is_all", default=False, action=store_true),
        help_text="搜索词条",
    ),
    Subcommand(
        "check|查看",
        Args["id#词条ID", int],
        Option("-f|--force", default=False, action=store_true),
        help_text="查看指定词条的的配置",
    ),
    Subcommand(
        "detail|详情",
        Args["id#词条ID", int]["page?#页码，列出指定页的词条内容", int],
        Option("-a|--all", dest="is_all", default=False, action=store_true),
        Option("-f|--force", dest="is_force", default=False, action=store_true),
        help_text="查看指定词条的详细内容",
    ),
    Subcommand(
        "edit|修改",
        Args["keyword#词条名", Any],
        Option("-r|--random", Args["is_random#是否随机回复", bool], default=True),
        Option(
            "-m|--match",
            Args["match_method#匹配方式（精准/模糊）", "精准|模糊"],
            default="精准"
        ),
        Option("-c|--cron", Args["cron#定时触发的cron表达式", str], default=""),
        Option("-s|--scope", Args["scope#作用域群号", str], default=""),
        Option("-g|--regex", Args["reg#正则匹配的正则表达式", str], default=""),
        Option("-a|--alias", Args["alias#为词条添加别名", Any], default=""),
        Option(
            "-A|--del_alias",
            Args["del_alias_id#删除指定序号的别名", str],
            default=""
        ),
        Option(
            "-C|--del_content",
            Args["del_content_id#删除指定id的内容", str],
            default=""
        ),
        Option(
            "-p|--replace",
            Args["replace_id#将被替换的内容编号", int]
                ["content#要替换的内容", MultiVar(Any)],
            help_text="替换指定id的回复",
        ),
        help_text="修改词条",
    ),
    meta=CommandMeta(
        keep_crlf=True,
    )
)
pe = on_alconna(perithacus, skip_for_unmatch=False, use_cmd_start=True, aliases={"pe"})

@pe.assign("$main")
async def handle_main() -> None:
    await pe.finish("发送“pe --help”查看帮助")


on_every_message = on_message(block=False)
