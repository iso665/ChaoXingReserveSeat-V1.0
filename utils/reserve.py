from .encrypt import AES_Encrypt, enc, generate_captcha_key
import json
import requests
import re
import time
import logging
import datetime
import pytz
import random
import numpy as np
import cv2
from urllib3.exceptions import InsecureRequestWarning

# 禁用不安全的请求警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=50, enable_slider=False, reserve_next_day=False):
        self.login_page = "https://passport2.chaoxing.com/mlogin?loginType=1&newversion=true&fid="
        self.url = "https://office.chaoxing.com/front/third/apps/seat/code?id={}&seatNum={}"
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        self.token = ""
        self.requests = requests.session()
        self.token_pattern = re.compile("token\s*=\s*['\"](.*?)['\"]")
        
        # 请求头设置
        self.headers = {
            "Referer": "https://office.chaoxing.com/",
            "Host": "captcha.chaoxing.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }
        self.login_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
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
    
    def _get_page_token(self, url):
        """获取页面token，带重试机制和详细日志"""
        retry_count = 0
        max_retries = 3  # 最大重试次数
        
        while retry_count < max_retries:
            try:
                response = self.requests.get(
                    url=url, 
                    verify=False, 
                    timeout=10,
                    headers={
                        "Referer": "https://office.chaoxing.com/",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                    }
                )
                
                if response.status_code != 200:
                    logging.warning(f"获取token失败，状态码: {response.status_code}，URL: {url}")
                    retry_count += 1
                    time.sleep(1)
                    continue
                    
                html = response.content.decode('utf-8')
                
                # 检查登录状态是否过期
                if "登录" in html and "请先登录" in html:
                    logging.error("会话已过期，需要重新登录")
                    return "SESSION_EXPIRED"
                    
                token_match = self.token_pattern.search(html)
                if token_match:
                    return token_match.group(1)
                else:
                    logging.warning(f"未在页面中找到token，可能页面结构变化，URL: {url}")
                    logging.debug(f"页面内容: {html[:500]}...")
                    return ""
                    
            except requests.exceptions.Timeout:
                logging.warning(f"获取token超时，第 {retry_count+1} 次重试")
                retry_count += 1
                time.sleep(1)
            except Exception as e:
                logging.error(f"获取token异常: {str(e)}")
                retry_count += 1
                time.sleep(1)
        
        logging.error(f"获取token失败，已达最大重试次数 {max_retries}")
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
                return (True, '')
            else:
                msg = obj.get('msg2', '未知错误')
                return (False, msg)
        except Exception as e:
            logging.error(f"登录异常: {str(e)}")
            return (False, str(e))

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

    def resolve_captcha(self):
        """解决滑块验证码"""
        try:
            captcha_token, bg, tp = self.get_slide_captcha_data()
            if not captcha_token or not bg or not tp:
                logging.error("获取验证码数据失败")
                return ""
                
            x = self.calculate_slide_distance(bg, tp)
            if x is None:
                logging.error("计算滑块距离失败")
                return ""
                
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
                    return extra_json.get('validate', "")
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
    
    def calculate_slide_distance(self, bg_url, tp_url):
        """计算滑块需要移动的距离"""
        try:
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
                
                # 获取token - 添加额外重试逻辑
                token_retry = 0
                token = ""
                while token_retry < 2 and not token:
                    token = self._get_page_token(self.url.format(roomid, seat))
                    if token == "SESSION_EXPIRED":
                        logging.critical("会话过期，无法继续预约")
                        return False
                    if not token:
                        logging.warning("获取token失败，重试中...")
                        token_retry += 1
                        time.sleep(0.5)
                
                if not token:
                    logging.error("无法获取有效token，跳过此座位")
                    continue
                    
                # 处理验证码
                captcha = ""
                if self.enable_slider:
                    captcha = self.resolve_captcha()
                    if not captcha:
                        logging.warning("验证码获取失败，使用空值继续尝试")
                
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
                
                # 生成加密签名
                parm["enc"] = enc(parm)
                
                try:
                    response = self.requests.post(
                        url=self.submit_url, 
                        params=parm, 
                        verify=True,
                        timeout=15,
                        headers={
                            "Referer": f"https://office.chaoxing.com/front/third/apps/seat/code?id={roomid}&seatNum={seat}",
                            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                            "X-Requested-With": "XMLHttpRequest"
                        }
                    )
                    
                    if response.status_code != 200:
                        logging.warning(f"预约请求失败，状态码: {response.status_code}")
                        # 记录响应内容以便调试
                        logging.debug(f"响应内容: {response.text[:500]}")
                        time.sleep(self.sleep_time)
                        continue
                    
                    try:
                        result = response.json()
                    except json.JSONDecodeError:
                        logging.error(f"响应JSON解析失败: {response.text[:500]}")
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
                            time.sleep(0.5)
                except Exception as e:
                    logging.error(f"请求异常: {str(e)}")
                
                time.sleep(self.sleep_time)
            
            if not suc:
                logging.warning(f"座位 {seat} 预约失败，已达最大尝试次数")
                results.append(False)
        
        # 只要有一个座位预约成功就返回True
        return any(results)
