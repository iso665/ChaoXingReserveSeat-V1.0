from .encrypt import AES_Encrypt, enc, generate_behavior_analysis
import json
import requests
import re
import time
import logging
import datetime
import pytz
import random  # 新增：用于退避抖动
from urllib3.exceptions import InsecureRequestWarning
from concurrent.futures import ThreadPoolExecutor, as_completed

# 禁用不安全的请求警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=3, enable_slider=False, reserve_next_day=False, retry_wait_sec=300):
        """
        retry_wait_sec：遇到“当前人数过多，请等待5分钟后尝试”等提示时的固定等待秒数
        """
        self.login_page = "https://passport2.chaoxing.com/mlogin?loginType=1&newversion=true&fid="
        self.seat_code_url = "https://office.chaoxing.com/front/third/apps/seat/code?id={}&seatNum={}"
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.login_url = "https://passport.chaoxing.com/fanyalogin"  # 有些学校在 passport2 与 passport 混用，保留此地址

        self.requests = requests.session()
        self.requests.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        })

        # 升级正则表达式列表，尝试多种可能格式
        self.token_patterns = [
            re.compile(r"token\s*=\s*['\"]([^'\"]+)['\"]"),
            re.compile(r'name="token"\s*content="([^"]+)"')
        ]
        self.deptIdEnc_patterns = [
            re.compile(r'deptIdEnc["\']?\s*[:=]\s*["\']([^"\']+)["\']'),  # deptIdEnc: "xxx" 或 deptIdEnc = 'xxx'
            re.compile(r'fid["\']?\s*[:=]\s*["\']([^"\']+)["\']'),        # 备用：fid: "xxx"
            re.compile(r'deptId\s*=\s*(\d+)')                              # 备用：deptId = 12345
        ]

        # 脚本配置
        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day
        self.retry_wait_sec = int(retry_wait_sec)
        self.beijing_tz = pytz.timezone('Asia/Shanghai')

        # 缓存数据
        self.username = None
        self.password = None
        self._logged_in = False

    def get_target_date(self, action):
        now = datetime.datetime.now(self.beijing_tz)
        delta_days = 1 if action else 0
        target_date = now + datetime.timedelta(days=delta_days)
        return target_date.strftime("%Y-%m-%d")

    def _get_page_data(self, roomid, seat_num):
        url = self.seat_code_url.format(roomid, seat_num)
        try:
            response = self.requests.get(url, verify=False, timeout=15)
            response.raise_for_status()
            html = response.text

            if "用户登录" in html:
                logging.error("会话已过期或未登录，无法获取页面数据")
                return None, None

            token, deptIdEnc = None, None

            # 依次尝试所有 token 正则表达式
            for pattern in self.token_patterns:
                match = pattern.search(html)
                if match:
                    token = match.group(1)
                    break

            # 依次尝试所有 deptIdEnc 正则表达式
            for pattern in self.deptIdEnc_patterns:
                match = pattern.search(html)
                if match:
                    deptIdEnc = match.group(1)
                    break

            if not token:
                logging.warning(f"在座位 {seat_num} 页面未能找到 token")
            if not deptIdEnc:
                logging.warning(f"在座位 {seat_num} 页面未能找到 deptIdEnc")
                # 最终手段：保存HTML以便定位字段变更
                try:
                    with open("page_source_for_debug.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    logging.critical("已将页面源码保存至 page_source_for_debug.html，请据此更新解析规则")
                except Exception:
                    pass

            return token, deptIdEnc

        except requests.RequestException as e:
            logging.error(f"获取座位 {seat_num} 页面数据时发生网络错误: {e}")
            return None, None

    def login(self, username, password):
        self.username = username
        self.password = password
        try:
            parm = {
                "fid": -1,
                "uname": AES_Encrypt(username),
                "password": AES_Encrypt(password),
                "refer": "http%3A%2F%2Foffice.chaoxing.com%2F",
                "t": True
            }
            response = self.requests.post(self.login_url, data=parm, verify=False, timeout=15)
            response.raise_for_status()
            obj = response.json()
            if obj.get('status', False):
                self._logged_in = True
                return (True, '')
            return (False, obj.get('msg2', '未知登录错误'))
        except (requests.RequestException, json.JSONDecodeError) as e:
            logging.error(f"登录请求异常: {e}")
            return (False, str(e))

    def _submit_single_seat(self, times, roomid, seat, action):
        """
        核心提交逻辑：
        1、每轮先动态获取 token、deptIdEnc
        2、遇到 ‘人数过多/请等待5分钟’ 固定等待 self.retry_wait_sec 再重试（并重新获取 token）
        3、‘未到开放时间’ 采用轻量抖动等待
        """
        for attempt in range(1, self.max_attempt + 1):
            logging.info(f"正在为座位 [{seat}] 进行第 {attempt}/{self.max_attempt} 次尝试...")
            token, deptIdEnc = self._get_page_data(roomid, seat)

            if not token or not deptIdEnc:
                logging.warning(f"获取座位 {seat} 的页面数据失败，将等待后重试")
                time.sleep(self.sleep_time * 2)
                continue

            day_str = self.get_target_date(action)
            parm = {
                "deptIdEnc": deptIdEnc,
                "roomId": str(roomid),
                "startTime": str(times[0]),
                "endTime": str(times[1]),
                "day": day_str,
                "seatNum": str(seat),
                "captcha": "",
                "token": token,
                "behaviorAnalysis": generate_behavior_analysis()
            }
            parm["enc"] = enc(parm)

            try:
                # 注意：为规避某些学校证书问题，这里保持 verify=False
                response = self.requests.post(self.submit_url, data=parm, verify=False, timeout=15)
                response.raise_for_status()
                # 兼容纯 JSON 与 HTML 包 JSON 的两种返回
                text = response.text or ""
                result = {}
                try:
                    result = response.json()
                except json.JSONDecodeError:
                    # 简易兜底：从文本里抽取常见键值
                    result = {
                        "success": ("成功" in text) or ('"code":0' in text),
                        "msg": text
                    }

                msg = str(result.get('msg', '无消息'))
                logging.info(f"座位 [{seat}] 响应: {msg[:200]}")

                if result.get("success", False):
                    logging.info(f"🎉 座位 [{seat}] 预约成功")
                    return True

                # 明确处理“人数过多/请等待5分钟后尝试”
                if ("人数过多" in msg) or ("请等待5分钟" in msg) or ("稍后再试" in msg):
                    logging.warning(f"座位 [{seat}] 当前人数过多，固定等待 {self.retry_wait_sec} 秒后重试")
                    time.sleep(self.retry_wait_sec)
                    # 继续 for 循环，下一轮会重新拉取 token、deptIdEnc
                    continue

                # 放号未到时间，轻量抖动重试
                if "未到开放时间" in msg:
                    time.sleep(self.sleep_time + random.uniform(0.1, 0.5))
                    continue

                # 其他明确失败，直接放弃该座位
                logging.error(f"座位 [{seat}] 预约失败，原因: {msg}，放弃该座位")
                return False

            except requests.RequestException as e:
                logging.error(f"提交座位 [{seat}] 预约时发生错误: {e}")

            time.sleep(self.sleep_time)

        logging.error(f"座位 [{seat}] 在 {self.max_attempt} 次尝试后仍未成功")
        return False

    def submit(self, times, roomid, seatid_list, action):
        """
        并发尝试多个 seatNum，并自动加入“去掉前导零”的容错版本
        例如 045 将同时尝试 ["045", "45"]，避免部分学校更新后的 seatNum 规范差异
        """
        if not isinstance(seatid_list, list):
            seatid_list = [seatid_list]

        # 自动扩展一个去前导 0 的版本，去重保持顺序
        expanded = []
        seen = set()
        for s in seatid_list:
            s = str(s).strip()
            cand = [s]
            s2 = s.lstrip("0")
            if s2 and s2 != s:
                cand.append(s2)
            for v in cand:
                if v not in seen:
                    expanded.append(v)
                    seen.add(v)

        seatid_list = expanded
        logging.info(f"开始并发预约，备选座位: {seatid_list}")

        with ThreadPoolExecutor(max_workers=len(seatid_list)) as executor:
            future_to_seat = {executor.submit(self._submit_single_seat, times, roomid, seat, action): seat for seat in seatid_list}
            for future in as_completed(future_to_seat):
                try:
                    if future.result():
                        ok_seat = future_to_seat[future]
                        logging.info(f"在备选座位中成功预约到 [{ok_seat}]，停止其他尝试")
                        return True
                except Exception as e:
                    logging.error(f"处理座位 [{future_to_seat[future]}] 的任务时发生异常: {e}")

        logging.error("所有备选座位均预约失败")
        return False
