from typing import Any

import httpx
from nonebot import get_driver, logger
from nonebot.internal.driver import Driver, HTTPClientMixin, Request
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_alconna.uniseg.segment import Media


class PeMessage(UniMessage):
    async def _download_with_driver(
        self,
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
        self,
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

    async def download(
        self,
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
                raw = await self._download_with_driver(media.url, driver, stream = stream, **kwargs)
            else:
                logger.debug("当前驱动器不支持 http 客户端，使用 httpx 下载")
                raw = await self._download_with_httpx(media.url, stream = stream, **kwargs)

            media.url = None
            media.raw = raw

        return self
