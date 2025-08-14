import requests
import json
import hashlib
import re
from bs4 import BeautifulSoup
import time

class Chaoxing:
    def __init__(self, user_info, seat_info):
        """
        初始化
        :param user_info: 用户信息字典
        :param seat_info: 座位信息字典
        """
        self.uid = user_info['uid']
        self.password = user_info['password']
        self.fid = user_info['fid']
        self.seat_info = seat_info
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Linux; Android 15; V2238A Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.179 Mobile Safari/537.36 (schild:d05e77ef983bdf21e7e1781c2a224141) (device:V2238A) Language/zh_CN com.chaoxing.mobile/ChaoXingStudy_3_6.5.9_android_phone_10890_281 (@Kalimdor)_20306d1391094cdc8d3b7b6837e3a649'
        })
        self.cookies = {}

    def login(self):
        """
        登录获取Cookie
        """
        url = 'https://passport2.chaoxing.com/fanyalogin'
        data = {
            'fid': self.fid,
            'uid': self.uid,
            'password': self.password,
            'refer': 'http%3A%2F%2Foffice.chaoxing.com',
            't': True
        }
        try:
            response = self.session.post(url, data=data, timeout=5)
            response_json = response.json()
            if response_json.get('status'):
                print('登录成功!')
                # 更新 session 的 cookies
                self.cookies = response.cookies.get_dict()
                return True
            else:
                print(f"登录失败: {response_json.get('msg2', '未知错误')}")
                return False
        except requests.RequestException as e:
            print(f"登录请求异常: {e}")
            return False

    def get_reserve_page_info(self):
        """
        获取预约页面的信息，包括用于提交的 token 和 captchaId
        """
        url = f'https://office.chaoxing.com/front/apps/seat/select?id={self.seat_info["roomId"]}&day={self.seat_info["day"]}&seatNum={self.seat_info["seatNum"]}&backLevel=1&fidEnc=92329df6bdb2d3ec'
        try:
            response = self.session.get(url, timeout=5)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 使用 BeautifulSoup 查找 token
            token_tag = soup.find('input', {'id': 'token', 'type': 'hidden'})
            if not token_tag or not token_tag.get('value'):
                print("在页面上未找到 token!")
                return None, None
            token = token_tag['value']
            print(f"成功获取到 token: {token}")

            # 使用正则表达式查找 captchaId
            captcha_id_match = re.search(r'captchaId: \'(.*?)\'', response.text)
            if not captcha_id_match:
                print("在页面上未找到 captchaId!")
                return token, None
            captcha_id = captcha_id_match.group(1)
            print(f"成功获取到 captchaId: {captcha_id}")

            return token, captcha_id
        except requests.RequestException as e:
            print(f"获取预约页面信息异常: {e}")
            return None, None
        except Exception as e:
            print(f"解析预约页面时出错: {e}")
            return None, None
            
    def get_enc(self):
        """
        根据预约信息生成加密签名 enc
        这是根据普遍的脚本推测的加密方式，如果服务器算法改变，这里可能需要更新
        """
        enc_str = f'uid={self.uid}&deptIdEnc=&roomId={self.seat_info["roomId"]}&seatNum={self.seat_info["seatNum"]}&day={self.seat_info["day"]}&startTime={self.seat_info["startTime"]}&endTime={self.seat_info["endTime"]}'
        enc = hashlib.md5(enc_str.encode('utf-8')).hexdigest()
        print(f"生成 enc: {enc}")
        return enc

    def submit(self, token, captcha_validation_str):
        """
        提交预约请求
        :param token: 从预约页面获取的 token
        :param captcha_validation_str: 验证码验证成功后得到的字符串
        """
        url = 'https://office.chaoxing.com/data/apps/seat/submit'
        
        # 构造 captcha 参数
        # 注意：这里的 captchaId 需要从 get_reserve_page_info 中获取，但为了简化，我们先假设它是固定的
        # 在实际应用中，你需要将 captchaId 传入此方法
        # captcha_id = "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1" # 这是一个示例，需要动态获取
        # captcha_value = f"validate_{captcha_id}_{captcha_validation_str}"
        
        # 从你的抓包数据看，captcha 字段可能不需要 captchaId，我们直接使用验证后的字符串
        # 这需要根据实际情况测试
        captcha_value = captcha_validation_str

        data = {
            'deptIdEnc': '',
            'roomId': self.seat_info['roomId'],
            'startTime': self.seat_info['startTime'],
            'endTime': self.seat_info['endTime'],
            'day': self.seat_info['day'],
            'seatNum': self.seat_info['seatNum'],
            'captcha': captcha_value,
            'token': token,
            'enc': self.get_enc()
        }
        
        print("\n准备提交预约，最终 payload:")
        print(json.dumps(data, indent=4))

        try:
            # 提交请求
            response = self.session.post(url, data=data, cookies=self.cookies, timeout=10)
            response_json = response.json()
            
            print("\n服务器响应:")
            print(response_json)

            if response_json.get('success'):
                print('🎉 恭喜！座位预约成功！')
                return True
            else:
                # 打印更详细的错误信息
                error_msg = response_json.get('msg', '未知错误')
                print(f'🔴 预约失败: {error_msg}')
                if '验证码' in error_msg:
                    print("提示：这通常意味着你的 captcha_validation_str 是错误的或已过期。")
                if '人数过多' in error_msg:
                    print("提示：这通常是 enc 或 token 错误，或者请求频率过高导致的。")
                return False
        except requests.RequestException as e:
            print(f"提交预约请求时发生网络错误: {e}")
            return False
        except json.JSONDecodeError:
            print(f"解析服务器响应失败，原始文本: {response.text}")
            return False

    def reserve(self):
        """
        执行完整的预约流程
        """
        if not self.login():
            return

        # 1. 获取预约页面的 token 和 captchaId
        token, captcha_id = self.get_reserve_page_info()
        if not token or not captcha_id:
            print("无法继续，缺少 token 或 captchaId。")
            return

        # 2. 获取并处理验证码
        # 这是一个复杂的过程，这里我们简化为手动操作
        print("\n--- 验证码手动操作步骤 ---")
        captcha_image_url = f"https://captcha.chaoxing.com/captcha/get/verification/image?captchaId={captcha_id}&type=rotate"
        print(f"1. 请在浏览器中打开以下链接，查看验证码图片:\n   {captcha_image_url}")
        print("2. 这是一个旋转验证码，你需要识别图片需要旋转多少度才能摆正。")
        
        # 3. 模拟验证码校验请求 (这一步在真实场景中由前端JS完成)
        # 前端JS会根据你的拖动角度，生成一个加密的 token 和 textClickArr
        # 然后请求 /check/verification/result 接口
        # 这里我们无法模拟，因为缺少前端JS的加密逻辑
        # 我们假设你通过某种方式（例如，手动抓包）获取了验证成功后的`validate`字符串
        print("3. 关键步骤：你需要通过抓包工具（如Fiddler/Charles）或浏览器开发者工具，")
        print("   在你手动完成验证码后，找到 /check/verification/result 这个请求，")
        print("   从它的响应中找到一个类似于 '44314FA9CEBA3751325A5E5715A55124' 的字符串。")
        
        captcha_validation_str = input("4. 请在此处输入你从验证码响应中获取到的 validation 字符串: ")

        if not captcha_validation_str:
            print("未输入 validation 字符串，无法继续。")
            return
            
        # 4. 提交预约
        self.submit(token, captcha_validation_str)

