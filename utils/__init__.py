import os
import logging

# 统一导出，方便其他文件调用
# 注意：这里已经删除了对 generate_captcha_key 的导入
from .encrypt import AES_Encrypt, enc, generate_behavior_analysis
from .reserve import reserve

def get_user_credentials(action):
    """从环境变量获取用户凭证"""
    if not action:
        return "", ""
    try:
        usernames = os.environ['USERNAMES']
        passwords = os.environ['PASSWORDS']
        if not usernames or not passwords:
            logging.error("环境变量 USERNAMES 或 PASSWORDS 为空。")
            return "", ""
        return usernames, passwords
    except KeyError:
        logging.error("在 Actions Secrets 中未找到 USERNAMES 或 PASSWORDS。")
        return "", ""
