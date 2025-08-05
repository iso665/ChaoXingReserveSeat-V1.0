from utils import AES_Encrypt, enc, generate_captcha_key, verify_param
import json
import requests
import re
import time
import logging
import datetime
from urllib3.exceptions import InsecureRequestWarning


def get_date(day_offset: int = 0):
    today = datetime.datetime.now().date()
    offset_day = today + datetime.timedelta(days=day_offset)
    tomorrow = offset_day.strftime("%Y-%m-%d")
    return tomorrow


class reserve:
    def __init__(
        self,
        sleep_time=0.2,
        max_attempt=50,
        enable_slider=False,
        reserve_next_day=False,
    ):
        self.login_page = "https://passport2.chaoxing.com/mlogin?loginType=1&newversion=true&fid="
        self.url = "https://office.chaoxing.com/front/third/apps/seat/code?id={}&seatNum={}"
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.seat_url = "https://office.chaoxing.com/data/apps/seat/getusedtimes"
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        self.token = ""
        self.success_times = 0
        self.fail_dict = []
        self.submit_msg = []
        self.requests = requests.session()
        self.token_pattern = re.compile("token = '(.*?)'")
        self.headers = {
            "Referer": "https://office.chaoxing.com/",
            "Host": "captcha.chaoxing.com",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        }
        self.login_headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "accept-encoding": "gzip, deflate, br, zstd",
            "cache-control": "no-cache",
            "Connection": "keep-alive",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.3 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1 wechatdevtools/1.05.2109131 MicroMessenger/8.0.5 Language/zh_CN webview/16364215743155638",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Host": "passport2.chaoxing.com",
        }

        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    def _get_page_token(self, url, require_value=False):
        """获取页面token和算法值"""
        try:
            response = self.requests.get(url=url, verify=False, timeout=10)
            html = response.content.decode("utf-8")
            
            # 获取token
            matches = re.findall(r"token = \'(.*?)\'", html)
            if not matches:
                # 尝试其他token格式
                matches = re.findall(r'token\s*=\s*["\']([^"\']*)["\']', html)
            
            value_matches = []
            if require_value:
                # 多种方式尝试获取算法值
                patterns = [
                    r'id\s*=\s*["\']algorithm["\'][^>]*value\s*=\s*["\']([^"\']*)["\']',
                    r'value\s*=\s*["\']([^"\']*)["\'][^>]*id\s*=\s*["\']algorithm["\']',
                    r'var\s+algorithm\s*=\s*["\']([^"\']*)["\']',
                    r'algorithm["\'].*?value\s*=\s*["\']([^"\']*)["\']',
                    r'<input[^>]*name\s*=\s*["\']algorithm["\'][^>]*value\s*=\s*["\']([^"\']*)["\']',
                ]
                
                for pattern in patterns:
                    value_matches = re.findall(pattern, html)
                    if value_matches:
                        break
                
                if not value_matches:
                    logging.warning(f"无法从页面获取算法值，使用默认值")
                    value_matches = ["%sd`~7^/>N4!Q#{']"]  # 默认算法值
            
            token = matches[0] if matches else ""
            algorithm_value = value_matches[0] if value_matches else ""
            
            if require_value:
                logging.info(f"获取到 token: {token}, algorithm: {algorithm_value}")
            
            return token, algorithm_value
            
        except Exception as e:
            logging.error(f"获取页面token失败: {str(e)}")
            return "", ""

    def get_login_status(self):
        self.requests.headers = self.login_headers
        self.requests.get(url=self.login_page, verify=False)

    def login(self, username, password):
        username = AES_Encrypt(username)
        password = AES_Encrypt(password)
        parm = {
            "fid": -1,
            "uname": username,
            "password": password,
            "refer": "http%3A%2F%2Foffice.chaoxing.com%2Ffront%2Fthird%2Fapps%2Fseat%2Fcode%3Fid%3D4219%26seatNum%3D380",
            "t": True,
        }
        try:
            jsons = self.requests.post(url=self.login_url, params=parm, verify=False, timeout=10)
            obj = jsons.json()
            if obj["status"]:
                logging.info(f"用户登录成功")
                return (True, "")
            else:
                logging.error(f"用户登录失败，请检查用户名和密码: {obj.get('msg2', '未知错误')}")
                return (False, obj.get("msg2", "登录失败"))
        except Exception as e:
            logging.error(f"登录请求异常: {str(e)}")
            return (False, f"登录请求异常: {str(e)}")

    def roomid(self, encode):
        """获取房间ID"""
        url = f"https://office.chaoxing.com/data/apps/seat/room/list?cpage=1&pageSize=100&firstLevelName=&secondLevelName=&thirdLevelName=&deptIdEnc={encode}"
        try:
            response = self.requests.get(url=url, timeout=10)
            json_data = response.content.decode("utf-8")
            ori_data = json.loads(json_data)
            for i in ori_data["data"]["seatRoomList"]:
                info = f'{i["firstLevelName"]}-{i["secondLevelName"]}-{i["thirdLevelName"]} id为：{i["id"]}'
                print(info)
        except Exception as e:
            logging.error(f"获取房间ID失败: {str(e)}")

    def resolve_captcha(self):
        """解决验证码"""
        logging.info(f"开始解决验证码")
        captcha_token, bg, tp = self.get_slide_captcha_data()
        
        if not captcha_token or not bg or not tp:
            logging.error(f"获取验证码数据失败，跳过此次尝试")
            return ""
    
        logging.info(f"成功获取验证码token: {captcha_token}")
        logging.info(f"验证码图片 URL-小图: {tp}, URL-大图: {bg}")
    
        try:
            x = self.x_distance(bg, tp)
            logging.info(f"成功计算验证码距离: {x}")
        except Exception as e:
            logging.error(f"计算验证码距离出错: {e}")
            x = 0

        params = {
            "callback": "jQuery33109180509737430778_1716381333117",
            "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
            "type": "slide",
            "token": captcha_token,
            "textClickArr": json.dumps([{"x": x}]),
            "coordinate": json.dumps([]),
            "runEnv": "10",
            "version": "1.1.18",
            "_": int(time.time() * 1000),
        }
        try:
            response = self.requests.get(
                f"https://captcha.chaoxing.com/captcha/check/verification/result",
                params=params,
                headers=self.headers,
                timeout=5
            )
            text = response.text.replace(
                "jQuery33109180509737430778_1716381333117(", ""
            ).replace(")", "")
            data = json.loads(text)
            logging.info(f"验证码解决结果: {data}")
            validate_val = json.loads(data.get("extraData", "{}")).get('validate', "")
            return validate_val
        except Exception as e:
            logging.error(f"解决验证码时出错: {e}")
            return ""

    def get_slide_captcha_data(self):
        """获取滑动验证码数据"""
        url = "https://captcha.chaoxing.com/captcha/get/verification/image"
        timestamp = int(time.time() * 1000)
        capture_key, token = generate_captcha_key(timestamp)
        referer = f"https://office.chaoxing.com/front/third/apps/seat/code?id=3993&seatNum=0199"
        params = {
            "callback": f"jQuery33107685004390294206_1716461324846",
            "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
            "type": "slide",
            "version": "1.1.18",
            "captchaKey": capture_key,
            "token": token,
            "referer": referer,
            "_": timestamp,
            "d": "a",
            "b": "a",
        }
        try:
            response = self.requests.get(url=url, params=params, headers=self.headers, timeout=5)
            content = response.text
            data = content.replace(
                "jQuery33107685004390294206_1716461324846(", ""
            ).replace(")", "")
            data = json.loads(data)
            captcha_token = data["token"]
            bg = data["imageVerificationVo"]["shadeImage"]
            tp = data["imageVerificationVo"]["cutoutImage"]
            return captcha_token, bg, tp
        except Exception as e:
            logging.error(f"获取验证码数据失败: {e}")
            return None, None, None

    def x_distance(self, bg, tp):
        """计算验证码滑动距离"""
        import numpy as np
        import cv2

        def cut_slide(slide):
            slider_array = np.frombuffer(slide, np.uint8)
            slider_image = cv2.imdecode(slider_array, cv2.IMREAD_UNCHANGED)
            slider_part = slider_image[:, :, :3]
            mask = slider_image[:, :, 3]
            mask[mask != 0] = 255
            x, y, w, h = cv2.boundingRect(mask)
            cropped_image = slider_part[y : y + h, x : x + w]
            return cropped_image

        c_captcha_headers = {
            "Referer": "https://office.chaoxing.com/",
            "Host": "captcha-b.chaoxing.com",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        }
        bgc, tpc = self.requests.get(bg, headers=c_captcha_headers), self.requests.get(
            tp, headers=c_captcha_headers
        )
        bg, tp = bgc.content, tpc.content
        bg_img = cv2.imdecode(np.frombuffer(bg, np.uint8), cv2.IMREAD_COLOR)
        tp_img = cut_slide(tp)
        bg_edge = cv2.Canny(bg_img, 100, 200)
        tp_edge = cv2.Canny(tp_img, 100, 200)
        bg_pic = cv2.cvtColor(bg_edge, cv2.COLOR_GRAY2RGB)
        tp_pic = cv2.cvtColor(tp_edge, cv2.COLOR_GRAY2RGB)
        res = cv2.matchTemplate(bg_pic, tp_pic, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        tl = max_loc
        return tl[0]

    def submit(self, times, roomid, seatid, action):
        """提交预约请求"""
        for seat in seatid:
            suc = False
            attempt_count = 0
            while not suc and attempt_count < self.max_attempt:
                try:
                    token, value = self._get_page_token(
                        self.url.format(roomid, seat), require_value=True
                    )
                    logging.info(f"获取到 token: {token}, algorithm value: {value}")
                    
                    if not token:
                        logging.error("获取token失败，跳过此次尝试")
                        attempt_count += 1
                        time.sleep(self.sleep_time)
                        continue
                    
                    captcha = self.resolve_captcha() if self.enable_slider else ""
                    logging.info(f"验证码token: {captcha}")
                    
                    suc = self.get_submit(
                        self.submit_url,
                        times=times,
                        token=token,
                        roomid=roomid,
                        seatid=seat,
                        captcha=captcha,
                        action=action,
                        value=value,
                    )
                    if suc:
                        return suc
                        
                except Exception as e:
                    logging.error(f"提交尝试失败: {str(e)}")
                    
                attempt_count += 1
                time.sleep(self.sleep_time)
                
        return suc

    def get_submit(self, url, times, token, roomid, seatid, captcha="", action=False, value=""):
        """发送预约提交请求"""
        delta_day = 1 if self.reserve_next_day else 0
        day = datetime.date.today() + datetime.timedelta(days=0 + delta_day)
        if action:
            day = datetime.date.today() + datetime.timedelta(days=1 + delta_day)
            
        # 构建参数字典 - 确保参数名称和顺序正确
        parm = {
            "captcha": captcha,
            "day": str(day),
            "endTime": times[1],
            "roomId": str(roomid),
            "seatNum": str(seatid),
            "startTime": times[0],
            "token": token,
            "type": "1",
            "verifyData": "1",
        }
        
        logging.info(f"提交参数: {parm}")
        
        # 使用算法值，如果没有获取到则使用默认值
        algorithm_value = value if value else "%sd`~7^/>N4!Q#{'"
        
        # 生成enc参数 - 只包含需要加密的核心参数
        encrypt_params = {
            "captcha": captcha,
            "day": str(day),
            "endTime": times[1],
            "roomId": str(roomid),
            "seatNum": str(seatid),
            "startTime": times[0],
            "token": token
        }
        
        try:
            parm["enc"] = verify_param(encrypt_params, algorithm_value)
            logging.info(f"生成的enc: {parm['enc']}")
        except Exception as e:
            logging.error(f"生成enc参数出错: {str(e)}")
            # 尝试使用旧的enc函数作为备用
            try:
                parm["enc"] = enc(encrypt_params)
                logging.info(f"使用备用enc: {parm['enc']}")
            except Exception as e2:
                logging.error(f"备用enc也失败: {str(e2)}")
                return False
        
        try:
            # 发送请求
            response = self.requests.post(url=url, params=parm, verify=True, timeout=10)
            html = response.content.decode("utf-8")
            
            # 记录提交信息
            self.submit_msg.append(times[0] + "~" + times[1] + ":  " + str(json.loads(html)))
            
            result = json.loads(html)
            logging.info(f"提交响应: {result}")
            
            # 检查响应状态
            if "success" in result:
                return result["success"]
            elif "status" in result:
                return result["status"]
            else:
                logging.warning(f"意外的响应格式: {result}")
                return False
                
        except json.JSONDecodeError as e:
            logging.error(f"解析响应JSON失败: {str(e)}")
            logging.error(f"原始响应: {html}")
            return False
        except Exception as e:
            logging.error(f"提交请求失败: {str(e)}")
            return False
