import json
import time
import argparse
import os
import logging
import datetime
import pytz
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from utils import reserve

# 修复时间处理函数 - 使用pytz正确处理时区
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

# 等待直到指定时间
def wait_until(target_time):
    """等待直到指定时间（北京时间）"""
    tz = pytz.timezone('Asia/Shanghai')
    while True:
        now = datetime.datetime.now(tz)
        current_time = now.strftime("%H:%M:%S")
        if current_time >= target_time:
            break
        time.sleep(0.5)

# 全局配置
SLEEPTIME = 0.1  # 减少等待时间
ENDTIME = "21:31:00"
ENABLE_SLIDER = True
MAX_ATTEMPT = 3  # 减少尝试次数
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
    # 使用覆盖的凭据（如果提供了）
    if action and username_override:
        username = username_override
    else:
        username = user_config["username"]
        
    if action and password_override:
        password = password_override
    else:
        password = user_config["password"]
    
    logging.info(f"----------- {username} 登录中 -----------")
    s = reserve(
        sleep_time=SLEEPTIME,
        max_attempt=MAX_ATTEMPT,
        enable_slider=ENABLE_SLIDER,
        reserve_next_day=RESERVE_TOMORROW
    )
    
    # 检查会话是否已存在
    if hasattr(s, '_logged_in') and s._logged_in:
        logging.info(f"用户 {username} 会话已存在，直接使用")
        return s
    
    s.get_login_status()
    login_result = s.login(username, password)
    
    if not login_result[0]:
        logging.error(f"登录失败: {login_result[1]}")
        return None
        
    s.requests.headers.update({'Host': 'office.chaoxing.com'})
    logging.info(f"用户 {username} 登录成功")
    
    # 登录成功后保存凭证以便重新登录
    s.username = username
    s.password = password
    
    return s


def login_all_users(users, usernames, passwords, action):
    """登录所有用户并返回会话缓存"""
    session_cache = {}
    
    for index, user in enumerate(users):
        username_override = None
        password_override = None
        
        if action:
            username_list = usernames.split(',') if usernames else []
            if index < len(username_list):
                username_override = username_list[index]
            else:
                logging.error(f"索引 {index} 的用户名缺失")
                continue
                
            password_list = passwords.split(',') if passwords else []
            if index < len(password_list):
                password_override = password_list[index]
            else:
                logging.error(f"索引 {index} 的密码缺失")
                continue
        
        # 登录用户
        session = login_user(user, username_override, password_override, action)
        if session:
            # 使用手机号作为缓存键
            cache_key = username_override if action else user["username"]
            session_cache[cache_key] = {
                "session": session,
                "config_username": user["username"]  # 保存配置中的用户名
            }
    
    return session_cache

def process_single_task(session, task, username, global_index, current_dayofweek, is_success):
    """处理单个预约任务"""
    # 在任务开始前检查会话有效性
    if not session.requests.cookies.get("JSESSIONID"):
        logging.warning("会话已过期，尝试重新登录")
        # 尝试重新登录
        login_result = session.login(session.username, session.password)
        if not login_result[0]:
            logging.error(f"重新登录失败: {login_result[1]}")
            return False
        else:
            logging.info("重新登录成功")
            session.requests.headers.update({'Host': 'office.chaoxing.com'})
    
    times = task["time"]
    roomid = task["roomid"]
    seatid = task["seatid"]
    daysofweek = task["daysofweek"]
    
    if isinstance(seatid, str):
        seatid = [seatid]
    
    if current_dayofweek not in daysofweek:
        logging.info(f"任务 {global_index}: 今天不预约")
        return False
    
    if is_success:
        logging.info(f"任务 {global_index} 已成功预约，跳过")
        return True
        
    logging.info(f"----------- {username} -- 任务 {global_index}: {times} -- {seatid} 尝试预约 -----------")
    try:
        suc = session.submit(times, roomid, seatid, True)
        if suc:
            logging.info(f"任务 {global_index} 预约成功!")
        return suc
    except Exception as e:
        # 添加更详细的错误信息
        logging.error(f"任务 {global_index} 异常: {str(e)}")
        return False

def process_user_tasks(session, user, current_dayofweek, success_list, start_index):
    """并行处理单个用户的所有预约任务"""
    task_results = []
    username = user["username"]
    
    # 使用线程池处理用户的所有任务
    with ThreadPoolExecutor(max_workers=len(user["tasks"])) as executor:
        futures = []
        for task_index, task in enumerate(user["tasks"]):
            global_index = start_index + task_index
            futures.append(executor.submit(
                process_single_task,
                session=session,
                task=task,
                username=username,
                global_index=global_index,
                current_dayofweek=current_dayofweek,
                is_success=success_list[global_index]
            ))
        
        # 收集结果 - 确保按原始顺序收集
        task_results = [future.result() for future in futures]
    
    return task_results

