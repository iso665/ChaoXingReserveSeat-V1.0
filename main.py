import json
import time
import argparse
import os
import logging
import datetime
import pytz
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from utils import reserve

# 修复时间计算逻辑
def get_current_time(action):
    """获取当前北京时间"""
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.datetime.now(tz)
    return now.strftime("%H:%M:%S")

def get_current_dayofweek(action):
    """获取当前星期几（英文）"""
    tz = pytz.timezone('Asia/Shanghai')
    now = datetime.datetime.now(tz)
    return now.strftime("%A")

# 全局配置
SLEEPTIME = 0.2
ENDTIME = "21:31:00"
ENABLE_SLIDER = True
MAX_ATTEMPT = 4  # 增加尝试次数
RESERVE_TOMORROW = True

def get_user_credentials(action):
    """从环境变量获取凭证"""
    if action:
        try:
            usernames = os.environ['USERNAMES']
            passwords = os.environ['PASSWORDS']
            return usernames, passwords
        except KeyError:
            logging.error("Missing USERNAMES or PASSWORDS in environment variables")
            return "", ""
    return "", ""

def login_user(user_config, username_override, password_override, action):
    """处理单个用户的登录"""
    username = user_config["username"]
    password = user_config["password"]
    
    # 使用覆盖的凭据（如果提供了）
    if action and username_override:
        username = username_override
    if action and password_override:
        password = password_override
        
    logging.info(f"----------- {username} login -----------")
    s = reserve(
        sleep_time=SLEEPTIME,
        max_attempt=MAX_ATTEMPT,
        enable_slider=ENABLE_SLIDER,
        reserve_next_day=RESERVE_TOMORROW
    )
    s.get_login_status()
    login_result = s.login(username, password)
    
    if not login_result[0]:
        logging.error(f"登录失败: {login_result[1]}")
        return None
        
    s.requests.headers.update({'Host': 'office.chaoxing.com'})
    return s

def reserve_seats(session, username, tasks, current_dayofweek, success_list, task_index):
    """处理单个用户的预约任务"""
    for task in tasks:
        times = task["time"]
        roomid = task["roomid"]
        seatid = task["seatid"]
        daysofweek = task["daysofweek"]
        
        # 确保seatid是列表
        if isinstance(seatid, str):
            seatid = [seatid]
        
        if current_dayofweek not in daysofweek:
            logging.info(f"Task {task_index}: Today not set to reserve")
            task_index += 1
            continue
            
        if not success_list[task_index]:
            logging.info(f"----------- {username} -- {times} -- {seatid} try -----------")
            try:
                suc = session.submit(times, roomid, seatid, True)
                success_list[task_index] = suc
                if suc:
                    logging.info(f"预约成功! 座位: {seatid}")
            except Exception as e:
                logging.error(f"预约异常: {str(e)}")
                success_list[task_index] = False
                
        task_index += 1
        
    return task_index, success_list

def login_and_reserve(users, usernames, passwords, action, success_list=None):
    logging.info(f"Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_TOMORROW: {RESERVE_TOMORROW}")
    
    if action and (len(usernames.split(",")) != len(users) or len(passwords.split(",")) != len(users)):
        raise Exception("用户数应与配置匹配")
    
    if success_list is None:
        total_tasks = sum(len(user["tasks"]) for user in users)
        success_list = [False] * total_tasks
        logging.info(f"初始化任务列表: {total_tasks} 个任务")
        
    current_dayofweek = get_current_dayofweek(action)
    session_cache = {}
    task_index = 0
    
    for index, user in enumerate(users):
        username_override = None
        password_override = None
        
        if action:
            username_list = usernames.split(',')
            password_list = passwords.split(',')
            
            if index < len(username_list):
                username_override = username_list[index]
            else:
                logging.error(f"索引 {index} 的用户名缺失")
                continue
                
            if index < len(password_list):
                password_override = password_list[index]
            else:
                logging.error(f"索引 {index} 的密码缺失")
                continue
        
        # 确定缓存键
        cache_key = username_override or user["username"]
        
        # 登录用户
        if cache_key not in session_cache:
            session = login_user(user, username_override, password_override, action)
            if not session:
                logging.error(f"用户 {cache_key} 登录失败，跳过任务")
                # 跳过该用户的所有任务
                task_index += len(user["tasks"])
                continue
            session_cache[cache_key] = session
        else:
            session = session_cache[cache_key]
            
        # 预约座位
        task_index, success_list = reserve_seats(
            session=session,
            username=cache_key,
            tasks=user["tasks"],
            current_dayofweek=current_dayofweek,
            success_list=success_list,
            task_index=task_index
        )
            
    logging.info(f"任务完成状态: {success_list}")
    return success_list

def wait_until(target_time, action):
    """精确等待到目标时间（北京时间）"""
    logging.info(f"等待目标时间: {target_time}")
    target_h, target_m, target_s = map(int, target_time.split(':'))
    
    tz = pytz.timezone('Asia/Shanghai')
    
    while True:
        now = datetime.datetime.now(tz)
        current_ts = now.hour * 3600 + now.minute * 60 + now.second
        
        target_ts = target_h * 3600 + target_m * 60 + target_s
        
        if current_ts >= target_ts:
            logging.info(f"达到目标时间: {now.strftime('%H:%M:%S')}")
            break
            
        # 精确等待
        time_diff = target_ts - current_ts
        if time_diff > 1:
            time.sleep(0.1)  # 每秒检查10次
        else:
            time.sleep(0.01)  # 接近目标时间时更频繁检查

