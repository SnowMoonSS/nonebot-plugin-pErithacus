from __future__ import annotations

import base64
import hashlib
from dataclasses import fields
from io import BytesIO
from pathlib import Path

from nonebot import require
from nonebot_plugin_alconna.uniseg.segment import (
    Media,
    Segment,
)
from nonebot_plugin_alconna.uniseg.utils import fleep

from .pe_message import PeMessage


class PeSegment(Segment):
    """
    Segment 类，用于处理消息段
    """

    def dump(
        self,
        *,
        media_save_dir: str | Path | bool | None = None,
        unsave: bool = False
    ) -> dict:
        """将对象转为 dict 数据
        注意：
            若 media_save_dir 为 False，则不会保存媒体文件。
            若 media_save_dir 为 True，则会将文件数据转为 base64 编码。
            若不指定 media_save_dir，则会尝试导入 `nonebot_plugin_localstore` 并使用其提供的路径。
            否则，将会尝试使用当前工作目录。
        """
        data = {
            f.name: getattr(self, f.name) for f in fields(self)
            if f.name not in ("origin", "_children")
        }
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
                path = self.save(media_save_dir=media_save_dir, unsave=unsave)
                data.pop("raw", None)
                data.pop("mimetype", None)
                data["path"] = str(path.resolve().as_posix())
        if self._children:
            data["children"] = [
                child.dump(media_save_dir=media_save_dir, unsave = unsave) for child in self._children
            ]
        return data

    def save(
        self,
        media_save_dir: str | Path | None = None,
        *,
        unsave: bool = False
    ) -> Path:
        if not isinstance(self, Media):
            raise TypeError
        if not self.raw:
            raise ValueError
        if isinstance(media_save_dir, (str, Path)):
            dir_ = Path(media_save_dir)
        else:
            try:
                require("nonebot_plugin_localstore")
                from nonebot_plugin_localstore import get_data_dir

                dir_ = get_data_dir("nonebot_plugin_alconna") / "media"
            except ImportError:
                get_data_dir = None
                dir_ = Path.cwd() / ".data" / "media"
        raw = self.raw.getvalue() if isinstance(self.raw, BytesIO) else self.raw
        header = raw[:128]
        info = fleep.get(header)
        ext = info.extensions[0] if info.extensions else "bin"
        md5 = hashlib.md5(raw).hexdigest()
        path = dir_ / md5[:2] / f"{md5}.{ext}"

        # 如果 unsave 为 True，只返回路径而不实际保存文件
        if unsave:
            return path.resolve()

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb+") as f:
            f.write(raw)
        return path.resolve()
