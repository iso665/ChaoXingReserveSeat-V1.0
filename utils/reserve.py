from .encrypt import AES_Encrypt, enc, generate_captcha_key, generate_behavior_analysis
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
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        
        # 修改后的cookies设置
        self.requests.cookies.update({
            'route': ''.join(random.choices('abcdef0123456789', k=32)),
            '_uid': str(random.randint(10000000, 99999999))
        })
        
        # 增强token提取模式
        self.token_patterns = [
            re.compile("token\s*=\s*['\"](.*?)['\"]"),
            re.compile("token\s*:\s*['\"](.*?)['\"]"),
            re.compile('<meta\s+name="token"\s+content="(.*?)"'),
            re.compile('window\.token\s*=\s*["\']([^"\']+)["\']'),
            re.compile('var\s+token\s*=\s*["\']([^"\']+)["\']')
        ]
        
        # 行为分析数据提取模式
        self.behavior_patterns = [
            re.compile(r'behaviorAnalysis["\']?\s*[:=]\s*["\']([^"\']+)["\']'),
            re.compile(r'data-behavior["\']?\s*[:=]\s*["\']([^"\']+)["\']'),
            re.compile(r'window\.behaviorAnalysis\s*=\s*["\']([^"\']+)["\']')
        ]
        
        # 请求头设置
        self.headers = {
            "Referer": "https://office.chaoxing.com/",
            "Host": "captcha.chaoxing.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache"
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
        
        # 缓存验证码结果和行为分析数据
        self._cached_captcha = None
        self._last_captcha_time = 0
        self._cached_behavior_analysis = None
        self._deptIdEnc = None

    def get_target_date(self):
        """获取正确的目标预约日期（北京时间）"""
        now = datetime.datetime.now(self.beijing_tz)
        if self.reserve_next_day:
            target_date = now + datetime.timedelta(days=1)
        else:
            target_date = now
        return target_date.strftime("%Y-%m-%d")
    
    def _get_page_token_and_data(self, url):
        """获取页面token和相关数据，包括behaviorAnalysis和deptIdEnc"""
        retry_count = 0
        max_retries = 5
        
        while retry_count < max_retries:
            try:
                response = self.requests.get(
                    url=url, 
                    verify=False, 
                    timeout=15,
                    headers={
                        "Referer": "https://office.chaoxing.com/",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Connection": "keep-alive",
                        "Host": "office.chaoxing.com"
                    }
                )
                
                if response.status_code != 200:
                    logging.warning(f"获取页面失败，状态码: {response.status_code}")
                    retry_count += 1
                    time.sleep(1.5)
                    continue
                    
                html = response.text
                
                # 检查登录状态
                if "登录" in html and "请先登录" in html:
                    logging.error("会话已过期，需要重新登录")
                    return "SESSION_EXPIRED", None, None
                
                # 提取token
                token = None
                for pattern in self.token_patterns:
                    token_match = pattern.search(html)
                    if token_match:
                        token = token_match.group(1)
                        break
                
                # 提取deptIdEnc
                deptIdEnc = None
                dept_pattern = re.compile(r'deptIdEnc["\']?\s*[:=]\s*["\']([^"\']+)["\']')
                dept_match = dept_pattern.search(html)
                if dept_match:
                    deptIdEnc = dept_match.group(1)
                    self._deptIdEnc = deptIdEnc
                
                # 提取或生成behaviorAnalysis
                behavior_analysis = None
                for pattern in self.behavior_patterns:
                    behavior_match = pattern.search(html)
                    if behavior_match:
                        behavior_analysis = behavior_match.group(1)
                        break
                
                if not behavior_analysis:
                    behavior_analysis = generate_behavior_analysis()
                    logging.debug("生成模拟behaviorAnalysis数据")
                
                self._cached_behavior_analysis = behavior_analysis
                
                if token:
                    logging.debug(f"成功获取页面数据: token={token[:20]}..., deptIdEnc={deptIdEnc}, behavior={behavior_analysis[:50]}...")
                    return token, deptIdEnc, behavior_analysis
                else:
                    logging.warning(f"未在页面中找到token，URL: {url}")
                    return "", deptIdEnc, behavior_analysis
                    
            except requests.exceptions.Timeout:
                logging.warning(f"获取页面超时，第 {retry_count+1} 次重试")
                retry_count += 1
                time.sleep(1.5)
            except Exception as e:
                logging.error(f"获取页面异常: {str(e)}")
                retry_count += 1
                time.sleep(1.5)
        
        logging.error(f"获取页面失败，已达最大重试次数 {max_retries}")
        return "", None, generate_behavior_analysis()

    def _get_page_token(self, url):
        """获取页面token（保持兼容性）"""
        token, _, _ = self._get_page_token_and_data(url)
        return token

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
            # 保存凭证以便重新登录
            self.username = username
            self.password = password
            
            # 加密用户名和密码
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
                url=self.login_url, data=parm, verify=False, timeout=10)
            
            if response.status_code != 200:
                logging.error(f"登录请求失败，状态码: {response.status_code}")
                return (False, "登录请求失败")
                
            obj = response.json()
            if obj.get('status', False):
                # 标记为已登录
                self._logged_in = True
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

    def resolve_captcha(self, roomid, seatid):
        """解决滑块验证码（带缓存）"""
        # 如果10分钟内解决过验证码，复用结果
        if self._cached_captcha and time.time() - self._last_captcha_time < 600:
            logging.info("复用缓存的验证码结果")
            return self._cached_captcha
            
        try:
            captcha_token, bg, tp = self.get_slide_captcha_data(roomid, seatid)
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
                    validate = extra_json.get('validate', "")
                    # 缓存结果
                    self._cached_captcha = validate
                    self._last_captcha_time = time.time()
                    return validate
                except Exception:
                    logging.error(f"extraData解析失败: {extra_data}")
                    return ""
            else:
                logging.error(f"验证码处理失败: {data.get('message', '未知错误')}")
                return ""
        except Exception as e:
            logging.error(f"验证码处理异常: {str(e)}")
            return ""

    def get_slide_captcha_data(self, roomid, seatid):
        """获取滑块验证码数据"""
        url = "https://captcha.chaoxing.com/captcha/get/verification/image"
        
        params = {
            "captchaId": "42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1",
            "type": "slide",
            "version": "1.1.18"
        }
        
        try:
            response = self.requests.get(url, params=params, headers=self.headers)
            if response.status_code != 200:
                logging.error(f"验证码请求失败，状态码: {response.status_code}")
                return None, None, None
            
            data = response.json()
            captcha_token = data.get("token")
            image_vo = data.get("imageVerificationVo", {})
            bg = image_vo.get("shadeImage")
            tp = image_vo.get("cutoutImage")
        
            if not all([captcha_token, bg, tp]):
                logging.error("验证码数据不完整")
                return None, None, None
            
            return captcha_token, bg, tp
        except Exception as e:
            logging.error(f"验证码数据获取异常: {str(e)}")
            return None, None, None

    def calculate_slide_distance(self, bg, tp):
        """计算滑块距离"""
        def cut_slide(slide):
            slider_array = np.frombuffer(slide, np.uint8)
            slider_image = cv2.imdecode(slider_array, cv2.IMREAD_UNCHANGED)
            slider_part = slider_image[:, :, :3]
            mask = slider_image[:, :, 3]
            mask[mask != 0] = 255
            x, y, w, h = cv2.boundingRect(mask)
            cropped_image = slider_part[y:y + h, x:x + w]
            return cropped_image
            
        # 验证码请求头
        c_captcha_headers = {
            "Referer": "https://office.chaoxing.com/",
            "Host": "captcha.chaoxing.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }
        
        try:
            # 获取验证码图片
            bg_response = self.requests.get(bg, headers=c_captcha_headers, timeout=10)
            tp_response = self.requests.get(tp, headers=c_captcha_headers, timeout=10)
            
            if bg_response.status_code != 200 or tp_response.status_code != 200:
                logging.error(f"获取验证码图片失败")
                return None
                
            bg_img = cv2.imdecode(np.frombuffer(bg_response.content, np.uint8), cv2.IMREAD_COLOR)
            tp_img = cut_slide(tp_response.content)
            
            # 边缘检测
            bg_edge = cv2.Canny(bg_img, 100, 200)
            tp_edge = cv2.Canny(tp_img, 100, 200)
            
            # 转换为RGB格式
            bg_pic = cv2.cvtColor(bg_edge, cv2.COLOR_GRAY2RGB)
            tp_pic = cv2.cvtColor(tp_edge, cv2.COLOR_GRAY2RGB)
            
            # 模板匹配
            res = cv2.matchTemplate(bg_pic, tp_pic, cv2.TM_CCOEFF_NORMED)
            _, _, _, max_loc = cv2.minMaxLoc(res)
            
            return max_loc[0]
        except Exception as e:
            logging.error(f"计算滑块距离异常: {str(e)}")
            return None

    def submit(self, times, roomid, seatid, action):
        """提交预约请求 - 适配新接口"""
        def format_time(t):
            parts = t.split(':')
            if len(parts) == 2:
                return f"{t}:00"
            return t
        
        start_time = format_time(times[0])
        end_time = format_time(times[1])
        
        if not isinstance(seatid, list):
            seatid = [seatid]
        
        day_str = self.get_target_date()
        logging.info(f"预约日期: {day_str}, 时段: {start_time}-{end_time}")
        
        def process_seat(seat):
            session_copy = self.copy_session()
            
            # 检查会话有效性
            if not session_copy.requests.cookies.get("JSESSIONID"):
                logging.warning("会话已过期，尝试重新登录")
                login_result = session_copy.login(session_copy.username, session_copy.password)
                if not login_result[0]:
                    logging.error(f"重新登录失败: {login_result[1]}")
                    return False
                else:
                    logging.info("重新登录成功")
                    session_copy.requests.headers.update({'Host': 'office.chaoxing.com'})
        
            logging.info(f"尝试预约座位: {seat}")
            suc = False
            attempt_count = 0
            
            while not suc and attempt_count < self.max_attempt:
                attempt_count += 1
                logging.info(f"座位 {seat} 尝试 #{attempt_count}/{self.max_attempt}")
                
                # 获取完整页面数据
                token, deptIdEnc, behavior_analysis = session_copy._get_page_token_and_data(
                    self.url.format(roomid, seat)
                )
                
                if token == "SESSION_EXPIRED":
                    logging.critical("会话过期，无法继续预约")
                    return False
                    
                if not token:
                    logging.warning("获取token失败，重试中...")
                    time.sleep(1)
                    continue
                
                # 处理验证码
                captcha = ""
                if self.enable_slider:
                    captcha = session_copy.resolve_captcha(roomid, seat)
                    if not captcha:
                        logging.warning("验证码获取失败，使用空值继续尝试")
                
                # 准备新版请求参数 - 根据抓包数据调整
                parm = {
                    "deptIdEnc": deptIdEnc or self._deptIdEnc or "92329df6bdb2d3ec",  # 使用默认值或从页面提取的值
                    "roomId": str(roomid),
                    "startTime": start_time,
                    "endTime": end_time,
                    "day": day_str,
                    "seatNum": str(seat).zfill(3),  # 座位号补零到3位
                    "captcha": captcha,
                    "token": token,
                    "behaviorAnalysis": behavior_analysis or session_copy._cached_behavior_analysis
                }
                
                # 生成加密签名
                parm["enc"] = enc(parm)
                
                try:
                    # 使用新的请求头
                    headers = {
                        "Host": "office.chaoxing.com",
                        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "X-Requested-With": "XMLHttpRequest",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                        "Referer": f"https://office.chaoxing.com/front/third/apps/seat/code?id={roomid}&seatNum={seat}",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        "Accept-Encoding": "gzip, deflate, br"
                    }
                    
                    response = session_copy.requests.post(
                        url=self.submit_url, 
                        data=parm, 
                        verify=True,
                        timeout=15,
                        headers=headers
                    )
                    
                    if response.status_code != 200:
                        logging.warning(f"预约请求失败，状态码: {response.status_code}")
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
                    else:
                        msg = result.get("msg", "未知错误")
                        logging.warning(f"预约失败: {msg}")
                        
                        # 特定错误处理
                        if "未在系统中开放" in msg:
                            logging.error("时段未开放，停止尝试")
                            break
                            
                        if "当前人数过多" in msg:
                            logging.warning("系统繁忙，稍后重试")
                            time.sleep(0.5)
                        
                        if "请等待5分钟后尝试" in msg:
                            logging.warning("触发频次限制，稍后重试")
                            time.sleep(2)
                            
                except Exception
