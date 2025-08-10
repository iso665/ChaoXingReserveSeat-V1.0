from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
from hashlib import md5
import random
from uuid import uuid1
import time

def AES_Encrypt(data):
    key = b"u2oh6Vu^HWe4_AES"  # Convert to bytes
    iv = b"u2oh6Vu^HWe4_AES"  # Convert to bytes
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data.encode('utf-8')) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    enctext = base64.b64encode(encrypted_data).decode('utf-8')
    return enctext
    
def resort(submit_info):
    return {key: submit_info[key] for key in sorted(submit_info.keys())}

def enc(submit_info):
    add = lambda x, y: x + y
    processed_info = resort(submit_info)
    needed = [add(add('[', key), '=' + str(value)) + ']' for key, value in processed_info.items()]
    pattern = "%sd`~7^/>N4!Q#){''"
    needed.append(add('[', pattern) + ']')
    seq = ''.join(needed)
    return md5(seq.encode("utf-8")).hexdigest()

def generate_captcha_key(timestamp: int):
    captcha_key = md5((str(timestamp) + str(uuid1())).encode("utf-8")).hexdigest()
    encoded_timestamp = md5(
        (str(timestamp) + "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1" + "slide" + captcha_key).encode("utf-8")
    ).hexdigest() + ":" + str(int(timestamp) + 0x493e0)
    return [captcha_key, encoded_timestamp]

def generate_behavior_analysis():
    """生成行为分析数据 - 基于真实抓包数据的结构"""
    import urllib.parse
    
    # 模拟真实的行为分析数据结构
    timestamp = int(time.time() * 1000)
    
    # 生成鼠标移动轨迹
    mouse_movements = []
    for i in range(random.randint(15, 30)):
        x = random.randint(100, 1200)
        y = random.randint(100, 800)
        t = timestamp + i * random.randint(50, 200)
        mouse_movements.append(f"{x},{y},{t}")
    
    # 生成点击事件
    clicks = []
    for i in range(random.randint(3, 8)):
        x = random.randint(200, 800)
        y = random.randint(200, 600)
        t = timestamp + random.randint(1000, 5000)
        clicks.append(f"{x},{y},{t}")
    
    # 生成滚动事件
    scrolls = []
    for i in range(random.randint(1, 5)):
        delta = random.randint(-300, 300)
        t = timestamp + random.randint(500, 3000)
        scrolls.append(f"{delta},{t}")
    
    # 构建行为数据字符串（模拟真实格式）
    behavior_data = {
        "moves": "|".join(mouse_movements),
        "clicks": "|".join(clicks),
        "scrolls": "|".join(scrolls),
        "keys": "",  # 键盘输入通常为空
        "focus": f"{timestamp},{timestamp + random.randint(10000, 30000)}",
        "timestamp": timestamp,
        "random": random.randint(100000, 999999)
    }
    
    # 转换为类似抓包数据的格式
    behavior_str = f"moves={behavior_data['moves']}&clicks={behavior_data['clicks']}&scrolls={behavior_data['scrolls']}&keys={behavior_data['keys']}&focus={behavior_data['focus']}&ts={behavior_data['timestamp']}&r={behavior_data['random']}"
    
    # URL编码
    encoded_behavior = urllib.parse.quote_plus(behavior_str)
    
    return encoded_behavior
