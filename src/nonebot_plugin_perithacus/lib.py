
import hashlib
import json
import os
import tempfile
from pathlib import Path

import filetype
import httpx
from apscheduler.triggers.cron import CronTrigger
from nonebot import logger
from nonebot.adapters import Event  # noqa: TC002
from nonebot_plugin_alconna import Match, UniMessage
from nonebot_plugin_localstore import get_plugin_data_dir

from .command import pe

media_save_dir = get_plugin_data_dir() / "media"

async def download_media(
        url: str,
        save_dir: Path,
        *,
        json: bool = False
) -> Path | None:
    """
    异步下载文件 → 保存为临时文件 → 计算 MD5 → 识别扩展名 → 重命名为 md5.extension

    :param url: 要下载的 URL
    :param save_dir: 保存目录（需存在）
    :param json: 为 True 时仅返回路径，不进行保存
    :return: 最终文件路径 或 None（失败时）
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    # 创建临时文件（在 save_dir 中）
    with tempfile.NamedTemporaryFile(delete=False, dir=save_dir) as tmp_file:
        tmp_path = Path(tmp_file.name)
        md5_hash = hashlib.md5()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:  # noqa: SIM117
                async with client.stream("GET", url) as response:
                    response.raise_for_status()

                    # 边下载边写入并计算 MD5
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            tmp_file.write(chunk)
                            md5_hash.update(chunk)

            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        except httpx.HTTPError as e:
            # 包括连接错误、超时、4xx/5xx 等
            tmp_path.unlink(missing_ok=True)
            logger.error(f"HTTP 请求失败: {e}")
            return None

        except OSError as e:
            # 文件写入、fsync、磁盘空间、权限等问题
            tmp_path.unlink(missing_ok=True)
            logger.error(f"文件 I/O 错误: {e}")
            return None

    # 识别扩展名（filetype 是同步库，但很快）
    try:
        kind = filetype.guess(str(tmp_path))
        extension = "." + kind.extension if kind else ".bin"
    except OSError as e:
        logger.info(f"文件类型识别失败({tmp_path}): {e}")
        extension = ".bin"

    # 生成最终路径
    md5_hex = md5_hash.hexdigest().upper()
    final_path = save_dir / (md5_hex + extension)

    if json:
        tmp_path.unlink(missing_ok=True)
        return final_path
    if final_path.exists():
        logger.info(f"文件已存在，跳过: {final_path}")
        tmp_path.unlink(missing_ok=True)
        return final_path

    # 重命名
    try:
        tmp_path.rename(final_path)
        logger.info(f"保存成功: {final_path}")
    except OSError as e:
        logger.info(f"重命名失败: {e}")
        tmp_path.unlink(missing_ok=True)
        return None
    else:
        return final_path


async def save_media(data: UniMessage) -> str:
    """
    保存媒体文件
    输入解析得到的元组，返回处理后的JSON数组
    """

    # 将解析得到的元组转换成UniMessage对象
    uni_data = UniMessage(data)
    # 使用UniMessage.dump()方法将UniMessage对象转换成JSON数组
    dumped_uni_data = uni_data.dump(json=True)

    # 处理JSON数组，下载媒体文件并保存
    loadded_data = json.loads(dumped_uni_data)
    for item in loadded_data:
        if "url" in item:
            # 下载文件
            file_path = await download_media(item["url"], media_save_dir)
            item["id"] = file_path.name if file_path else item["id"]
            # 标记为 media
            item["media"] = True
            # 删除url字段
            del item["url"]

    return json.dumps(loadded_data, ensure_ascii=False)

def load_media(data: str) -> UniMessage:
    """
    加载媒体文件
    输入存储的JSON数组字符串，返回包含媒体文件的UniMessage对象
    """

    media_save_dir = get_plugin_data_dir() / "media"

    loadded_data = json.loads(data)
    for item in loadded_data:
        if item.get("media"):
            item["path"] = str(media_save_dir / item["id"])
            del item["media"]

    dumped_data = json.dumps(loadded_data, ensure_ascii=False)
    return UniMessage.load(dumped_data)

async def convert_media(data: UniMessage) -> str:
    """
    输入解析得到的元组，返回处理后的JSON数组，与 save_media 保存下来的格式一致
    """
    uni_data = UniMessage(data)
    dumped_uni_data = uni_data.dump(json=True)
    loaded_data = json.loads(dumped_uni_data)
    for item in loaded_data:
        if "url" in item:
            # 构造文件路径，但不保存
            file_path = await download_media(item["url"], media_save_dir, json=True)
            item["id"] = file_path.name if file_path else item["id"]
            del item["url"]
            item["media"] = True

    return json.dumps(loaded_data, ensure_ascii=False)

def uni_message_to_dumpped_data(data: UniMessage) -> str:
    """
    将 UniMessage 转换为 JSON 数组字符串
    """
    dumped_uni_data = data.dump(json=True)
    loaded_data = json.loads(dumped_uni_data)
    for item in loaded_data:
        if "url" in item:
            del item["url"]
            item["media"] = True

    return json.dumps(loaded_data, ensure_ascii=False)

def get_source(event: Event) -> str:
    """
    获取消息来源
    """
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

    return this_source

async def get_cron(cron: Match) -> None | str:
    """
    验证 cron 表达式的基本格式，
    当用户提供的 cron 参数为 "None" 字符串时，将 cron 设置为 None
    """

    if cron.available:
        if cron.result != "None":
            cron_expressions = cron.result.replace("#", " ")
            try:
                CronTrigger.from_crontab(cron_expressions)
            except ValueError as e:
                logger.error(f"cron参数格式错误: {e}")
                await pe.finish("cron参数格式错误")
        else:
            cron_expressions = None
    else:
        cron_expressions = None

    return cron_expressions

async def get_scope(scope: Match, this_source: str) -> list[str]:
    """
    获取作用域列表
    """
    if not scope.available:
        return [this_source]

    scope_list = scope.result.split(",")
    for s in scope_list:
        if not s.startswith(("g", "u")):
            await pe.finish("scope参数格式错误，应以 'g' 或 'u' 开头")

    return scope_list
