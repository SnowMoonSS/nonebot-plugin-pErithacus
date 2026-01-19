from __future__ import annotations

from json import dumps
from typing import TYPE_CHECKING, Any, Self

import httpx
from nonebot import get_driver, logger
from nonebot.internal.driver import HTTPClientMixin, Request
from nonebot_plugin_alconna.uniseg.message import UniMessage
from nonebot_plugin_alconna.uniseg.segment import (
    Media,
)

if TYPE_CHECKING:
    from pathlib import Path


class PeMessage(UniMessage):

    def dump( # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        *,
        media_save_dir: str | Path | bool | None = None,
        json: bool = False,
        unsave: bool = False
    ) -> str | list[dict[str, Any]]:
        """将消息序列化为 JSON 格式

        注意：
            若 media_save_dir 为 False，则不会保存媒体文件。
            若 media_save_dir 为 True，则会将文件数据转为 base64 编码。
            若不指定 media_save_dir，
                则会尝试导入 `nonebot_plugin_localstore` 并使用其提供的路径。
            否则，将会尝试使用当前工作目录。

        Args:
            media_save_dir (Union[str, Path， bool, None], optional):
                媒体文件保存路径. Defaults to None.
            json (bool, optional): 是否返回 JSON 字符串. Defaults to False.

        Returns:
            Union[str, list[dict]]: 序列化后的消息
        """
        result = [seg.dump(media_save_dir=media_save_dir,unsave = unsave) for seg in self]
        return dumps(result, ensure_ascii=False) if json else result

    async def download(self, stream: bool = False, **kwargs: Any) -> Self:  # noqa: FBT001, FBT002
        """将消息中的媒体链接下载为文件数据

        Args:
            stream (bool, optional): 是否以流式下载. Defaults to False.
            **kwargs: 传递给下载器的参数
        """
        driver = get_driver()

        for media in self.select(Media):
            if not media.url:
                continue

            raw = b""

            # 尝试使用 NoneBot 的 driver（优先）
            if isinstance(driver, HTTPClientMixin):
                try:
                    request = Request("GET", media.url)
                    sess = driver.get_session(**kwargs)
                    if stream:
                        async for chunk in sess.stream_request(request):
                            raw += chunk.content # pyright: ignore[reportOperatorIssue]
                    else:
                        response = await sess.request(request)
                        raw = response.content
                except httpx.HTTPError as e:
                    # 包括连接错误、超时、4xx/5xx 等
                    logger.error(f"HTTP 请求失败: {e}")
                    return self
            else:
                # fallback：使用 httpx 作为备用客户端
                # 注意：**不传递 kwargs 给 httpx**（因原函数 kwargs 是给 driver 用的）
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        if stream:
                            async with client.stream("GET", media.url) as resp:
                                resp.raise_for_status()
                                async for chunk in resp.aiter_bytes(chunk_size=8192):
                                    raw += chunk
                        else:
                            resp = await client.get(media.url)
                            resp.raise_for_status()
                            raw = resp.content
                except httpx.HTTPError as e:
                    # 包括连接错误、超时、4xx/5xx 等
                    logger.error(f"HTTP 请求失败: {e}")
                    return self

            # 严格保持原逻辑：清除 url，设置 raw
            media.url = None
            media.raw = raw # pyright: ignore[reportAttributeAccessIssue]

        return self
