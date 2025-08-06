from utils import AES_Encrypt, enc, generate_captcha_key, verify_param
import json
import requests
import re
import time
import logging
import datetime
from urllib3.exceptions import InsecureRequestWarning
from bs4 import BeautifulSoup


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
        """获取页面token和算法值 - 增强版本"""
        try:
            # 设置更真实的请求头
            page_headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Host": "office.chaoxing.com",
                "Pragma": "no-cache",
                "Referer": "https://office.chaoxing.com/",
                "Sec-Ch-Ua": '"Google Chrome";v="128", "Chromium";v="128", "Not.A/Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Linux"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            }
            
            response = self.requests.get(url=url, headers=page_headers, verify=False, timeout=15)
            response.raise_for_status()
            
            # 确保页面完全加载
            time.sleep(0.2)
            
            html = response.content.decode("utf-8", errors='ignore')
            
            # 保存HTML用于调试
            logging.debug(f"获取的页面长度: {len(html)}")
            
            # 获取token - 多种模式匹配
            token = ""
            token_patterns = [
                r"token\s*=\s*['\"]([^'\"]+)['\"]",
                r"token\s*:\s*['\"]([^'\"]+)['\"]",
                r"var\s+token\s*=\s*['\"]([^'\"]+)['\"]",
                r"let\s+token\s*=\s*['\"]([^'\"]+)['\"]",
                r"const\s+token\s*=\s*['\"]([^'\"]+)['\"]",
                r"'token':\s*['\"]([^'\"]+)['\"]",
                r'"token":\s*[\'"]([^\'"]+)[\'"]'
            ]
            
            for pattern in token_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                if matches:
                    token = matches[0]
                    logging.info(f"使用模式 {pattern} 找到token: {token}")
                    break
            
            if not token:
                logging.warning("未找到token，尝试从JavaScript中提取")
                # 尝试从更复杂的JavaScript结构中提取
                js_patterns = [
                    r'data-token\s*=\s*["\']([^"\']+)["\']',
                    r'token["\']?\s*:\s*["\']([^"\']+)["\']'
                ]
                for pattern in js_patterns:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    if matches:
                        token = matches[0]
                        break
            
            # 获取算法值
            algorithm_value = ""
            if require_value:
                # 使用BeautifulSoup更准确地解析HTML
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # 查找id为algorithm的元素
                    algorithm_elem = soup.find(attrs={'id': 'algorithm'})
                    if algorithm_elem:
                        algorithm_value = algorithm_elem.get('value', '')
                        logging.info(f"通过BeautifulSoup找到algorithm值: {algorithm_value}")
                    
                    # 如果没找到，尝试name属性
                    if not algorithm_value:
                        algorithm_elem = soup.find(attrs={'name': 'algorithm'})
                        if algorithm_elem:
                            algorithm_value = algorithm_elem.get('value', '')
                            logging.info(f"通过name属性找到algorithm值: {algorithm_value}")
                            
                except ImportError:
                    logging.warning("BeautifulSoup未安装，使用正则表达式")
                
                # 如果BeautifulSoup没找到，使用正则表达式
                if not algorithm_value:
                    algorithm_patterns = [
                        r'<input[^>]*\bid\s*=\s*["\']algorithm["\'][^>]*\bvalue\s*=\s*["\']([^"\']*)["\']',
                        r'<input[^>]*\bvalue\s*=\s*["\']([^"\']*)["\'][^>]*\bid\s*=\s*["\']algorithm["\']',
                        r'<input[^>]*\bname\s*=\s*["\']algorithm["\'][^>]*\bvalue\s*=\s*["\']([^"\']*)["\']',
                        r'var\s+algorithm\s*=\s*["\']([^"\']*)["\']',
                        r'let\s+algorithm\s*=\s*["\']([^"\']*)["\']',
                        r'const\s+algorithm\s*=\s*["\']([^"\']*)["\']',
                        r'algorithm\s*:\s*["\']([^"\']*)["\']',
                        r'"algorithm"\s*:\s*["\']([^"\']*)["\']'
                    ]
                    
                    for pattern in algorithm_patterns:
                        matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
                        if matches:
                            algorithm_value = matches[0]
                            logging.info(f"使用正则表达式找到algorithm值: {algorithm_value}")
                            break
                
                # 如果还是没找到，尝试从script标签中提取
                if not algorithm_value:
                    script_pattern = r'<script[^>]*>(.*?)</script>'
                    scripts = re.findall(script_pattern, html, re.IGNORECASE | re.DOTALL)
                    for script in scripts:
                        if 'algorithm' in script.lower():
                            algo_matches = re.findall(r'algorithm["\']?\s*[=:]\s*["\']([^"\']+)["\']', script, re.IGNORECASE)
                            if algo_matches:
                                algorithm_value = algo_matches[0]
                                logging.info(f"从script标签找到algorithm值: {algorithm_value}")
                                break
                
                if not algorithm_value:
                    logging.warning("无法从页面获取算法值，使用默认值")
                    algorithm_value = "%sd`~7^/>N4!Q#{'"
            
            logging.info(f"最终获取结果 - token: {token}, algorithm: {algorithm_value}")
            
            return token, algorithm_value
            
        except Exception as e:
            logging.error(f"获取页面token失败: {str(e)}")
            import traceback
            logging.error(f"详细错误信息: {traceback.format_exc()}")
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
        """提交预约请求 - 增强版本"""
        for seat in seatid:
            suc = False
            attempt_count = 0
            while not suc and attempt_count < self.max_attempt:
                try:
                    # 增加重试间隔，避免请求过于频繁
                    if attempt_count > 0:
                        time.sleep(min(self.sleep_time * attempt_count, 2.0))
                    
                    logging.info(f"第 {attempt_count + 1} 次尝试获取页面信息")
                    
                    token, value = self._get_page_token(
                        self.url.format(roomid, seat), require_value=True
                    )
                    
                    if not token:
                        logging.error("获取token失败，跳过此次尝试")
                        attempt_count += 1
                        continue
                    
                    logging.info(f"获取到 token: {token}")
                    logging.info(f"获取到 algorithm value: {value}")
                    
                    captcha = self.resolve_captcha() if self.enable_slider else ""
                    if self.enable_slider:
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
                        logging.info(f"座位 {seat} 预约成功!")
                        return suc
                    else:
                        logging.warning(f"座位 {seat} 第 {attempt_count + 1} 次尝试失败")
                        
                except Exception as e:
                    logging.error(f"座位 {seat} 第 {attempt_count + 1} 次尝试异常: {str(e)}")
                    import traceback
                    logging.debug(f"详细错误: {traceback.format_exc()}")
                    
                attempt_count += 1
                
        return suc

    def get_submit(self, url, times, token, roomid, seatid, captcha="", action=False, value=""):
        """发送预约提交请求 - 增强版本"""
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
        
        # 使用算法值生成enc参数
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
        
        # 尝试多种算法生成enc
        enc_generated = False
        
        # 方法1: 使用获取的algorithm值
        if not enc_generated:
            try:
                parm["enc"] = verify_param(encrypt_params, algorithm_value)
                logging.info(f"使用algorithm值生成enc: {parm['enc']}")
                enc_generated = True
            except Exception as e:
                logging.warning(f"使用algorithm值生成enc失败: {str(e)}")
        
        # 方法2: 使用默认算法值
        if not enc_generated:
            try:
                parm["enc"] = verify_param(encrypt_params, "%sd`~7^/>N4!Q#{'")
                logging.info(f"使用默认算法值生成enc: {parm['enc']}")
                enc_generated = True
            except Exception as e:
                logging.warning(f"使用默认算法值生成enc失败: {str(e)}")
        
        # 方法3: 使用旧版enc算法
        if not enc_generated:
            try:
                parm["enc"] = enc(encrypt_params)
                logging.info(f"使用旧版算法生成enc: {parm['enc']}")
                enc_generated = True
            except Exception as e:
                logging.error(f"所有enc生成方法都失败: {str(e)}")
                return False
        
        if not enc_generated:
            logging.error("无法生成enc参数，取消提交")
            return False
        
        try:
            # 设置提交请求头
            submit_headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Host": "office.chaoxing.com",
                "Origin": "https://office.chaoxing.com",
                "Pragma": "no-cache",
                "Referer": f"https://office.chaoxing.com/front/third/apps/seat/code?id={roomid}&seatNum={seatid}",
                "Sec-Ch-Ua": '"Google Chrome";v="128", "Chromium";v="128", "Not.A/Brand";v="24"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Linux"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "X-Requested-With": "XMLHttpRequest"
            }
            
            # 发送POST请求
            response = self.requests.post(
                url=url, 
                params=parm, 
                headers=submit_headers,
                verify=False, 
                timeout=15
            )
            response.raise_for_status()
            
            html = response.content.decode("utf-8")
            
            # 记录提交信息
            self.submit_msg.append(f"{times[0]}~{times[1]}: {html}")
            
            try:
                result = json.loads(html)
                logging.info(f"提交响应: {result}")
                
                # 检查响应状态
                if "success" in result:
                    if result["success"]:
                        logging.info("预约成功!")
                        return True
                    else:
                        msg = result.get("msg", "未知错误")
                        logging.warning(f"预约失败: {msg}")
                        return False
                elif "status" in result:
                    if result["status"]:
                        logging.info("预约成功!")
                        return True
                    else:
                        msg = result.get("msg", "未知错误")
                        logging.warning(f"预约失败: {msg}")
                        return False
                else:
                    logging.warning(f"意外的响应格式: {result}")
                    return False
                    
            except json.JSONDecodeError as e:
                logging.error(f"解析响应JSON失败: {str(e)}")
                logging.error(f"原始响应: {html}")
                return False
                
        except requests.RequestException as e:
            logging.error(f"提交请求网络错误: {str(e)}")
            return False
        except Exception as e:
            logging.error(f"提交请求异常: {str(e)}")
            import traceback
            logging.debug(f"详细错误: {traceback.format_exc()}")
            return False
