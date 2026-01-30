import httpx
import time
import json
from typing import Optional, Any, Dict
from . import Crypt

def get_sai_wen(url: str) -> Optional[str]:
    """
    :param url: 请求地址
    :return: 提取到的文本
    """
    
    # 1. 构造数据 payload
    data = {
        "competitionType": 0,
        "snumflag": "1",
        "from": "web",
        "timestamp": int(time.time()), 
        "version": "v2.1.5",
        "subversions": 17108,
    }

    # 2. 执行加密
    # 假设 Crypt.encrypt 是同步函数
    cipher = Crypt.encrypt(data)

    # 3. 构造 POST 请求体
    payload = {
        0: cipher[1:]  # 去掉加密字符串的第一个字符
    }

    try:
        # 使用 httpx 同步客户端发送请求
        with httpx.Client(timeout=20.0) as client:
            # 发送 POST 请求
            response = client.post(url, json=payload)
            
        # 解析响应 JSON
        res_data = response.json()
        msg = res_data.get("msg")

        selected_text = ""

        # 4. 处理响应逻辑 (对应 JS 的 if/else 逻辑)
        if isinstance(msg, str):
            selected_text = msg
        elif isinstance(msg, dict):
            if "content" in msg:
                selected_text = msg["content"]
            elif "0" in msg:  # JS 中 msg["0"] 指的是 key 为字符串 "0"
                selected_text = msg["0"]
        else:
            # 如果是其他情况（比如是数字或列表），尝试原样转换或置空
            selected_text = str(msg) if msg else ""

        return selected_text

    except Exception as e:
        print(f"请求发生错误: {e}")
        return None

