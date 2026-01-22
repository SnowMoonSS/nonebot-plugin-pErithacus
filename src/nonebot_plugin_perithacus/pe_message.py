from typing import Any

import httpx
from nonebot import get_driver, logger
from nonebot.internal.driver import HTTPClientMixin, Request
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_alconna.uniseg.segment import Media


class PeMessage(UniMessage):

    async def download(
        self,
        stream: bool = False,  # noqa: FBT001, FBT002
        **kwargs: Any
    ) -> PeMessage:
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
        return self