def main(users, action=False):
    logging.info("程序启动")
    
    if action:
        logging.info("GitHub Actions 模式 - 启用精确时间控制")
        
        # 第一步：等待到北京时间 09:44:00
        wait_until("09:44:00", action)
        logging.info("开始账号登录流程")
        
        # 获取凭证
        usernames, passwords = get_user_credentials(action)
        
        # 登录账号
        success_list = login_and_reserve(users, usernames, passwords, action, None)
        logging.info("账号登录完成")
        
        # 第二步：等待到北京时间 09:45:00
        wait_until("09:45:00", action)
        logging.info("开始预约流程")
        
        attempt_times = 0
        total_tasks = sum(len(user["tasks"]) for user in users)
        
        while True:
            attempt_times += 1
            current_time = get_current_time(action)
            
            # 检查是否超过结束时间
            if current_time >= ENDTIME:
                logging.info(f"已超过结束时间 {ENDTIME}，停止尝试")
                break
                
            success_list = login_and_reserve(users, usernames, passwords, action, success_list)
            logging.info(f"尝试 #{attempt_times}, 当前时间 {current_time}, 成功状态: {success_list}")
            
            # 检查是否所有任务都已完成
            if all(success_list):
                logging.info("所有任务预约成功!")
                return
                
            # 检查最大尝试次数
            if attempt_times >= MAX_ATTEMPT:
                logging.info(f"达到最大尝试次数 {MAX_ATTEMPT}")
                break
                
            time.sleep(1)  # 每次尝试间隔1秒
    else:
        # 非GitHub Actions模式
        logging.info("本地模式 - 立即执行")
        success_list = login_and_reserve(users, "", "", action, None)
        logging.info(f"预约结果: {success_list}")

def debug(users, action=False):
    logging.info(f"调试模式启动")
    logging.info(f"全局设置: SLEEPTIME={SLEEPTIME}, ENDTIME={ENDTIME}, ENABLE_SLIDER={ENABLE_SLIDER}, RESERVE_TOMORROW={RESERVE_TOMORROW}")
    
    usernames, passwords = "", ""
    if action:
        usernames, passwords = get_user_credentials(action)
    
    current_dayofweek = get_current_dayofweek(action)
    session_cache = {}
    
    for index, user in enumerate(users):
        username_override = None
        password_override = None
        
        if action:
            username_list = usernames.split(',')
            password_list = passwords.split(',')
            
            if index < len(username_list):
                username_override = username_list[index]
            if index < len(password_list):
                password_override = password_list[index]
        
        # 确定缓存键
        cache_key = username_override or user["username"]
        
        # 登录用户
        if cache_key not in session_cache:
            session = login_user(user, username_override, password_override, action)
            if not session:
                logging.error(f"用户 {cache_key} 登录失败，跳过任务")
                continue
            session_cache[cache_key] = session
        else:
            session = session_cache[cache_key]
            
        for task_index, task in enumerate(user["tasks"]):
            times = task["time"]
            roomid = task["roomid"]
            seatid = task["seatid"]
            daysofweek = task["daysofweek"]
            
            # 确保seatid是列表
            if isinstance(seatid, str):
                seatid = [seatid]
            
            if current_dayofweek not in daysofweek:
                logging.info(f"任务 {task_index+1}: 今天不预约")
                continue
            
            logging.info(f"----------- {cache_key} -- 任务 {task_index+1}: {times} -- {seatid} 尝试 -----------")
            try:
                suc = session.submit(times, roomid, seatid, action)
                if suc:
                    logging.info(f"任务 {task_index+1} 预约成功!")
                else:
                    logging.warning(f"任务 {task_index+1} 预约失败")
            except Exception as e:
                logging.error(f"任务 {task_index+1} 异常: {str(e)}")

def get_roomid(args1, args2):
    username = input("用户名：")
    password = input("密码：")
    s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_TOMORROW)
    s.get_login_status()
    login_result = s.login(username=username, password=password)
    if not login_result[0]:
        print(f"登录失败: {login_result[1]}")
        return
    s.requests.headers.update({'Host': 'office.chaoxing.com'})
    encode = input("deptldEnc：")
    s.roomid(encode)

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    parser = argparse.ArgumentParser(prog='超星座位自动预约')
    parser.add_argument('-u','--user', default=config_path, help='用户配置文件')
    parser.add_argument('-m','--method', default="reserve" ,choices=["reserve", "debug", "room"], help='运行模式')
    parser.add_argument('-a','--action', action="store_true", help='启用GitHub Actions模式')
    args = parser.parse_args()
    
    func_dict = {
        "reserve": main,
        "debug": debug,
        "room": get_roomid
    }
    
    try:
        with open(args.user, "r") as data:
            config = json.load(data)
            usersdata = config.get("reserve", [])
            logging.info(f"加载 {len(usersdata)} 个用户配置")
    except Exception as e:
        logging.error(f"配置文件加载失败: {str(e)}")
        exit(1)
    
    func_dict[args.method](usersdata, args.action)
