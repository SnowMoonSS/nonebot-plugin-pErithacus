import os
import requests
import json

from nonebot import logger
from nonebot_plugin_localstore import get_plugin_data_dir

def save_media(data: str) -> str:
    media_save_dir = get_plugin_data_dir() / "media"

    loadded_data = json.loads(data)
    for item in loadded_data:
        if 'url' in item:
            try:
                # 下载文件
                response = requests.get(item['url'])
                if response.status_code == 200:
                    file_name = os.path.splitext(item['id'])[0]
                    file_path = os.path.join(media_save_dir, file_name)
                    # 如果文件已存在则跳过处理
                    if not os.path.exists(file_path):
                        # 保存文件
                        with open(file_path, 'wb') as file:
                            file.write(response.content)
                    # 添加 path 字段
                    item['path'] = str(file_path)
                    # 删除url字段
                    del item['url']
            except Exception as e:
                logger.info(f"Error downloading file: {e}")
    dumped_data = json.dumps(loadded_data, ensure_ascii=False)

    return dumped_data