def reserve_all_tasks(session_cache, users, current_dayofweek, success_list):
    """并发预约所有用户的任务"""
    total_tasks = sum(len(user["tasks"]) for user in users)
    if not success_list:
        success_list = [False] * total_tasks
        
    # 计算每个用户的任务起始索引
    start_indices = []
    current_index = 0
    for user in users:
        start_indices.append(current_index)
        current_index += len(user["tasks"])
    
    # 使用线程池并发执行预约
    futures = []
    with ThreadPoolExecutor(max_workers=min(len(session_cache), 4)) as executor:  # 限制并发线程数
        for idx, user in enumerate(users):
            username = user["username"]
            
            # 查找会话 - 优先尝试使用配置用户名
            session_info = None
            for key in session_cache:
                if session_cache[key]["config_username"] == username:
                    session_info = session_cache[key]
                    break
            
            if not session_info:
                logging.warning(f"用户 {username} 无有效会话，跳过")
                # 标记该用户的所有任务为失败
                start_index = start_indices[idx]
                for i in range(len(user["tasks"])):
                    if start_index + i < len(success_list):
                        success_list[start_index + i] = False
                continue
                
            session = session_info["session"]
            start_index = start_indices[idx]
            future = executor.submit(
                process_user_tasks,
                session=session,
                user=user,
                current_dayofweek=current_dayofweek,
                success_list=success_list,
                start_index=start_index
            )
            futures.append(future)
    
    # 收集结果
    new_success_list = success_list.copy()
    for future in as_completed(futures):
        results = future.result()
        if results:
            # 找到对应的用户索引
            idx = futures.index(future)
            start_index = start_indices[idx]
            # 只更新当前用户的任务结果
            for i, result in enumerate(results):
                if start_index + i < len(new_success_list):
                    new_success_list[start_index + i] = result
    
    return new_success_list

def main(users, action=False):
    logging.info("程序启动")
    
    if action:
        logging.info("GitHub Actions 模式 - 启用精确时间控制")
        
        # 第一步：等待到登录时间
        login_time = "21:29:30"
        logging.info(f"等待到登录时间: {login_time}")
        wait_until(login_time)
        
        # 获取凭证
        usernames, passwords = get_user_credentials(action)
        
        # 登录所有用户
        logging.info("开始账号登录流程")
        session_cache = login_all_users(users, usernames, passwords, action)
        logging.info(f"登录完成，共 {len(session_cache)} 个用户登录成功")
        
        # 第二步：等待到预约时间
        reserve_time = "21:30:00"
        logging.info(f"等待到预约时间: {reserve_time}")
        wait_until(reserve_time)
        logging.info("开始预约流程")
        
        current_dayofweek = get_current_dayofweek(action)
        total_tasks = sum(len(user["tasks"]) for user in users)
        success_list = [False] * total_tasks

        # 只执行一次预约流程
        success_list = reserve_all_tasks(
            session_cache=session_cache,
            users=users,
            current_dayofweek=current_dayofweek,
            success_list=success_list
        )

        # 检查结果
        if all(success_list):
            logging.info("所有任务预约成功！")
        else:
            # 正确统计失败任务
            success_count = sum(1 for success in success_list if success)
            failed_count = len(success_list) - success_count
            logging.info(f"预约完成，成功: {success_count}, 失败: {failed_count}")
            
            # 记录失败任务详情
            for i, user in enumerate(users):
                start_index = sum(len(u["tasks"]) for u in users[:i])
                for j, task in enumerate(user["tasks"]):
                    idx = start_index + j
                    if idx < len(success_list) and not success_list[idx]:
                        logging.warning(f"用户 {user['username']} 任务 {j} 预约失败")

    else:
        # 非GitHub Actions模式 - 立即执行
        logging.info("本地模式 - 立即执行")
        usernames, passwords = "", ""
        session_cache = login_all_users(users, usernames, passwords, action)
        current_dayofweek = get_current_dayofweek(action)
        total_tasks = sum(len(user["tasks"]) for user in users)
        success_list = [False] * total_tasks
        success_list = reserve_all_tasks(session_cache, users, current_dayofweek, success_list)
        logging.info(f"预约结果: {success_list}")

def debug(users, action=False):
    logging.info(f"调试模式启动")
    logging.info(f"全局设置: SLEEPTIME={SLEEPTIME}, ENDTIME={ENDTIME}, ENABLE_SLIDER={ENABLE_SLIDER}, RESERVE_TOMORROW={RESERVE_TOMORROW}")
    
    usernames, passwords = "", ""
    if action:
        usernames, passwords = get_user_credentials(action)
    
    session_cache = login_all_users(users, usernames, passwords, action)
    current_dayofweek = get_current_dayofweek(action)
    
    for username, session in session_cache.items():
        user = next((u for u in users if u["username"] == username), None)
        if not user:
            continue
            
        # 并行处理用户的所有任务
        with ThreadPoolExecutor(max_workers=len(user["tasks"])) as executor:
            futures = []
            for task_index, task in enumerate(user["tasks"]):
                futures.append(executor.submit(
                    process_single_task,
                    session=session["session"],
                    task=task,
                    username=username,
                    global_index=task_index+1,
                    current_dayofweek=current_dayofweek,
                    is_success=False
                ))
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    logging.info(f"任务完成，结果: {result}")
                except Exception as e:
                    logging.error(f"任务异常: {str(e)}")

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
