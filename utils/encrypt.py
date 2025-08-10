from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
from hashlib import md5
import random
import time
import urllib.parse

def AES_Encrypt(data):
    """AES加密函数，用于加密用户名和密码"""
    key = b"u2oh6Vu^HWe4_AES"
    iv = b"u2oh6Vu^HWe4_AES"
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data.encode('utf-8')) + padder.finalize()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    enctext = base64.b64encode(encrypted_data).decode('utf-8')
    return enctext
    
def enc(submit_info):
    """
    生成 enc 签名。
    这是适配最新接口的关键，它必须包含所有提交的参数。
    """
    # 按照key的字母顺序排序
    sorted_items = sorted(submit_info.items())
    
    # 拼接成 [key=value] 的格式
    needed = [f"[{key}={value}]" for key, value in sorted_items]
    
    # 加上固定的“盐”
    pattern = "%sd`~7^/>N4!Q#){''"
    needed.append(f"[{pattern}]")
    
    seq = ''.join(needed)
    return md5(seq.encode("utf-8")).hexdigest()

def generate_behavior_analysis():
    """
    模拟生成 behaviorAnalysis（行为分析）数据。
    这是为了绕过服务器对机器人操作的检测。
    我们模拟了鼠标移动、点击和页面聚焦等行为。
    """
    timestamp = int(time.time() * 1000)
    
    # 1. 模拟鼠标移动轨迹 (moves)
    # 格式: x坐标,y坐标,时间戳
    mouse_movements = []
    start_x, start_y = random.randint(300, 500), random.randint(400, 600)
    for i in range(random.randint(20, 40)):
        move_x = start_x + random.randint(-20, 20)
        move_y = start_y + random.randint(-15, 15)
        move_t = timestamp + i * random.randint(30, 100)
        mouse_movements.append(f"{move_x},{move_y},{move_t}")
    
    # 2. 模拟鼠标点击 (clicks)
    # 格式: x坐标,y坐标,时间戳
    clicks = []
    for i in range(random.randint(2, 5)):
        click_x = random.randint(200, 800)
        click_y = random.randint(200, 700)
        click_t = timestamp + random.randint(1000, 8000)
        clicks.append(f"{click_x},{click_y},{click_t}")

    # 3. 模拟页面聚焦 (focus)
    # 格式: 获得焦点时间戳,失去焦点时间戳
    focus_start = timestamp - random.randint(10000, 20000)
    focus_end = timestamp
    focus = f"{focus_start},{focus_end}"

    # 4. 拼接所有行为数据
    # 格式: a=...&b=...&c=...
    behavior_str = (
        f"moves={'|'.join(mouse_movements)}&"
        f"clicks={'|'.join(clicks)}&"
        f"scrolls=&keys=&" # 滚动和键盘通常可以为空
        f"focus={focus}&"
        f"ts={timestamp}&"
        f"r={random.random()}" # 一个随机数
    )
    
    # 5. 进行URL编码，这是必须的步骤
    return urllib.parse.quote_plus(behavior_str)
