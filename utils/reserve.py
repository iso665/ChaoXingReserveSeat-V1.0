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



class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=3, enable_slider=False, reserve_next_day=False, retry_wait_sec=300):
        """
        retry_wait_sec：遇到“当前人数过多，请等待5分钟后尝试”提示时的固定等待秒数
        """
        # 登录接口：大多仍是 passport2，如学校切到 passport 请按抓包改
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"

        # 新版座位页面，用于获取 token 与 deptIdEnc（fidEnc）
        # 需要 fidEnc，如果未提供则回退到旧版
        self.seat_select_url = "https://office.chaoxing.com/front/apps/seat/select?id={room}&day={day}&seatNum={seat}&backLevel=2&fidEnc={fid}"

        # 旧版座位页面（回退用）
        self.seat_code_url_legacy = "https://office.chaoxing.com/front/third/apps/seat/code?id={room}&seatNum={seat}"

        # 预约提交接口（与抓包一致）
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"

        # 可选：房间信息接口与验证码类型接口，当前逻辑不必调用，仅保留以便后续扩展
        self.room_info_url = "https://office.chaoxing.com/data/apps/seat/room/info"
        self.captcha_type_url = "https://office.chaoxing.com/data/apps/seat/captcha/type"

        # HTTP 会话
        self.requests = requests.session()
        self.requests.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "X-Requested-With": "XMLHttpRequest"
        })

        # 抽取 token 与 deptIdEnc/fidEnc 的正则
        self.token_patterns = [
            re.compile(r"token\s*=\s*['\"]([^'\"]+)['\"]"),
            re.compile(r'name="token"\s*content="([^"]+)"'),
            re.compile(r'"token"\s*:\s*"([^"]+)"'),
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

        # 可通过环境变量传入 fidEnc（强烈建议在 GitHub Actions 的 Secrets 中设置）
        # 变量名：FID_ENC，没有则在页面里解析
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

    # === 页面抓取与字段解析 ===
    def _get_page_data(self, roomid, seat_num, day, fid_enc_hint=""):
        """
        优先走新版 select 页面获取 token 与 deptIdEnc
        若没有 fidEnc 可用则回退到旧版 third/code 页面
        """
        # 1) 新版路径，需 fidEnc
        fid_use = (fid_enc_hint or self.default_fid_enc).strip()
        if fid_use:
            url = self.seat_select_url.format(room=roomid, day=day, seat=seat_num, fid=fid_use)
            try:
                resp = self.requests.get(url, verify=False, timeout=15)
                resp.raise_for_status()
                html = resp.text

                token, deptIdEnc = self._extract_token_dept(html)
                # 新版里 deptIdEnc 等于 fidEnc，若未命中正则则直接用 fid_use
                if not deptIdEnc:
                    deptIdEnc = fid_use
                return token, deptIdEnc
            except requests.RequestException as e:
                logging.warning(f"新版 select 页面获取失败，将回退旧版，原因: {e}")

        # 2) 旧版回退路径
        url_old = self.seat_code_url_legacy.format(room=roomid, seat=seat_num)
        try:
            resp = self.requests.get(url_old, verify=False, timeout=15)
            resp.raise_for_status()
            html = resp.text
            token, deptIdEnc = self._extract_token_dept(html)
            if not token or not deptIdEnc:
                # 保存源码便于定位字段变更
                try:
                    with open("page_source_for_debug.html", "w", encoding="utf-8") as f:
                        f.write(html)
                    logging.critical("未能解析 token/deptIdEnc，已保存 page_source_for_debug.html，请据此更新解析规则")
                except Exception:
                    pass
            return token, deptIdEnc
        except requests.RequestException as e:
            logging.error(f"旧版 code 页面获取失败: {e}")
            return None, None

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
            parm = {
                "fid": -1,
                "uname": AES_Encrypt(username),
                "password": AES_Encrypt(password),
                "refer": "http%3A%2F%2Foffice.chaoxing.com%2F",
                "t": True
            }
            r = self.requests.post(self.login_url, data=parm, verify=False, timeout=15)
            r.raise_for_status()
            obj = r.json()
            if obj.get("status", False):
                self._logged_in = True
                return (True, "")
            return (False, obj.get("msg2", "未知登录错误"))
        except (requests.RequestException, json.JSONDecodeError) as e:
            logging.error(f"登录请求异常: {e}")
            return (False, str(e))

    # === 提交单座位 ===
    def _submit_single_seat(self, times, roomid, seat, action):
        """
        每轮：
        先抓页面拿 token/deptIdEnc → 组织参数 → 提交
        遇到“人数过多/请等待5分钟”固定等待 self.retry_wait_sec 再重试（并重新抓 token）
        “未到开放时间”轻量抖动
        """
        day_str = self.get_target_date(action)
        for attempt in range(1, self.max_attempt + 1):
            logging.info(f"座位[{seat}] 第 {attempt}/{self.max_attempt} 次尝试")
            token, deptIdEnc = self._get_page_data(roomid, seat, day_str)

            if not token or not deptIdEnc:
                logging.warning(f"座位[{seat}] 获取 token/deptIdEnc 失败，稍后重试")
                time.sleep(self.sleep_time * 2)
                continue

            parm = {
                "deptIdEnc": deptIdEnc,
                "roomId": str(roomid),
                "startTime": str(times[0]),
                "endTime": str(times[1]),
                "day": day_str,
                "seatNum": str(seat),
                "captcha": "",
                "token": token,
                "behaviorAnalysis": generate_behavior_analysis(),
            }
            parm["enc"] = enc(parm)

            try:
                resp = self.requests.post(self.submit_url, data=parm, verify=False, timeout=15)
                resp.raise_for_status()

                text = resp.text or ""
                try:
                    result = resp.json()
                    success = bool(result.get("success", False))
                    msg = str(result.get("msg", ""))
                except json.JSONDecodeError:
                    success = ("成功" in text) or ('"code":0' in text)
                    msg = text

                logging.info(f"座位[{seat}] 响应: {msg[:200]}")

                if success:
                    logging.info(f"🎉 座位[{seat}] 预约成功")
                    return True

                if ("人数过多" in msg) or ("请等待5分钟" in msg) or ("稍后再试" in msg):
                    logging.warning(f"座位[{seat}] 当前人数过多，等待 {self.retry_wait_sec} 秒后重试")
                    time.sleep(self.retry_wait_sec)
                    continue

                if "未到开放时间" in msg:
                    time.sleep(self.sleep_time + random.uniform(0.1, 0.5))
                    continue

                logging.error(f"座位[{seat}] 明确失败，原因：{msg}，放弃该座位")
                return False

            except requests.RequestException as e:
                logging.error(f"座位[{seat}] 提交时网络异常: {e}")

            time.sleep(self.sleep_time)

        logging.error(f"座位[{seat}] 在 {self.max_attempt} 次尝试后仍未成功")
        return False

    # === 并发提交多座位，自动加“去前导 0”候选 ===
    def submit(self, times, roomid, seatid_list, action):
        if not isinstance(seatid_list, list):
            seatid_list = [seatid_list]

        expanded, seen = [], set()
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

        logging.info(f"开始并发预约，备选座位: {expanded}")

        with ThreadPoolExecutor(max_workers=len(expanded)) as ex:
            future_to_seat = {ex.submit(self._submit_single_seat, times, roomid, seat, action): seat for seat in expanded}
            for fut in as_completed(future_to_seat):
                try:
                    if fut.result():
                        ok = future_to_seat[fut]
                        logging.info(f"已抢到座位[{ok}]，停止其他尝试")
                        return True
                except Exception as e:
                    logging.error(f"处理座位[{future_to_seat[fut]}] 时异常: {e}")

        logging.error("所有备选座位均预约失败")
        return False
