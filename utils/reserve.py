from .encrypt import AES_Encrypt, enc, generate_captcha_key
import json
import requests
import re
import time
import logging
import datetime
import pytz
import random
from urllib3.exceptions import InsecureRequestWarning

# 禁用不安全的请求警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=50, enable_slider=False, reserve_next_day=False):
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
            "Pragma": 'no-cache',
            "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Linux"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
        }
        self.login_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 10_3_1 like Mac OS X) AppleWebKit/603.1.3 (KHTML, like Gecko) Version/10.0 Mobile/14E304 Safari/602.1 wechatdevtools/1.05.2109131 MicroMessenger/8.0.5 Language/zh_CN webview/16364215743155638",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Host": "passport2.chaoxing.com"
        }

        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day
        self.beijing_tz = pytz.timezone('Asia/Shanghai')
        self.requests.headers.update(self.login_headers)

    def get_target_date(self):
        """获取正确的目标预约日期（北京时间）"""
        now = datetime.datetime.now(self.beijing_tz)
        
        # 根据reserve_next_day计算目标日期
        if self.reserve_next_day:
            target_date = now + datetime.timedelta(days=1)
        else:
            target_date = now
        
        return target_date.strftime("%Y-%m-%d")
    
    # login and page token
    def _get_page_token(self, url):
        """获取页面token，带错误处理和超时"""
        try:
            response = self.requests.get(url=url, verify=False, timeout=10)
            if response.status_code != 200:
                logging.error(f"获取token失败，状态码: {response.status_code}")
                return ""
                
            html = response.content.decode('utf-8')
            token_match = self.token_pattern.search(html)
            return token_match.group(1) if token_match else ""
        except Exception as e:
            logging.error(f"获取token异常: {str(e)}")
            return ""

    def get_login_status(self):
        """获取登录状态"""
        try:
            response = self.requests.get(url=self.login_page, verify=False, timeout=10)
            return response.status_code == 200
        except Exception as e:
            logging.error(f"获取登录状态异常: {str(e)}")
            return False

    def login(self, username, password):
        """用户登录"""
        try:
            username_enc = AES_Encrypt(username)
            password_enc = AES_Encrypt(password)
            parm = {
                "fid": -1,
                "uname": username_enc,
                "password": password_enc,
                "refer": "http%3A%2F%2Foffice.chaoxing.com%2F",
                "t": True
            }
            response = self.requests.post(
                url=self.login_url, params=parm, verify=False, timeout=10)
            
            if response.status_code != 200:
                logging.error(f"登录请求失败，状态码: {response.status_code}")
                return (False, "登录请求失败")
                
            obj = response.json()
            if obj.get('status', False):
                logging.info(f"用户 {username} 登录成功")
                return (True, '')
            else:
                msg = obj.get('msg2', '未知错误')
                logging.error(f"登录失败: {msg}")
                return (False, msg)
        except Exception as e:
            logging.error(f"登录异常: {str(e)}")
            return (False, str(e))

    # extra: get roomid
    def roomid(self, encode):
        """获取图书馆房间ID"""
        try:
            url = f"https://office.chaoxing.com/data/apps/seat/room/list?cpage=1&pageSize=100&firstLevelName=&secondLevelName=&thirdLevelName=&deptIdEnc={encode}"
            response = self.requests.get(url=url, timeout=10)
            if response.status_code != 200:
                logging.error(f"获取roomid失败，状态码: {response.status_code}")
                return
                
            data = response.json()
            for i in data.get("data", {}).get("seatRoomList", []):
                info = f'{i.get("firstLevelName", "")}-{i.get("secondLevelName", "")}-{i.get("thirdLevelName", "")} id: {i.get("id", "")}'
                print(info)
        except Exception as e:
            logging.error(f"获取roomid异常: {str(e)}")

    # solve captcha 
    def resolve_captcha(self):
        """解决滑块验证码"""
        try:
            logging.info("开始处理验证码")
            captcha_token, bg, tp = self.get_slide_captcha_data()
            if not captcha_token or not bg or not tp:
                logging.error("获取验证码数据失败")
                return ""
                
            logging.info(f"验证码数据获取成功")
            x = self.x_distance(bg, tp)
            if x is None:
                logging.error("计算滑块距离失败")
                return ""
                
            logging.info(f"计算滑块距离: {x}px")

            # 生成随机callback函数名
            callback_name = f"jQuery{random.randint(100000000000, 999999999999)}_{int(time.time()*1000)}"
            
            params = {
                "callback": callback_name,
                "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
                "type": "slide",
                "token": captcha_token,
                "textClickArr": json.dumps([{"x": x}]),
                "coordinate": json.dumps([]),
                "runEnv": "10",
                "version": "1.1.18",
                "_": int(time.time() * 1000)
            }
            
            response = self.requests.get(
                'https://captcha.chaoxing.com/captcha/check/verification/result', 
                params=params, 
                headers=self.headers,
                timeout=15
            )
            
            # 处理JSONP响应
            response_text = response.text
            if not response_text.startswith(callback_name):
                logging.error(f"验证码响应格式错误: {response_text[:100]}")
                return ""
                
            json_str = response_text.replace(callback_name, "", 1).strip("();")
            
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                logging.error(f"验证码响应JSON解析失败: {json_str[:200]}")
                return ""
                
            if data.get("success", False):
                extra_data = data.get("extraData", "")
                try:
                    extra_json = json.loads(extra_data)
                    validate_val = extra_json.get('validate', "")
                    logging.info(f"验证码处理成功: {validate_val}")
                    return validate_val
                except Exception:
                    logging.error(f"extraData解析失败: {extra_data}")
                    return ""
            else:
                logging.error(f"验证码处理失败: {data.get('message', '未知错误')}")
                return ""
        except Exception as e:
            logging.error(f"验证码处理异常: {str(e)}")
            return ""

    def get_slide_captcha_data(self):
        """获取滑块验证码数据"""
        try:
            url = "https://captcha.chaoxing.com/captcha/get/verification/image"
            timestamp = int(time.time() * 1000)
            captcha_key, token = generate_captcha_key(timestamp)
            
            # 生成随机callback函数名
            callback_name = f"jQuery{random.randint(100000000000, 999999999999)}_{timestamp}"
            
            params = {
                "callback": callback_name,
                "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
                "type": "slide",
                "version": "1.1.18",
                "captchaKey": captcha_key,
                "token": token,
                "referer": "https://office.chaoxing.com/",
                "_": timestamp,
                "d": "a",
                "b": "a"
            }
            
            response = self.requests.get(url=url, params=params, headers=self.headers, timeout=15)
            if response.status_code != 200:
                logging.error(f"获取验证码数据失败，状态码: {response.status_code}")
                return "", "", ""
                
            content = response.text
            
            # 处理JSONP响应
            if not content.startswith(callback_name):
                logging.error(f"验证码数据响应格式错误: {content[:100]}")
                return "", "", ""
                
            json_str = content.replace(callback_name, "", 1).strip("();")
            
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                logging.error(f"验证码数据JSON解析失败: {json_str[:200]}")
                return "", "", ""
                
            captcha_token = data.get("token", "")
            image_data = data.get("imageVerificationVo", {})
            bg = image_data.get("shadeImage", "")
            tp = image_data.get("cutoutImage", "")
            
            return captcha_token, bg, tp
        except Exception as e:
            logging.error(f"获取验证码数据异常: {str(e)}")
            return "", "", ""
    
    def x_distance(self, bg_url, tp_url):
        """计算滑块需要移动的距离"""
        try:
            import numpy as np
            import cv2
            
            # 下载背景图
            bg_response = self.requests.get(bg_url, timeout=15)
            if bg_response.status_code != 200:
                logging.error(f"下载背景图失败，状态码: {bg_response.status_code}")
                return None
            bg_img = cv2.imdecode(np.frombuffer(bg_response.content, np.uint8), cv2.IMREAD_COLOR)
            
            # 下载滑块图
            tp_response = self.requests.get(tp_url, timeout=15)
            if tp_response.status_code != 200:
                logging.error(f"下载滑块图失败，状态码: {tp_response.status_code}")
                return None
            tp_img = cv2.imdecode(np.frombuffer(tp_response.content, np.uint8), cv2.IMREAD_UNCHANGED)
            
            # 提取滑块
            if tp_img.shape[2] == 4:  # 带alpha通道
                mask = tp_img[:, :, 3]
                mask = cv2.threshold(mask, 1, 255, cv2.THRESH_BINARY)[1]
                x, y, w, h = cv2.boundingRect(mask)
                tp_img = tp_img[y:y+h, x:x+w, :3]
            
            # 边缘检测
            bg_edge = cv2.Canny(bg_img, 100, 200)
            tp_edge = cv2.Canny(tp_img, 100, 200)
            
            # 模板匹配
            result = cv2.matchTemplate(bg_edge, tp_edge, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            
            if max_val < 0.4:  # 匹配阈值
                logging.warning(f"模板匹配可信度低: {max_val}")
                
            return max_loc[0]
        except ImportError:
            logging.error("缺少OpenCV依赖，请安装opencv-python")
            return None
        except Exception as e:
            logging.error(f"计算滑块距离异常: {str(e)}")
            return None

    def submit(self, times, roomid, seatid, action):
        """提交预约请求"""
        if not isinstance(seatid, list):
            seatid = [seatid]  # 确保seatid是列表
        
        day_str = self.get_target_date()
        logging.info(f"预约日期: {day_str}, 时段: {times[0]}-{times[1]}")
        
        results = []  # 存储每个座位的预约结果
        
        for seat in seatid:
            logging.info(f"尝试预约座位: {seat}")
            suc = False
            attempt_count = 0
            
            while not suc and attempt_count < self.max_attempt:
                attempt_count += 1
                logging.info(f"座位 {seat} 尝试 #{attempt_count}/{self.max_attempt}")
                
                # 获取token
                token = self._get_page_token(self.url.format(roomid, seat))
                if not token:
                    logging.warning("获取token失败，稍后重试")
                    time.sleep(self.sleep_time)
                    continue
                
                # 处理验证码
                captcha = ""
                if self.enable_slider:
                    logging.info("需要滑块验证")
                    captcha = self.resolve_captcha()
                    if not captcha:
                        logging.warning("验证码获取失败，使用空值继续尝试")
                else:
                    logging.info("无需滑块验证")
                
                # 准备请求参数
                parm = {
                    "roomId": roomid,
                    "startTime": times[0],
                    "endTime": times[1],
                    "day": day_str,
                    "seatNum": seat,
                    "captcha": captcha,
                    "token": token
                }
                logging.debug(f"提交参数: {parm}")
                
                # 生成加密签名
                parm["enc"] = enc(parm)
                
                try:
                    response = self.requests.post(
                        url=self.submit_url, 
                        params=parm, 
                        verify=True,
                        timeout=15
                    )
                    
                    if response.status_code != 200:
                        logging.warning(f"预约请求失败，状态码: {response.status_code}")
                        time.sleep(self.sleep_time)
                        continue
                    
                    try:
                        result = response.json()
                    except json.JSONDecodeError:
                        logging.error(f"响应JSON解析失败: {response.text[:200]}")
                        time.sleep(self.sleep_time)
                        continue
                    
                    logging.info(f"预约响应: {result}")
                    
                    if result.get("success", False):
                        logging.info(f"座位 {seat} 预约成功!")
                        suc = True
                        results.append(True)
                        break
                    else:
                        msg = result.get("msg", "未知错误")
                        logging.warning(f"预约失败: {msg}")
                        
                        # 特定错误处理
                        if "未在系统中开放" in msg:
                            logging.error("时段未开放，停止尝试")
                            results.append(False)
                            break
                            
                        if "当前人数过多" in msg:
                            logging.warning("系统繁忙，稍后重试")
                            time.sleep(0.5)  # 稍长等待
                except Exception as e:
                    logging.error(f"请求异常: {str(e)}")
                
                time.sleep(self.sleep_time)
            
            if not suc:
                logging.warning(f"座位 {seat} 预约失败，已达最大尝试次数")
                results.append(False)
        
        # 只要有一个座位预约成功就返回True
        return any(results)
