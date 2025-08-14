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
    生成 enc 签名，按照最新的接口要求
    根据抓包数据，需要包含所有提交的参数
    """
    # 创建参数副本，移除空的 enc 字段
    params = {k: v for k, v in submit_info.items() if k != 'enc'}
    
    # 按照key的字母顺序排序
    sorted_items = sorted(params.items())
    
    # 拼接成 [key=value] 的格式
    needed = [f"[{key}={value}]" for key, value in sorted_items]
    
    # 加上固定的"盐"（可能需要根据最新抓包调整）
    pattern = "%sd`~7^/>N4!Q#){''"
    needed.append(f"[{pattern}]")
    
    seq = ''.join(needed)
    result = md5(seq.encode("utf-8")).hexdigest()
    return result

def generate_behavior_analysis():
    """
    生成更真实的 behaviorAnalysis（行为分析）数据
    根据抓包数据优化，使其更接近真实用户行为
    """
    timestamp = int(time.time() * 1000)
    
    # 1. 模拟鼠标移动轨迹 (moves)
    # 更自然的移动模式
    mouse_movements = []
    start_x, start_y = random.randint(200, 400), random.randint(300, 500)
    
    for i in range(random.randint(15, 35)):
        # 模拟更自然的鼠标移动
        if i == 0:
            move_x, move_y = start_x, start_y
        else:
            # 相对平滑的移动
            move_x = max(0, min(800, move_x + random.randint(-30, 30)))
            move_y = max(0, min(600, move_y + random.randint(-25, 25)))
        
        move_t = timestamp - random.randint(10000, 30000) + i * random.randint(50, 200)
        mouse_movements.append(f"{move_x},{move_y},{move_t}")
    
    # 2. 模拟鼠标点击 (clicks)
    clicks = []
    for i in range(random.randint(1, 4)):
        click_x = random.randint(150, 700)
        click_y = random.randint(200, 600)
        click_t = timestamp - random.randint(5000, 15000) + i * random.randint(500, 2000)
        clicks.append(f"{click_x},{click_y},{click_t}")

    # 3. 模拟页面聚焦 (focus)
    focus_start = timestamp - random.randint(20000, 60000)
    focus_end = timestamp - random.randint(1000, 5000)
    focus = f"{focus_start},{focus_end}"

    # 4. 模拟键盘事件 (keys) - 通常为空但保留结构
    keys = ""
    
    # 5. 模拟滚动事件 (scrolls) - 可以添加一些滚动
    scrolls = []
    for i in range(random.randint(0, 3)):
        scroll_t = timestamp - random.randint(8000, 20000) + i * random.randint(1000, 3000)
        scroll_delta = random.randint(-300, 300)
        scrolls.append(f"0,{scroll_delta},{scroll_t}")

    # 6. 拼接所有行为数据
    behavior_str = (
        f"moves={'|'.join(mouse_movements)}&"
        f"clicks={'|'.join(clicks)}&"
        f"scrolls={'|'.join(scrolls)}&"
        f"keys={keys}&"
        f"focus={focus}&"
        f"ts={timestamp}&"
        f"r={random.random():.16f}"  # 高精度随机数
    )
    
    # 7. 进行URL编码
    return urllib.parse.quote_plus(behavior_str)

def generate_captcha_token():
    """生成验证码相关的token"""
    return f"{random.randint(100000000000000000000000000000000, 999999999999999999999999999999999)}"

def generate_request_id():
    """生成请求ID"""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    return ''.join(random.choice(chars) for _ in range(32))
