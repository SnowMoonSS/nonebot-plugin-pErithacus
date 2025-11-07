import os
import requests
import json

from nonebot_plugin_localstore import get_plugin_data_dir
from nonebot_plugin_alconna import UniMessage

async def save_media(data: UniMessage) -> str:
    """
    保存媒体文件
    输入解析得到的元组，返回处理后的JSON数组
    """

    media_save_dir = get_plugin_data_dir() / "media"
    media_save_dir.mkdir(parents=True, exist_ok=True)

    # 将解析得到的元组转换成UniMessage对象
    uni_data = UniMessage(data)
    # 使用UniMessage.dump()方法将UniMessage对象转换成JSON数组
    dumped_uni_data = uni_data.dump(json=True)
    
    # 处理JSON数组，下载媒体文件并保存
    loadded_data = json.loads(dumped_uni_data)
    for item in loadded_data:
        if 'url' in item:
            # 下载文件
            response = requests.get(item['url'])
            if response.status_code == 200:
                file_name = os.path.splitext(item['id'])[0]
                file_path = os.path.join(media_save_dir, file_name)
                # 如果文件不存在则保存文件
                if not os.path.exists(file_path):
                    with open(file_path, 'wb') as file:
                        file.write(response.content)
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
            item['path'] = str(media_save_dir / os.path.splitext(item['id'])[0])
            del item['media']

    dumped_data = json.dumps(loadded_data, ensure_ascii=False)
    return UniMessage.load(dumped_data)

def convert_media(data: UniMessage) -> str:
    """
    将收到的 UniMessage 转换为 JSON 数组，与 save_media 保存下来的格式一致
    """
    uni_data = UniMessage(data)
    dumped_uni_data = uni_data.dump(json=True)
    loaded_data = json.loads(dumped_uni_data)
    for item in loaded_data:
        if 'url' in item:
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