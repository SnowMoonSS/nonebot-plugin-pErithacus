import base64
import hashlib
import json
import os
import re
import tempfile
from dataclasses import fields
from io import BytesIO
from pathlib import Path
from typing import Any

import filetype
import httpx
from apscheduler.triggers.cron import CronTrigger
from nonebot import get_driver, logger
from nonebot.internal.driver import Driver, HTTPClientMixin, Request
from nonebot_plugin_alconna import Match, MsgTarget, Segment, UniMessage
from nonebot_plugin_alconna.uniseg.segment import Media
from nonebot_plugin_localstore import get_plugin_data_dir

from .command import pe

MEDIA_SAVE_DIR = get_plugin_data_dir() / "media"

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
            file_path = await download_media(item["url"], MEDIA_SAVE_DIR)
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

    loadded_data = json.loads(data)
    for item in loadded_data:
        if item.get("media"):
            item["path"] = str(MEDIA_SAVE_DIR / item["id"])
            del item["media"]

    dumped_data = json.dumps(loadded_data, ensure_ascii=False)
    return UniMessage.load(dumped_data)

async def convert_media(data: UniMessage) -> str:
    """
    输入解析得到的元组，返回处理后的JSON数组，与 save_media() 保存下来的格式一致
    不保存任何媒体
    """
    uni_data = UniMessage(data)
    dumped_uni_data = uni_data.dump(json=True)
    loaded_data = json.loads(dumped_uni_data)
    for item in loaded_data:
        if "url" in item:
            # 构造文件路径，但不保存
            file_path = await download_media(item["url"], MEDIA_SAVE_DIR, json=True)
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

def get_source(target: MsgTarget) -> str:
    """
    获取消息来源
    """
    if target.private:
        return f"u{target.id}"
    return f"g{target.id}"

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

async def get_num_list(num_str: str) -> list[int]:
    """
    将类似 "1,2,5-7" 的字符串转换为整数列表 [1,2,5,6,7]
    """
    pattern = r"^(?:(?:\d+)|\d+-\d+)(?:,(?:(?:\d+)|\d+-\d+))*$"
    if not bool(re.fullmatch(pattern, num_str)):
        await pe.finish("参数格式错误")

    num_list = []
    parts = num_str.split(",")
    for part in parts:
        if "-" in part:
            start, end = part.split("-")
            if start >= end:
                await pe.finish("参数格式错误")
            num_list.extend(range(int(start), int(end) + 1))
        else:
            num_list.append(int(part))
    return num_list

async def _download_with_driver(
    media_url: str,
    driver: Driver,
    *,
    stream: bool,
    **kwargs: Any
) -> bytes:
    request = Request("GET", media_url)
    sess = driver.get_session(**kwargs) # pyright: ignore[reportAttributeAccessIssue] 不支持 HTTPClientMixin 的 Driver 不会被传入这个函数
    raw = b""
    if stream:
        async for chunk in sess.stream_request(request):
            raw += chunk.content
    else:
        response = await sess.request(request)
        raw = response.content

    return raw

async def _download_with_httpx(
    media_url: str,
    *,
    stream: bool,
    **kwargs: Any
) -> bytes:
    async with httpx.AsyncClient(**kwargs) as client:
        if stream:
            raw = b""
            async with client.stream("GET", media_url) as response:
                async for chunk in response.aiter_bytes():
                    raw += chunk
            return raw
        response = await client.get(media_url)
        return response.content

async def download_with_fallback(
    self: UniMessage,
    stream: bool = False,  # noqa: FBT001, FBT002
    **kwargs: Any
) -> UniMessage:
    """将消息中的媒体链接下载为文件数据

    Args:
        stream (bool, optional): 是否以流式下载. Defaults to False.
        **kwargs: 传递给下载器的参数
    """
    driver = get_driver()
    use_driver = isinstance(driver, HTTPClientMixin)

    for media in self.select(Media):
        if not media.url:
            continue

        if use_driver:
            raw = await _download_with_driver(media.url, driver, stream = stream, **kwargs)
        else:
            logger.debug("当前驱动器不支持 http 客户端，使用 httpx 下载")
            raw = await _download_with_httpx(media.url, stream = stream, **kwargs)

        media.url = None
        media.raw = raw

    return self


# 将方法绑定到 UniMessage
UniMessage.download = download_with_fallback

def save(
    self: Media,
    media_save_dir: str | Path | None = None
) -> Path:
    if not self.raw:
        raise ValueError
    dir_ = Path(media_save_dir) if isinstance(media_save_dir, (str, Path)) else MEDIA_SAVE_DIR
    raw = self.raw.getvalue() if isinstance(self.raw, BytesIO) else self.raw
    kind = filetype.guess(raw)
    if kind:
        ext = "." + kind.extension if kind else ".bin"
    else:
        logger.info("Media.save: Unknow Filetype")
        ext = ".bin"
    md5 = hashlib.md5(raw).hexdigest().upper()
    path = dir_ / f"{md5}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not media_save_dir:
        with path.open("wb+") as f:
            f.write(raw)
    return path.resolve()

Media.save = save
