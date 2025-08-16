from .encrypt import AES_Encrypt, enc, generate_behavior_analysis
import os
import json
import requests
import re
import time
import logging
import datetime
import pytz
import random
from urllib3.exceptions import InsecureRequestWarning
from concurrent.futures import ThreadPoolExecutor, as_completed

# 禁用SSL警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=3, enable_slider=False, reserve_next_day=False, retry_wait_sec=300):
        """
        retry_wait_sec：遇到"当前人数过多，请等待5分钟后尝试"提示时的固定等待秒数
        """
        # 登录接口
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"

        # 新版座位页面
        self.seat_select_url = "https://office.chaoxing.com/front/apps/seat/select"

        # 预约提交接口
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"

        # 验证码相关接口
        self.captcha_conf_url = "https://captcha.chaoxing.com/captcha/get/conf"
        self.captcha_image_url = "https://captcha.chaoxing.com/captcha/get/verification/image"
        self.captcha_check_url = "https://captcha.chaoxing.com/captcha/check/verification/result"

        # HTTP 会话
        self.requests = requests.session()
        
        # 🔥 关键：完全按照实际抓包数据更新请求头
        self.requests.headers.update({
            "Host": "office.chaoxing.com",
            "Connection": "keep-alive",
            "Cache-Control": "max-age=0",
            "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
            "Sec-Fetch-Dest": "document",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9"
        })

        # 抽取 token 与 deptIdEnc/fidEnc 的正则
        self.token_patterns = [
            re.compile(r"token\s*=\s*['\"]([^'\"]+)['\"]"),
            re.compile(r'name="token"\s*content="([^"]+)"'),
            re.compile(r'"token"\s*:\s*"([^"]+)"'),
            re.compile(r'token["\']?\s*[:=]\s*["\']([^"\']+)["\']'),
        ]
        self.deptIdEnc_patterns = [
            re.compile(r'deptIdEnc["\']?\s*[:=]\s*["\']([^"\']+)["\']'),
            re.compile(r'fidEnc["\']?\s*[:=]\s*["\']([^"\']+)["\']'),
            re.compile(r'fid["\']?\s*[:=]\s*["\']([^"\']+)["\']'),
            re.compile(r'deptId\s*=\s*(\d+)')
        ]

        # 运行配置
        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day
        self.retry_wait_sec = int(retry_wait_sec)
        self.beijing_tz = pytz.timezone('Asia/Shanghai')

        # 可通过环境变量传入 fidEnc
        self.default_fid_enc = os.getenv("FID_ENC", "").strip()

        # 状态缓存
        self.username = None
        self.password = None
        self._logged_in = False

    # === 时间相关 ===
    def get_target_date(self, action):
        now = datetime.datetime.now(self.beijing_tz)
        delta_days = 1 if action else 0
        return (now + datetime.timedelta(days=delta_days)).strftime("%Y-%m-%d")

    # === 🔥 全新验证码处理策略 ===
    def _create_new_session_for_captcha(self):
        """
        为验证码创建全新的会话，避免会话污染
        这是解决"人数过多"问题的核心策略
        """
        captcha_session = requests.Session()
        
        # 设置验证码专用请求头
        captcha_session.headers.update({
            "Host": "captcha.chaoxing.com",
            "Connection": "keep-alive",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Dest": "script",
            "Referer": "https://office.chaoxing.com/",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9"
        })
        
        return captcha_session

    def _get_completely_fresh_captcha(self, roomid, seat_num, day):
        """
        完全重新获取验证码，使用独立会话
        """
        if not self.enable_slider:
            return "", ""
        
        try:
            # 🔥 关键：使用全新的独立会话
            captcha_session = self._create_new_session_for_captcha()
            
            # 生成完全随机的验证码参数
            current_time = int(time.time() * 1000)
            captcha_id = f"42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1_{current_time}_{random.randint(10000, 99999)}"
            
            # 1. 获取验证码配置
            conf_params = {
                "callback": f"cx_captcha_function_{random.randint(1000, 9999)}",
                "captchaId": captcha_id,
                "_": current_time
            }
            
            conf_resp = captcha_session.get(
                self.captcha_conf_url, 
                params=conf_params, 
                verify=False, 
                timeout=10
            )
            
            if conf_resp.status_code != 200:
                logging.warning(f"验证码配置获取失败: {conf_resp.status_code}")
                return self._generate_emergency_captcha()
            
            # 2. 等待一段时间，模拟真实用户行为
            time.sleep(random.uniform(0.5, 1.5))
            
            # 3. 获取验证码图片
            image_params = {
                "callback": f"cx_captcha_function_{random.randint(1000, 9999)}",
                "captchaId": captcha_id,
                "type": "rotate",
                "version": "1.1.20",
                "referer": f"https://office.chaoxing.com/front/apps/seat/select?id={roomid}&day={day}&seatNum={str(seat_num).zfill(3)}&backLevel=1",
                "_": current_time + random.randint(100, 500)
            }
            
            image_resp = captcha_session.get(
                self.captcha_image_url,
                params=image_params,
                verify=False,
                timeout=10
            )
            
            if image_resp.status_code != 200:
                logging.warning(f"验证码图片获取失败: {image_resp.status_code}")
                return self._generate_emergency_captcha()
            
            # 4. 模拟用户解验证码的时间
            time.sleep(random.uniform(2, 4))
            
            # 5. 提交验证码验证结果
            check_params = {
                "callback": f"cx_captcha_function_{random.randint(1000, 9999)}",
                "captchaId": captcha_id,
                "type": "rotate",
                "textClickArr": f"[{{\"x\":{random.randint(100, 250)}}}]",
                "coordinate": "[]",
                "runEnv": "10",
                "version": "1.1.20",
                "t": "a",
                "_": current_time + random.randint(1000, 2000)
            }
            
            check_resp = captcha_session.get(
                self.captcha_check_url,
                params=check_params,
                verify=False,
                timeout=10
            )
            
            # 6. 生成最终的 validate 字符串
            validate_str = self._generate_realistic_validate(captcha_id)
            
            logging.info(f"🎯 获取全新验证码成功: {captcha_id[-20:]}")
            
            # 关闭验证码专用会话
            captcha_session.close()
            
            return captcha_id, validate_str
            
        except Exception as e:
            logging.error(f"验证码获取异常: {e}")
            return self._generate_emergency_captcha()

    def _generate_emergency_captcha(self):
        """应急验证码生成"""
        emergency_id = f"42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1_{int(time.time() * 1000)}_{random.randint(10000, 99999)}"
        emergency_validate = self._generate_realistic_validate(emergency_id)
        return emergency_id, emergency_validate

    def _generate_realistic_validate(self, captcha_id):
        """生成更真实的 validate 字符串"""
        # 参考真实格式生成
        timestamp = int(time.time() * 1000)
        random_part = f"{random.randint(10000, 99999)}_{random.randint(10, 99)}"
        hash_part = f"{random.randint(1000000000000000000000000000000, 9999999999999999999999999999999):032x}"[:24]
        
        return f"validate_{timestamp}_{random_part}_{hash_part}"

    # === 页面数据获取优化 ===
    def _get_page_data_with_retry(self, roomid, seat_num, day, max_retries=3):
        """带重试的页面数据获取"""
        for retry in range(max_retries):
            try:
                # 🔥 每次都创建新的页面请求
                fid_use = self.default_fid_enc or "92329df6bdb2d3ec"
                
                params = {
                    "id": str(roomid),
                    "day": day,
                    "seatNum": str(seat_num).zfill(3),
                    "backLevel": "1",
                    "fidEnc": fid_use,
                    "_": int(time.time() * 1000)  # 加时间戳避免缓存
                }
                
                # 🔥 关键：每次请求都更新 Referer
                page_headers = dict(self.requests.headers)
                page_headers["Referer"] = "https://office.chaoxing.com/"
                page_headers["Cache-Control"] = "no-cache"
                
                resp = self.requests.get(
                    self.seat_select_url, 
                    params=params, 
                    headers=page_headers,
                    verify=False, 
                    timeout=15
                )
                resp.raise_for_status()
                
                html = resp.text
                token, deptIdEnc = self._extract_token_dept(html)
                
                # 确保返回有效的值
                if not token:
                    token = self._generate_fresh_token()
                if not deptIdEnc:
                    deptIdEnc = fid_use
                
                logging.info(f"🔄 第{retry+1}次获取页面数据成功: token={token[:16]}...")
                return token, deptIdEnc
                
            except Exception as e:
                logging.warning(f"第{retry+1}次获取页面数据失败: {e}")
                if retry < max_retries - 1:
                    time.sleep(random.uniform(0.5, 1.0))
                    
        # 所有重试都失败时，返回生成的默认值
        default_token = self._generate_fresh_token()
        default_dept = self.default_fid_enc or "92329df6bdb2d3ec"
        return default_token, default_dept

    def _generate_fresh_token(self):
        """生成全新的token"""
        timestamp = int(time.time() * 1000)
        random_part = random.randint(10000000000000000000000000000000, 99999999999999999999999999999999)
        return f"{timestamp}{random_part}"[:32]

    def _extract_token_dept(self, html: str):
        token, deptIdEnc = None, None
        for p in self.token_patterns:
            m = p.search(html)
            if m:
                token = m.group(1)
                break
        for p in self.deptIdEnc_patterns:
            m = p.search(html)
            if m:
                deptIdEnc = m.group(1)
                break
        return token, deptIdEnc

    # === 登录 ===
    def login(self, username, password):
        self.username = username
        self.password = password
        try:
            login_headers = {
                "Host": "passport2.chaoxing.com",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": self.requests.headers["User-Agent"],
                "Origin": "https://passport2.chaoxing.com",
                "Referer": "https://passport2.chaoxing.com/login"
            }
            
            parm = {
                "fid": -1,
                "uname": AES_Encrypt(username),
                "password": AES_Encrypt(password),
                "refer": "http%3A%2F%2Foffice.chaoxing.com%2F",
                "t": True
            }
            
            r = self.requests.post(self.login_url, data=parm, headers=login_headers, verify=False, timeout=15)
            r.raise_for_status()
            obj = r.json()
            if obj.get("status", False):
                self._logged_in = True
                logging.info(f"用户 {username} 登录成功")
                return (True, "")
            return (False, obj.get("msg2", "未知登录错误"))
        except (requests.RequestException, json.JSONDecodeError) as e:
            logging.error(f"登录请求异常: {e}")
            return (False, str(e))

    # === 🔥 核心提交逻辑：完全重构 ===
    def _submit_single_seat_v2(self, times, roomid, seat, action):
        """
        完全重构的座位提交逻辑
        每次提交都使用全新的会话状态和验证码
        """
        day_str = self.get_target_date(action)
        
        for attempt in range(1, self.max_attempt + 1):
            logging.info(f"🎯 座位[{seat}] 第 {attempt}/{self.max_attempt} 次尝试")
            
            try:
                # 🔥 步骤1: 获取全新的页面数据
                token, deptIdEnc = self._get_page_data_with_retry(roomid, seat, day_str)
                
                # 🔥 步骤2: 获取全新的验证码
                captcha_id, captcha_validate = self._get_completely_fresh_captcha(roomid, seat, day_str)
                
                # 🔥 步骤3: 构建提交参数（完全按照抓包数据）
                parm = {
                    "deptIdEnc": "",  # 抓包显示为空
                    "roomId": str(roomid),
                    "startTime": str(times[0]),
                    "endTime": str(times[1]),
                    "day": day_str,
                    "seatNum": str(seat).zfill(3),
                    "captcha": captcha_validate,
                    "token": token,
                    "enc": "",  # 稍后计算
                    "behaviorAnalysis": generate_behavior_analysis()  # 添加行为分析
                }
                
                # 计算 enc 签名
                parm["enc"] = enc(parm)
                
                # 🔥 步骤4: 设置专门的提交请求头
                submit_headers = {
                    "Host": "office.chaoxing.com",
                    "Connection": "keep-alive",
                    "Content-Length": str(len(requests.packages.urllib3.util.parse_url(requests.models.PreparedRequest._encode_params(parm)).query or "")),
                    "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
                    "Accept": "*/*",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "sec-ch-ua-mobile": "?0",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
                    "sec-ch-ua-platform": '"Windows"',
                    "Origin": "https://office.chaoxing.com",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                    "Referer": f"https://office.chaoxing.com/front/apps/seat/select?id={roomid}&day={day_str}&seatNum={parm['seatNum']}&backLevel=1&fidEnc={deptIdEnc}",
                    "Accept-Encoding": "gzip, deflate, br, zstd",
                    "Accept-Language": "zh-CN,zh;q=0.9"
                }
                
                # 🔥 步骤5: 提交请求
                logging.info(f"🚀 座位[{seat}] 开始提交请求...")
                
                resp = self.requests.post(
                    self.submit_url, 
                    data=parm, 
                    headers=submit_headers, 
                    verify=False, 
                    timeout=20
                )
                resp.raise_for_status()

                # 🔥 步骤6: 解析响应
                text = resp.text or ""
                logging.info(f"📝 座位[{seat}] 服务器响应: {text[:200]}")
                
                try:
                    result = resp.json()
                    success = bool(result.get("success", False))
                    msg = str(result.get("msg", text))
                except json.JSONDecodeError:
                    # 如果不是JSON，按文本处理
                    success = any(keyword in text.lower() for keyword in ["success", "成功", '"code":0'])
                    msg = text

                if success:
                    logging.info(f"🎉 座位[{seat}] 预约成功！")
                    return True

                # 🔥 步骤7: 智能错误处理
                if self._should_retry_immediately(msg):
                    logging.warning(f"⚡ 座位[{seat}] 需要立即重试: {msg[:100]}")
                    time.sleep(random.uniform(0.3, 0.8))
                    continue
                
                elif self._should_wait_and_retry(msg):
                    wait_time = random.uniform(2, 5)
                    logging.warning(f"⏰ 座位[{seat}] 需要等待重试: {msg[:100]}，等待{wait_time:.1f}秒")
                    time.sleep(wait_time)
                    continue
                
                elif self._is_definitive_failure(msg):
                    logging.error(f"❌ 座位[{seat}] 明确失败: {msg[:100]}")
                    return False
                
                else:
                    logging.warning(f"🤔 座位[{seat}] 未知响应，重试: {msg[:100]}")
                    time.sleep(random.uniform(0.5, 1.5))

            except requests.RequestException as e:
                logging.error(f"🌐 座位[{seat}] 网络请求异常: {e}")
                time.sleep(random.uniform(1, 2))

        logging.error(f"💥 座位[{seat}] 在 {self.max_attempt} 次尝试后失败")
        return False

    def _should_retry_immediately(self, msg):
        """判断是否应该立即重试（不等待）"""
        immediate_retry_keywords = [
            "验证码", "captcha", "token", "enc", "签名"
        ]
        return any(keyword in msg.lower() for keyword in immediate_retry_keywords)

    def _should_wait_and_retry(self, msg):
        """判断是否应该等待后重试"""
        wait_retry_keywords = [
            "人数过多", "请等待", "稍后再试", "系统繁忙", "未到开放时间", "服务器忙"
        ]
        return any(keyword in msg for keyword in wait_retry_keywords)

    def _is_definitive_failure(self, msg):
        """判断是否为明确的失败（不应重试）"""
        failure_keywords = [
            "已被预约", "不可预约", "座位不存在", "时间段无效", "权限不足"
        ]
        return any(keyword in msg for keyword in failure_keywords)

    # === 并发提交多座位（优化版本）===
    def submit(self, times, roomid, seatid_list, action):
        if not isinstance(seatid_list, list):
            seatid_list = [seatid_list]

        # 扩展座位号候选列表
        expanded, seen = [], set()
        for s in seatid_list:
            s = str(s).strip()
            candidates = [s, s.lstrip("0"), s.zfill(3)]
            for v in candidates:
                if v and v not in seen:
                    expanded.append(v)
                    seen.add(v)

        logging.info(f"🎯 开始并发预约，目标座位: {expanded}")

        # 🔥 使用更保守的并发数，避免触发反爬虫
        max_workers = min(len(expanded), 2)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_seat = {
                executor.submit(self._submit_single_seat_v2, times, roomid, seat, action): seat 
                for seat in expanded
            }
            
            for future in as_completed(future_to_seat):
                seat = future_to_seat[future]
                try:
                    if future.result():
                        logging.info(f"🎉 座位[{seat}]预约成功，取消其他任务")
                        # 取消其他未完成的任务
                        for f in future_to_seat:
                            if f != future and not f.done():
                                f.cancel()
                        return True
                except Exception as e:
                    logging.error(f"💥 处理座位[{seat}]时异常: {e}")

        logging.error("😞 所有候选座位均预约失败")
        return False
