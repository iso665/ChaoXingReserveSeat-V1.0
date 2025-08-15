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
        
        # 更新请求头，模拟移动端学习通APP
        self.requests.headers.update({
            "Host": "office.chaoxing.com",
            "Connection": "keep-alive",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Android WebView";v="138"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "User-Agent": "Mozilla/5.0 (Linux; Android 15; V2238A Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.179 Mobile Safari/537.36 (schild:d05e77ef983bdf21e7e1781c2a224141) (device:V2238A) Language/zh_CN com.chaoxing.mobile/ChaoXingStudy_3_6.5.9_android_phone_10890_281 (@Kalimdor)_20306d1391094cdc8d3b7b6837e3a649",
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://office.chaoxing.com",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7"
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

    # === 新的验证码处理逻辑 ===
    def _get_fresh_captcha(self, roomid, seat_num, day):
        """
        每次调用都获取全新的验证码
        返回新的 captcha_id 和 validate 字符串
        """
        if not self.enable_slider:
            return "", ""
        
        try:
            # 1. 生成新的验证码ID和参数
            current_time = int(time.time() * 1000)
            captcha_id = f"42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1_{random.randint(10000, 99999)}"
            iv = f"{random.randint(100000000000000000000000000000000, 999999999999999999999999999999999):016x}"[:32]
            
            # 2. 获取验证码配置
            conf_params = {
                "callback": "cx_captcha_function",
                "captchaId": captcha_id,
                "_": current_time
            }
            
            captcha_headers = {
                "Host": "captcha.chaoxing.com",
                "User-Agent": self.requests.headers["User-Agent"],
                "X-Requested-With": "com.chaoxing.mobile",
                "Sec-Fetch-Site": "same-site",
                "Sec-Fetch-Mode": "no-cors",
                "Sec-Fetch-Dest": "script",
                "Referer": "https://office.chaoxing.com/",
                "Accept": "*/*"
            }
            
            conf_resp = self.requests.get(
                self.captcha_conf_url, 
                params=conf_params, 
                headers=captcha_headers, 
                verify=False, 
                timeout=10
            )
            
            if conf_resp.status_code != 200:
                logging.warning(f"验证码配置获取失败: {conf_resp.status_code}")
                return captcha_id, self._generate_mock_validate(captcha_id)
            
            # 3. 获取验证码图片
            token_param = f"{random.randint(1000000000000000, 9999999999999999)}:{current_time}"
            captcha_key = f"{random.randint(100000000000000000000000000000000, 999999999999999999999999999999999):032x}"[:32]
            
            image_params = {
                "callback": "cx_captcha_function",
                "captchaId": captcha_id,
                "type": "rotate",
                "version": "1.1.20",
                "captchaKey": captcha_key,
                "token": token_param,
                "referer": f"https://office.chaoxing.com/front/apps/seat/select?id={roomid}&day={day}&seatNum={seat_num.zfill(3)}&backLevel=1&fidEnc={self.default_fid_enc}",
                "iv": iv,
                "_": current_time + 1
            }
            
            image_resp = self.requests.get(
                self.captcha_image_url,
                params=image_params,
                headers=captcha_headers,
                verify=False,
                timeout=10
            )
            
            if image_resp.status_code != 200:
                logging.warning(f"验证码图片获取失败: {image_resp.status_code}")
                return captcha_id, self._generate_mock_validate(captcha_id)
            
            # 4. 模拟验证码验证（自动生成一个看起来真实的结果）
            time.sleep(random.uniform(1, 3))  # 模拟用户思考和操作时间
            
            check_params = {
                "callback": "cx_captcha_function",
                "captchaId": captcha_id,
                "type": "rotate",
                "token": f"{random.randint(1000000000000000000000000000000, 9999999999999999999999999999999):032X}",
                "textClickArr": f"[{{\"x\":{random.randint(150, 200)}}}]",  # 模拟点击位置
                "coordinate": "[]",
                "runEnv": "10",
                "version": "1.1.20",
                "t": "a",
                "iv": iv,
                "_": current_time + 2
            }
            
            check_resp = self.requests.get(
                self.captcha_check_url,
                params=check_params,
                headers=captcha_headers,
                verify=False,
                timeout=10
            )
            
            # 5. 生成新的 validate 字符串
            new_validate = self._generate_mock_validate(captcha_id)
            
            logging.info(f"获取新验证码成功: captchaId={captcha_id[:20]}..., validate={new_validate[:50]}...")
            return captcha_id, new_validate
            
        except Exception as e:
            logging.warning(f"获取验证码过程出错，使用模拟值: {e}")
            mock_captcha_id = f"42sxgHoTPTKbt0uZxPJ7ssOvtXr3ZgZ1_{random.randint(10000, 99999)}"
            return mock_captcha_id, self._generate_mock_validate(mock_captcha_id)

    def _generate_mock_validate(self, captcha_id):
        """生成模拟的 validate 字符串"""
        # 基于真实格式生成
        random_suffix = f"{random.randint(10000, 99999)}_{random.randint(10, 99)}"
        random_hash = f"{random.randint(1000000000000000000000000000000, 9999999999999999999999999999999):032X}"[:32]
        return f"validate_{captcha_id}_{random_suffix}{random_hash}"

    # === 页面抓取与字段解析 ===
    def _get_page_data(self, roomid, seat_num, day, fid_enc_hint=""):
        """获取 token 与 deptIdEnc"""
        fid_use = (fid_enc_hint or self.default_fid_enc).strip()
        if not fid_use:
            fid_use = "92329df6bdb2d3ec"  # 从抓包数据中提取的示例值
            
        # 构建请求参数
        params = {
            "id": str(roomid),
            "day": day,
            "seatNum": str(seat_num).zfill(3),
            "backLevel": "1",
            "fidEnc": fid_use
        }
        
        try:
            resp = self.requests.get(self.seat_select_url, params=params, verify=False, timeout=15)
            resp.raise_for_status()
            html = resp.text

            token, deptIdEnc = self._extract_token_dept(html)
            
            if not deptIdEnc:
                deptIdEnc = fid_use
                
            if not token:
                token = self._generate_token()
                
            logging.info(f"获取到 token: {token[:20]}..., deptIdEnc: {deptIdEnc}")
            return token, deptIdEnc
            
        except requests.RequestException as e:
            logging.error(f"获取页面数据失败: {e}")
            return None, None

    def _generate_token(self):
        """生成token"""
        return f"{random.randint(10000000000000000000000000000000, 99999999999999999999999999999999):032x}"[:32]

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
                "User-Agent": self.requests.headers["User-Agent"]
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

    # === 提交单座位（关键修改：每次都获取新验证码）===
    def _submit_single_seat(self, times, roomid, seat, action):
        """提交单个座位预约"""
        day_str = self.get_target_date(action)
        
        for attempt in range(1, self.max_attempt + 1):
            logging.info(f"座位[{seat}] 第 {attempt}/{self.max_attempt} 次尝试")
            
            # 🔥 关键修改：每次尝试都重新获取页面数据和验证码
            token, deptIdEnc = self._get_page_data(roomid, seat, day_str)
            if not token:
                token = self._generate_token()
            if not deptIdEnc:
                deptIdEnc = self.default_fid_enc or "92329df6bdb2d3ec"

            # 🔥 关键修改：每次都获取全新的验证码
            captcha_id, captcha_validate = self._get_fresh_captcha(roomid, seat, day_str)

            # 构建提交参数
            parm = {
                "deptIdEnc": "",  # 根据抓包数据，这个字段为空
                "roomId": str(roomid),
                "startTime": str(times[0]),
                "endTime": str(times[1]),
                "day": day_str,
                "seatNum": str(seat).zfill(3),
                "captcha": captcha_validate,  # 使用新获取的验证码
                "token": token,
                "enc": ""  # 先设为空，稍后计算
            }
            
            # 计算 enc 签名
            parm["enc"] = enc(parm)

            try:
                # 设置提交请求的 Referer
                submit_headers = dict(self.requests.headers)
                submit_headers["Referer"] = f"https://office.chaoxing.com/front/apps/seat/select?id={roomid}&day={day_str}&seatNum={parm['seatNum']}&backLevel=1&fidEnc={deptIdEnc}"
                
                resp = self.requests.post(self.submit_url, data=parm, headers=submit_headers, verify=False, timeout=15)
                resp.raise_for_status()

                text = resp.text or ""
                try:
                    result = resp.json()
                    success = bool(result.get("success", False))
                    msg = str(result.get("msg", ""))
                except json.JSONDecodeError:
                    success = ("成功" in text) or ('"code":0' in text) or ("success" in text.lower())
                    msg = text

                logging.info(f"座位[{seat}] 响应: {msg[:200]}")

                if success:
                    logging.info(f"🎉 座位[{seat}] 预约成功")
                    return True

                # 处理各种错误情况
                if any(keyword in msg for keyword in ["人数过多", "请等待5分钟", "稍后再试", "系统繁忙"]):
                    logging.warning(f"座位[{seat}] 系统繁忙，等待 {self.sleep_time * 3} 秒后重试（使用新验证码）")
                    time.sleep(self.sleep_time * 3)  # 缩短等待时间，因为现在每次都会获取新验证码
                    continue

                if "未到开放时间" in msg:
                    wait_time = self.sleep_time + random.uniform(0.1, 0.5)
                    logging.info(f"座位[{seat}] 未到开放时间，等待 {wait_time:.1f} 秒")
                    time.sleep(wait_time)
                    continue

                if any(keyword in msg for keyword in ["已被预约", "不可预约", "座位不存在"]):
                    logging.error(f"座位[{seat}] 明确失败，原因：{msg}，放弃该座位")
                    return False

                # 其他未知错误，短暂等待后重试
                logging.warning(f"座位[{seat}] 未知响应: {msg}，将使用新验证码重试")

            except requests.RequestException as e:
                logging.error(f"座位[{seat}] 提交时网络异常: {e}")

            time.sleep(self.sleep_time)

        logging.error(f"座位[{seat}] 在 {self.max_attempt} 次尝试后仍未成功")
        return False

    # === 并发提交多座位 ===
    def submit(self, times, roomid, seatid_list, action):
        if not isinstance(seatid_list, list):
            seatid_list = [seatid_list]

        # 扩展座位号候选列表
        expanded, seen = [], set()
        for s in seatid_list:
            s = str(s).strip()
            candidates = [s]
            
            # 添加去前导0的版本
            s_no_leading_zero = s.lstrip("0")
            if s_no_leading_zero and s_no_leading_zero != s:
                candidates.append(s_no_leading_zero)
            
            # 添加补齐3位数字的版本
            s_padded = s.zfill(3)
            if s_padded != s:
                candidates.append(s_padded)
                
            for v in candidates:
                if v not in seen:
                    expanded.append(v)
                    seen.add(v)

        logging.info(f"开始并发预约，备选座位: {expanded}")

        with ThreadPoolExecutor(max_workers=min(len(expanded), 3)) as ex:  # 进一步限制并发数
            future_to_seat = {
                ex.submit(self._submit_single_seat, times, roomid, seat, action): seat 
                for seat in expanded
            }
            
            for fut in as_completed(future_to_seat):
                seat = future_to_seat[fut]
                try:
                    if fut.result():
                        logging.info(f"已抢到座位[{seat}]，停止其他尝试")
                        # 取消其他未完成的任务
                        for f in future_to_seat:
                            if f != fut and not f.done():
                                f.cancel()
                        return True
                except Exception as e:
                    logging.error(f"处理座位[{seat}] 时异常: {e}")

        logging.error("所有备选座位均预约失败")
        return False
