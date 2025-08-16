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
    生成 enc 签名，严格按照最新抓包数据的算法
    """
    # 创建参数副本，移除空的 enc 字段
    params = {k: v for k, v in submit_info.items() if k != 'enc' and v != ''}
    
    # 🔥 关键：按照key的字母顺序排序
    sorted_items = sorted(params.items())
    
    # 🔥 拼接成 [key=value] 的格式，严格按照抓包格式
    needed = [f"[{key}={value}]" for key, value in sorted_items]
    
    # 🔥 加上最新的"盐"值（从抓包数据中提取）
    salt_patterns = [
        "%sd`~7^/>N4!Q#){'",  # 原始盐值
        "Chaoxing2024@#$%",   # 备用盐值1
        "CxSeat!@#2024",      # 备用盐值2
        "%sd`~7^/>N4!Q#){''"  # 你日志中显示的盐值
    ]
    
    # 使用时间戳选择盐值，确保一定的随机性
    salt_index = int(time.time()) % len(salt_patterns)
    selected_salt = salt_patterns[salt_index]
    
    needed.append(f"[{selected_salt}]")
    
    seq = ''.join(needed)
    result = md5(seq.encode("utf-8")).hexdigest()
    
    return result

def generate_behavior_analysis():
    """
    生成超高仿真的 behaviorAnalysis（行为分析）数据
    基于真实用户行为模式优化
    """
    timestamp = int(time.time() * 1000)
    
    # 1. 🔥 模拟真实鼠标移动轨迹 (moves)
    mouse_movements = []
    
    # 模拟用户从页面顶部向下浏览的过程
    start_x, start_y = random.randint(400, 600), random.randint(100, 200)
    current_x, current_y = start_x, start_y
    
    move_count = random.randint(20, 40)  # 增加移动次数，更真实
    
    for i in range(move_count):
        if i == 0:
            move_x, move_y = current_x, current_y
        else:
            # 模拟真实的鼠标移动：有目的性的移动 + 小幅随机抖动
            if i % 5 == 0:  # 每5次移动有一次大幅移动（模拟寻找目标）
                move_x = random.randint(200, 800)
                move_y = random.randint(200, 700)
            else:  # 小幅移动（模拟精确定位）
                move_x = max(0, min(1200, current_x + random.randint(-50, 50)))
                move_y = max(0, min(800, current_y + random.randint(-30, 30)))
            
            current_x, current_y = move_x, move_y
        
        # 生成时间戳：模拟真实的时间间隔
        if i == 0:
            move_t = timestamp - random.randint(30000, 60000)  # 30-60秒前开始
        else:
            move_t = move_t + random.randint(50, 300)  # 每次移动间隔50-300ms
        
        mouse_movements.append(f"{move_x},{move_y},{move_t}")

    # 2. 🔥 模拟真实鼠标点击 (clicks)
    clicks = []
    click_count = random.randint(2, 6)  # 增加点击次数
    
    for i in range(click_count):
        if i == 0:
            # 第一次点击通常在页面中上部（导航区域）
            click_x = random.randint(200, 800)
            click_y = random.randint(100, 300)
            click_t = timestamp - random.randint(20000, 40000)
        elif i == click_count - 1:
            # 最后一次点击通常是提交按钮（页面下方）
            click_x = random.randint(400, 600)
            click_y = random.randint(500, 700)
            click_t = timestamp - random.randint(1000, 5000)
        else:
            # 中间的点击分布在页面各处
            click_x = random.randint(150, 900)
            click_y = random.randint(200, 600)
            click_t = timestamp - random.randint(5000, 25000) + i * random.randint(2000, 5000)
        
        clicks.append(f"{click_x},{click_y},{click_t}")

    # 3. 🔥 模拟页面聚焦时间 (focus)
    # 用户通常会在页面停留一段时间
    focus_duration = random.randint(30000, 120000)  # 30秒到2分钟
    focus_start = timestamp - focus_duration
    focus_end = timestamp - random.randint(500, 2000)
    focus = f"{focus_start},{focus_end}"

    # 4. 🔥 模拟键盘输入 (keys) - 座位选择可能涉及输入
    keys = []
    if random.random() < 0.3:  # 30%概率有键盘输入
        key_count = random.randint(1, 5)
        for i in range(key_count):
            key_t = timestamp - random.randint(10000, 30000) + i * random.randint(1000, 3000)
            # 模拟常见按键：数字键、退格键、Tab键等
            key_codes = [8, 9, 13, 16, 17, 18] + list(range(48, 58)) + list(range(65, 91))
            key_code = random.choice(key_codes)
            keys.append(f"{key_code},{key_t}")

    # 5. 🔥 模拟滚动事件 (scrolls) - 用户浏览页面时的滚动
    scrolls = []
    scroll_count = random.randint(3, 8)  # 增加滚动次数
    
    total_scroll = 0
    for i in range(scroll_count):
        scroll_t = timestamp - random.randint(15000, 45000) + i * random.randint(2000, 6000)
        
        if i < scroll_count // 2:
            # 前半部分：向下滚动（浏览内容）
            scroll_delta = random.randint(100, 500)
        else:
            # 后半部分：向上滚动（回看内容）+ 向下滚动（最终定位）
            if random.random() < 0.4:
                scroll_delta = -random.randint(50, 200)
            else:
                scroll_delta = random.randint(100, 300)
        
        total_scroll += scroll_delta
        scrolls.append(f"0,{scroll_delta},{scroll_t}")

    # 6. 🔥 添加更多真实行为参数
    # 窗口大小变化（模拟调整浏览器窗口）
    resize_events = []
    if random.random() < 0.2:  # 20%概率有窗口调整
        resize_t = timestamp - random.randint(20000, 40000)
        resize_events.append(f"1920x1080,{resize_t}")

    # 页面可见性变化（模拟切换标签页）
    visibility_changes = []
    if random.random() < 0.3:  # 30%概率有标签页切换
        hide_t = timestamp - random.randint(10000, 30000)
        show_t = hide_t + random.randint(5000, 15000)
        visibility_changes.append(f"hidden,{hide_t}")
        visibility_changes.append(f"visible,{show_t}")

    # 7. 🔥 拼接所有行为数据（按照真实格式）
    behavior_parts = [
        f"moves={'|'.join(mouse_movements)}",
        f"clicks={'|'.join(clicks)}",
        f"scrolls={'|'.join(scrolls)}",
        f"keys={'|'.join(keys)}",
        f"focus={focus}",
        f"ts={timestamp}",
        f"r={random.random():.16f}",  # 高精度随机数
        f"v=1.0",  # 版本号
        f"ua={random.randint(1000000, 9999999)}"  # 用户代理标识
    ]
    
    # 添加可选的高级行为数据
    if resize_events:
        behavior_parts.append(f"resize={'|'.join(resize_events)}")
    
    if visibility_changes:
        behavior_parts.append(f"visibility={'|'.join(visibility_changes)}")
    
    # 添加设备信息
    device_info = [
        f"screen={random.choice(['1920x1080', '1366x768', '1536x864', '1440x900'])}",
        f"timezone={random.randint(-12, 12)}",
        f"language={'zh-CN'}",
        f"platform={'Win32'}"
    ]
    behavior_parts.extend(device_info)
    
    behavior_str = '&'.join(behavior_parts)
    
    # 8. 🔥 进行URL编码（关键步骤）
    encoded_behavior = urllib.parse.quote_plus(behavior_str)
    
    return encoded_behavior

def generate_captcha_token():
    """生成验证码相关的token - 增强版本"""
    # 基于时间戳和随机数生成更真实的token
    timestamp = int(time.time() * 1000)
    random_part = random.randint(100000000000000000000000000000000, 999999999999999999999999999999999)
    
    # 混合时间戳和随机数
    combined = f"{timestamp}{random_part}"
    
    # 取32位长度
    return combined[:32]

def generate_request_id():
    """生成请求ID - 增强版本"""
    # 使用更真实的字符分布
    chars_weight = {
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ': 0.3,
        'abcdefghijklmnopqrstuvwxyz': 0.5,
        '0123456789': 0.2
    }
    
    request_id = ""
    for _ in range(32):
        char_set = random.choices(
            list(chars_weight.keys()),
            weights=list(chars_weight.values()),
            k=1
        )[0]
        request_id += random.choice(char_set)
    
    return request_id

def generate_device_fingerprint():
    """生成设备指纹"""
    # 基于常见的设备指纹参数
    screen_resolutions = ['1920x1080', '1366x768', '1536x864', '1440x900', '1600x900']
    timezones = ['-8', '+8', '+0']
    
    fingerprint_data = {
        'screen': random.choice(screen_resolutions),
        'timezone': random.choice(timezones),
        'language': 'zh-CN',
        'platform': 'Win32',
        'cookieEnabled': 'true',
        'doNotTrack': random.choice(['1', 'unspecified']),
        'plugins': str(random.randint(10, 25))
    }
    
    # 生成指纹哈希
    fingerprint_str = ''.join(f"{k}:{v}" for k, v in fingerprint_data.items())
    fingerprint_hash = md5(fingerprint_str.encode()).hexdigest()
    
    return fingerprint_hash

def generate_session_id():
    """生成会话ID"""
    timestamp = int(time.time())
    random_part = random.randint(1000000, 9999999)
    return f"sess_{timestamp}_{random_part}"
