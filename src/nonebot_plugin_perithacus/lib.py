import base64
import hashlib
import json
import os
import re
import tempfile
from dataclasses import fields
from io import BytesIO
from json import dumps
from pathlib import Path
from typing import Any, Literal, overload

import filetype
import httpx
from apscheduler.triggers.cron import CronTrigger
from nonebot import get_driver, logger
from nonebot.internal.driver import HTTPClientMixin, Request
from nonebot_plugin_alconna import Match, MsgTarget, UniMessage
from nonebot_plugin_alconna.uniseg.segment import Media, Segment
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
    dumped_uni_data = uni_data.dump(media_save_dir=False, json=True)
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

async def pe_download(
    self: UniMessage,
    *,
    stream: bool = False,
    **kwargs: Any
) -> UniMessage:
    """将消息中的媒体链接下载为文件数据

    Args:
        stream (bool, optional): 是否以流式下载. Defaults to False.
        **kwargs: 传递给下载器的参数
    """
    logger.debug("开始下载媒体数据")
    driver = get_driver()
    use_driver = isinstance(driver, HTTPClientMixin)
    for media in self.select(Media):
        if not media.url:
            continue
        raw: bytes = b""
        if use_driver:
            request = Request("GET", media.url)
            sess = driver.get_session(**kwargs)
            if stream:
                async for chunk in sess.stream_request(request):
                    raw += chunk.content # pyright: ignore[reportOperatorIssue]
            else:
                response = await sess.request(request)
                raw = response.content # pyright: ignore[reportAssignmentType]
        else:
            logger.debug("当前驱动器不支持 http 客户端，使用 httpx 下载")
            async with httpx.AsyncClient(**kwargs) as client:
                if stream:
                    raw = b""
                    async with client.stream("GET", media.url) as response:
                        async for chunk in response.aiter_bytes():
                            raw += chunk
                else:
                    response = await client.get(media.url)
                    raw = response.content
        media.url = None
        media.raw = raw

        md5 = hashlib.md5(media.raw).hexdigest().upper()
        kind = filetype.guess(media.raw)
        ext = kind.extension if kind else "bin"
        media.id = f"{md5}.{ext}"
    return self

@overload
def pe_uni_dump(
    self: UniMessage,
    *,
    media_save_dir: str | Path | bool | None = None,
    json: Literal[False] = False
) -> list[dict[str, Any]]: ...

@overload
def pe_uni_dump(
    self: UniMessage,
    *,
    media_save_dir: str | Path | bool | None = None,
    json: Literal[True]
) -> str: ...

def pe_uni_dump(
    self: UniMessage,
    *,
    media_save_dir: str | Path | bool | None = None,
    json: bool = False
) -> str | list[dict[str, Any]]:
    """将消息序列化为 JSON 格式

    注意：
        若 media_save_dir 为 False，则不会保存媒体文件。
        若 media_save_dir 为 True，则会将文件数据转为 base64 编码。
        若不指定 media_save_dir，则会尝试导入 `nonebot_plugin_localstore` 并使用其提供的路径。
        否则，将会尝试使用当前工作目录。

    Args:
        media_save_dir (Union[str, Path， bool, None], optional): 媒体文件保存路径. Defaults to None.
        json (bool, optional): 是否返回 JSON 字符串. Defaults to False.

    Returns:
        Union[str, list[dict]]: 序列化后的消息
    """
    result = [pe_seg_dump(seg, media_save_dir=media_save_dir) for seg in self]
    return dumps(result, ensure_ascii=False) if json else result

def pe_seg_dump(
    self: Segment,
    *,
    media_save_dir: str | Path | bool | None = None,
) -> dict:
    """将对象转为 dict 数据
    注意：
        若 media_save_dir 为 False，则不会保存媒体文件。
        若 media_save_dir 为 True，则会将文件数据转为 base64 编码。
        若不指定 media_save_dir，则会尝试导入 `nonebot_plugin_localstore` 并使用其提供的路径。
        否则，将会尝试使用当前工作目录。
    """
    # 如果不是 Media 及其子类，直接委托给原版 .dump()
    if not isinstance(self, Media):
        # 原版 dump 方法通常支持 **kwargs，传入 media_save_dir 是安全的
        return self.dump(media_save_dir=media_save_dir)
    data = {f.name: getattr(self, f.name) for f in fields(self) if f.name not in ("origin", "_children")}
    data = {"type": self.type, **{k: v for k, v in data.items() if v is not None}}
    if isinstance(self, Media):
        if self.name == self.__default_name__:
            data.pop("name", None)
        if self.url or self.path or not self.raw:
            data.pop("raw", None)
            data.pop("mimetype", None)
        elif media_save_dir is True:
            data["raw"] = base64.b64encode(self.raw_bytes).decode()
        elif media_save_dir is not False:
            pe_save(self, media_save_dir=media_save_dir)
            data.pop("raw", None)
            data.pop("mimetype", None)
        elif media_save_dir is False:
            data.pop("raw", None)
            data.pop("mimetype", None)
    if self._children:
        data["children"] = [pe_seg_dump(child, media_save_dir=media_save_dir) for child in self._children]
    return data

def pe_save(
    self: Media,
    *,
    media_save_dir: str | Path | bool | None = None
) -> Path:
    if not self.raw:
        raise ValueError
    dir_ = Path(media_save_dir) if isinstance(media_save_dir, (str, Path)) else MEDIA_SAVE_DIR
    raw = self.raw.getvalue() if isinstance(self.raw, BytesIO) else self.raw
    path = dir_ / f"{self.id}"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb+") as f:
        f.write(raw)
    return path.resolve()

async def dump_msg(
    msg: UniMessage,
    *,
    media_save_dir: str | Path | bool | None = MEDIA_SAVE_DIR
) -> str:
    """
    将消息序列化为 JSON 格式
    注意：
        若 media_save_dir 为 False，则不会保存媒体文件。
        若 media_save_dir 为 True，则会将文件数据转为 base64 编码。
        若不指定 media_save_dir，则会保存到 MEDIA_SAVE_DIR。

    :param msg: 消息
    :type msg: UniMessage
    :param media_save_dir: 媒体文件保存路径
    :type media_save_dir: str | Path | bool | None
    :return: 序列化的消息
    :rtype: str
    """

    if isinstance(msg, tuple):
        msg = UniMessage(msg)

    msg = await pe_download(msg)
    return pe_uni_dump(msg, media_save_dir=media_save_dir, json=True)

def load_msg(msg: str) -> UniMessage:
    """
    将 JSON 格式的消息转为消息对象

    :param msg: JSON 格式的消息
    :type msg: str
    :return: 消息对象
    :rtype: UniMessage
    """
    uni_message = UniMessage.load(msg)
    for seg in uni_message:
        _process_segment_recursive(seg)
    return uni_message

def _process_segment_recursive(seg: Segment):
    """递归处理单个段落"""
    if isinstance(seg, Media):
        seg.path = str(MEDIA_SAVE_DIR / seg.id) if seg.path is None and seg.id is not None else seg.path

    # 递归处理子元素
    if seg._children:
        for child in seg._children:
            _process_segment_recursive(child)
