from typing import Any

from arclet.alconna import (
    Alconna,
    Arg,
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
        Args(
            Arg("keyword", Any, notice="词条名"),
            Arg("content", MultiVar(Any), notice="回复内容"),
        ),
        Option(
            "-m|--match",
            Args["match_method#匹配方式（精准/模糊）", "精准|模糊"],
            default="精准"
        ),
        Option("-r|--random", Args["is_random#是否随机回复", bool], default=True),
        Option("-c|--cron", Args["cron#定时触发的cron表达式", str], default=""),
        Option("-s|--scope", Args["scope#作用域", str], default=""),
        Option("-R|--reg", Args["reg#正则匹配的正则表达式", str], default=""),
        Option("-a|--alias", Args["alias#为词条添加别名", str], default=""),
        help_text="添加词条",
    ),
    Subcommand(
        "del|删除",
        Args["keyword#词条名", str],
        Option("-s|--scope", Args["scope#作用域", str], default=""),
        help_text="删除词条。从作用域中删除指定的词条。未指定作用域时，删除当前会话所在的作用域。",
    ),
    Subcommand(
        "list",
        Arg("page?#页码", int, notice="列出指定页的词条"),
        Option("-s|--scope", Args["scope#作用域", str], default=""),
        Option("-a|--all", dest="is_all", default=False, action=store_true),
        Option("-f|--force", dest="is_force", default=False, action=store_true),
        help_text="列出词条",
    ),
    Subcommand(
        "search|搜索",
        Args(
            Arg("keyword", Any, notice="关键词"),
            Arg("page?#页码", int, notice="列出指定页的搜索结果"),
        ),
        Option("-s|--scope", Args["scope#作用域", str], default=""),
        Option("-a|--all", dest="is_all", default=False, action=store_true),
        help_text="搜索词条",
    ),
    Subcommand(
        "check|查看",
        Arg("id", int, notice="词条ID"),
        Option("-f|--force", default=False, action=store_true),
        help_text="查看指定词条的的配置",
    ),
    Subcommand(
        "detail|详情",
        Args(
            Arg("id", int, notice="词条ID"),
            Arg("page?#页码", int, notice="列出指定页的词条内容"),
        ),
        Option("-a|--all", dest="is_all", default=False, action=store_true),
        Option("-f|--force", dest="is_force", default=False, action=store_true),
        help_text="查看指定词条的详细内容",
    ),
    Subcommand(
        "edit|修改",
        Args(
            Arg("keyword", str, notice="词条名"),
        ),
        Option("-r|--random", Args["is_random#是否随机回复", bool], default=True),
        Option(
            "-m|--match",
            Args["match_method#匹配方式（精准/模糊）", "精准|模糊"],
            default="精准"
        ),
        Option("-c|--cron", Args["cron#定时触发的cron表达式", str], default=""),
        Option("-s|--scope", Args["scope#作用域群号", str], default=""),
        Option("-R|--regex", Args["reg#正则匹配的正则表达式", str], default=""),
        Option("-a|--alias", Args["alias#为词条添加别名", str], default=""),
        Option("-d|--delete", Args["delete_id#删除指定id的回复", int], default=0),
        Option(
            "-rep|--replace",
            Args(
                Arg("replace_id", int, notice="将被替换的内容编号"),
                Arg("content", MultiVar(Any), notice="要替换的内容"),
            ),
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


on_every_message = on_message()
