import os
import json
import hashlib
import filetype
import tempfile
import httpx

from pathlib import Path
from nonebot import logger
from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot_plugin_alconna import UniMessage

media_save_dir = get_plugin_data_dir() / "media"

async def download_media(
        url: str,
        save_dir: Path,
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()

                    # 边下载边写入并计算 MD5
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            tmp_file.write(chunk)
                            md5_hash.update(chunk)

            tmp_file.flush()
            os.fsync(tmp_file.fileno())

        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            logger.info(f"下载或写入失败: {e}")
            return None

    # 识别扩展名（filetype 是同步库，但很快）
    try:
        kind = filetype.guess(str(tmp_path))
        extension = '.' + kind.extension if kind else '.bin'
    except Exception as e:
        logger.info(f"文件类型识别失败: {e}")
        extension = '.bin'

    # 生成最终路径
    md5_hex = md5_hash.hexdigest().upper()
    final_path = save_dir / (md5_hex + extension)

    if json:
        tmp_path.unlink(missing_ok=True)
        return final_path
    elif final_path.exists():
        logger.info(f"文件已存在，跳过: {final_path}")
        tmp_path.unlink(missing_ok=True)
        return final_path

    # 重命名
    try:
        tmp_path.rename(final_path)
        logger.info(f"保存成功: {final_path}")
        return final_path
    except Exception as e:
        logger.info(f"重命名失败: {e}")
        tmp_path.unlink(missing_ok=True)
        return None

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
        if 'url' in item:
            # 下载文件
            file_path = await download_media(item['url'], media_save_dir)
            item['id'] = file_path.name if file_path else item['id']
            # 标记为 media
            item['media'] = True
            # 删除url字段
            del item['url']

    dumped_data = json.dumps(loadded_data, ensure_ascii=False)
    return dumped_data

def load_media(data: str) -> UniMessage:
    """
    加载媒体文件
    输入存储的JSON数组字符串，返回包含媒体文件的UniMessage对象
    """

    media_save_dir = get_plugin_data_dir() / "media"

    loadded_data = json.loads(data)
    for item in loadded_data:
        if item.get('media'):
            item['path'] = str(media_save_dir / item['id'])
            del item['media']

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
        if 'url' in item:
            # 构造文件路径，但不保存
            file_path = await download_media(item['url'], media_save_dir, json=True)
            item['id'] = file_path.name if file_path else item['id']
            del item['url']
            item['media'] = True
    
    dumped_data = json.dumps(loaded_data, ensure_ascii=False)
    return dumped_data

def uni_message_to_dumpped_data(data: UniMessage) -> str:
    """
    将 UniMessage 转换为 JSON 数组字符串
    """
    dumped_uni_data = data.dump(json=True)
    loaded_data = json.loads(dumped_uni_data)
    for item in loaded_data:
        if 'url' in item:
            del item['url']
            item['media'] = True
    
    dumped_data = json.dumps(loaded_data, ensure_ascii=False)
    return dumped_data