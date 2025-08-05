from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import base64
from hashlib import md5
import random
from uuid import uuid1
import hashlib
import logging


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
    """旧版本的加密函数，作为备用"""
    add = lambda x, y: x + y
    processed_info = resort(submit_info)
    needed = [add(add('[', key), '=' + str(value)) + ']' for key, value in processed_info.items()]
    pattern = "%sd`~7^/>N4!Q#{'"
    needed.append(add('[', pattern) + ']')
    seq = ''.join(needed)
    return md5(seq.encode("utf-8")).hexdigest()


def generate_captcha_key(timestamp: int):
    captcha_key = md5((str(timestamp) + str(uuid1())).encode("utf-8")).hexdigest()
    encoded_timestamp = md5(
        (str(timestamp) + "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1" + "slide" + captcha_key).encode("utf-8")
    ).hexdigest() + ":" + str(int(timestamp) + 0x493e0)
    return [captcha_key, encoded_timestamp]


def sort_dict_by_keys(dictionary):
    """将字典按键排序并返回新字典"""
    sorted_keys = sorted(dictionary.keys())
    sorted_dict = {key: dictionary[key] for key in sorted_keys}
    return sorted_dict


def verify_param(params, algorithm_value):
    """
    生成参数的MD5验证哈希值 - 新版加密算法
    
    参数:
        params: 要验证的参数字典
        algorithm_value: 对应JavaScript中id为'algorithm'的元素值
    
    返回:
        计算得到的MD5哈希字符串
    """
    try:
        # 确保所有参数值都是字符串类型
        string_params = {}
        for key, value in params.items():
            if value is None:
                string_params[key] = ""
            else:
                string_params[key] = str(value)
        
        # 对参数字典按键排序
        sorted_params = sort_dict_by_keys(string_params)
        
        # 构建哈希字符串列表
        hash_list = []
        
        # 遍历排序后的参数，构建格式为 [key=value] 的字符串
        for key, value in sorted_params.items():
            hash_list.append(f"[{key}={value}]")
        
        # 添加algorithm值
        if algorithm_value:
            hash_list.append(f"[{algorithm_value}]")
        else:
            # 使用默认算法值
            hash_list.append("[%sd`~7^/>N4!Q#{']")
        
        # 连接所有元素形成最终字符串
        hash_string = "".join(hash_list)
        
        logging.debug(f"用于enc的哈希字符串: {hash_string}")
        
        # 计算MD5哈希值
        md5_hash = hashlib.md5(hash_string.encode("utf-8")).hexdigest()
        
        logging.debug(f"生成的MD5哈希: {md5_hash}")
        
        return md5_hash
        
    except Exception as e:
        logging.error(f"verify_param错误: {str(e)}")
        # 如果新算法失败，尝试使用旧算法
        logging.warning("回退到旧的enc算法")
        return enc(params)


def verify_param_v2(params, algorithm_value):
    """
    备用加密算法 - 尝试不同的参数组合
    """
    try:
        # 尝试另一种参数顺序和格式
        required_keys = ["roomId", "startTime", "endTime", "day", "seatNum", "captcha", "token"]
        
        # 确保包含所有必需的键
        filtered_params = {}
        for key in required_keys:
            if key in params:
                filtered_params[key] = str(params[key]) if params[key] is not None else ""
        
        # 按照特定顺序排序
        sorted_params = {key: filtered_params[key] for key in sorted(filtered_params.keys())}
        
        # 构建哈希字符串
        hash_parts = []
        for key, value in sorted_params.items():
            hash_parts.append(f"[{key}={value}]")
        
        # 添加算法值
        if algorithm_value:
            hash_parts.append(f"[{algorithm_value}]")
        
        hash_string = "".join(hash_parts)
        
        logging.debug(f"V2哈希字符串: {hash_string}")
        
        return hashlib.md5(hash_string.encode("utf-8")).hexdigest()
        
    except Exception as
