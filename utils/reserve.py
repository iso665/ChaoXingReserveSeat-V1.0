from .encrypt import AES_Encrypt, enc, generate_behavior_analysis
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

# 禁用不安全的请求警告
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

class reserve:
    def __init__(self, sleep_time=0.2, max_attempt=50, enable_slider=False, reserve_next_day=False):
        self.login_page = "https://passport2.chaoxing.com/mlogin?loginType=1&newversion=true&fid="
        self.seat_code_url = "https://office.chaoxing.com/front/third/apps/seat/code?id={}&seatNum={}"
        self.submit_url = "https://office.chaoxing.com/data/apps/seat/submit"
        self.login_url = "https://passport2.chaoxing.com/fanyalogin"
        
        self.requests = requests.session()
        self.requests.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        })
        
        # 提取页面关键信息的正则表达式
        self.token_pattern = re.compile(r"token\s*=\s*'([^']+)'")
        self.deptIdEnc_pattern = re.compile(r'deptIdEnc:"([^"]+)"')

        # 脚本配置
        self.sleep_time = sleep_time
        self.max_attempt = max_attempt
        self.enable_slider = enable_slider
        self.reserve_next_day = reserve_next_day
        self.beijing_tz = pytz.timezone('Asia/Shanghai')

        # 缓存数据
        self.username = None
        self.password = None
        self._logged_in = False

    def get_target_date(self, action):
        """根据是否在Actions中运行，获取正确的目标预约日期"""
        now = datetime.datetime.now(self.beijing_tz)
        # 在Actions中，由于时区差异，通常需要预约逻辑上的“明天”
        delta_days = 1 if action or self.reserve_next_day else 0
        target_date = now + datetime.timedelta(days=delta_days)
        return target_date.strftime("%Y-%m-%d")

    def _get_page_data(self, roomid, seat_num):
        """从选座页面获取 token 和 deptIdEnc"""
        url = self.seat_code_url.format(roomid, seat_num)
        try:
            response = self.requests.get(url, verify=False, timeout=10)
            response.raise_for_status()
            html = response.text

            if "用户登录" in html:
                logging.error("会话已过期或未登录，无法获取页面数据。")
                return None, None

            token_match = self.token_pattern.search(html)
            deptIdEnc_match = self.deptIdEnc_pattern.search(html)

            token = token_match.group(1) if token_match else None
            deptIdEnc = deptIdEnc_match.group(1) if deptIdEnc_match else None

            if not token:
                logging.warning(f"在座位 {seat_num} 页面未能找到 token。")
            if not deptIdEnc:
                logging.warning(f"在座位 {seat_num} 页面未能找到 deptIdEnc。")

            return token, deptIdEnc

        except requests.RequestException as e:
            logging.error(f"获取座位 {seat_num} 页面数据时发生网络错误: {e}")
            return None, None

    def login(self, username, password):
        """用户登录"""
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
            else:
                return (False, obj.get('msg2', '未知登录错误'))
        except requests.RequestException as e:
            logging.error(f"登录请求异常: {e}")
            return (False, str(e))
        except json.JSONDecodeError:
            logging.error("登录响应不是有效的JSON格式。")
            return (False, "服务器响应格式错误")

    def _submit_single_seat(self, times, roomid, seat, action):
        """为单个座位尝试提交预约请求"""
        for attempt in range(1, self.max_attempt + 1):
            logging.info(f"正在为座位 [{seat}] 进行第 {attempt}/{self.max_attempt} 次尝试...")
            
            token, deptIdEnc = self._get_page_data(roomid, seat)
            if not token or not deptIdEnc:
                logging.warning(f"获取座位 {seat} 的页面数据失败，将等待后重试。")
                time.sleep(self.sleep_time)
                continue

            # 准备请求参数
            day_str = self.get_target_date(action)
            parm = {
                "deptIdEnc": deptIdEnc,
                "roomId": str(roomid),
                "startTime": str(times[0]),
                "endTime": str(times[1]),
                "day": day_str,
                "seatNum": str(seat),
                "captcha": "", # 滑块验证码（如果需要）
                "token": token,
                "behaviorAnalysis": generate_behavior_analysis() # 生成模拟行为数据
            }
            
            # 生成加密签名
            parm["enc"] = enc(parm)
            
            try:
                response = self.requests.post(self.submit_url, data=parm, verify=True, timeout=15)
                response.raise_for_status()
                result = response.json()
                
                logging.info(f"座位 [{seat}] 响应: {result.get('msg', '无消息')}")

                if result.get("success", False):
                    logging.info(f"🎉 🎉 🎉 座位 [{seat}] 预约成功!")
                    return True
                else:
                    # 如果是时间未到，则短暂等待后重试
                    if "未到开放时间" in result.get('msg', ''):
                        time.sleep(self.sleep_time)
                    # 如果是人数过多，说明接口已开放，可以稍微增加等待
                    elif "人数过多" in result.get('msg', ''):
                        time.sleep(self.sleep_time + 0.3)
                    else:
                        # 其他错误，可能是座位被占，直接放弃此座位
                        logging.error(f"座位 [{seat}] 预约失败，原因: {result.get('msg', '未知')}")
                        return False

            except requests.RequestException as e:
                logging.error(f"提交座位 [{seat}] 预约时发生网络错误: {e}")
            except json.JSONDecodeError:
                logging.error(f"解析座位 [{seat}] 的预约响应时失败。")
            
            time.sleep(self.sleep_time) # 每次尝试后都短暂等待

        logging.error(f"座位 [{seat}] 在 {self.max_attempt} 次尝试后仍未成功。")
        return False

    def submit(self, times, roomid, seatid_list, action):
        """提交预约请求，支持并发尝试多个座位"""
        if not isinstance(seatid_list, list):
            seatid_list = [seatid_list]
        
        logging.info(f"开始并发预约，备选座位: {seatid_list}")
        
        # 使用线程池并发地为每个备选座位提交请求
        with ThreadPoolExecutor(max_workers=len(seatid_list)) as executor:
            # 提交所有任务
            future_to_seat = {executor.submit(self._submit_single_seat, times, roomid, seat, action): seat for seat in seatid_list}
            
            for future in as_completed(future_to_seat):
                seat = future_to_seat[future]
                try:
                    # 只要有一个任务成功，就立即返回成功
                    if future.result():
                        logging.info(f"在备选座位中成功预约到 [{seat}]，停止其他尝试。")
                        # 这里可以添加逻辑来取消其他正在运行的future，但对于抢座场景，让它们完成也无妨
                        return True
                except Exception as e:
                    logging.error(f"处理座位 [{seat}] 的预约任务时发生异常: {e}")
        
        logging.error("所有备选座位均预约失败。")
        return False
