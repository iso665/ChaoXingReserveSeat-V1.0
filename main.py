import json
import time
import argparse
import os
import logging
import datetime
import calendar
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from utils import reserve, get_user_credentials

# 移除pytz依赖 - 使用简单的时间偏移处理北京时间
def get_current_time(action):
    """获取当前北京时间"""
    # 北京时间 = UTC + 8小时
    beijing_time = time.time() + 8 * 3600
    return time.strftime("%H:%M:%S", time.gmtime(beijing_time))

def get_current_dayofweek(action):
    """获取当前星期几（英文）"""
    # 北京时间 = UTC + 8小时
    beijing_time = time.time() + 8 * 3600
    return time.strftime("%A", time.gmtime(beijing_time))

# 等待直到指定时间
def wait_until(target_time):
    """等待直到指定时间（北京时间）"""
    h, m, s = map(int, target_time.split(':'))
    
    while True:
        # 获取当前北京时间
        beijing_time = time.time() + 8 * 3600
        current_struct = time.gmtime(beijing_time)
        current_time = time.strftime("%H:%M:%S", current_struct)
        
        # 检查是否到达目标时间
        current_h, current_m, current_s = current_struct.tm_hour, current_struct.tm_min, current_struct.tm_sec
        current_total_seconds = current_h * 3600 + current_m * 60 + current_s
        target_total_seconds = h * 3600 + m * 60 + s
        
        if current_total_seconds >= target_total_seconds:
            logging.info(f"到达目标时间 {target_time}（北京时间），开始执行")
            break
        
        time.sleep(0.5)

# 全局配置
SLEEPTIME = 0.1  # 减少等待时间
ENDTIME = "22:01:00"
ENABLE_SLIDER = False
MAX_ATTEMPT = 3  # 减少尝试次数
RESERVE_TOMORROW = True

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
    
    # 处理旧格式配置（直接用户列表）和新格式配置（带tasks的用户）
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
        
        # 兼容旧格式配置
        if "tasks" not in user:
            # 旧格式：直接包含预约信息
            user_config = {
                "username": user.get("username", ""),
                "password": user.get("password", ""),
                "tasks": [user]  # 将整个用户配置作为单个任务
            }
        else:
            # 新格式：包含tasks数组
            user_config = user
        
        # 登录用户
        session = login_user(user_config, username_override, password_override, action)
        if session:
            # 使用手机号作为缓存键
            cache_key = username_override if action else user_config["username"]
            session_cache[cache_key] = {
                "session": session,
                "config_username": user_config["username"]  # 保存配置中的用户名
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
    
    # 兼容旧格式和新格式
    times = task.get("time", task.get("times", []))
    roomid = task.get("roomid", task.get("roomId", ""))
    seatid = task.get("seatid", task.get("seatId", []))
    daysofweek = task.get("daysofweek", task.get("daysOfWeek", []))
    
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
        suc = session.submit(times, roomid, seatid, action)
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
    username = user.get("username", "")
    
    # 获取用户的任务列表
    if "tasks" in user:
        tasks = user["tasks"]
    else:
        # 兼容旧格式：整个用户配置就是一个任务
        tasks = [user]
    
    # 使用线程池处理用户的所有任务
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = []
        for task_index, task in enumerate(tasks):
            global_index = start_index + task_index
            futures.append(executor.submit(
                process_single_task,
                session=session,
                task=task,
                username=username,
                global_index=global_index,
                current_dayofweek=current_dayofweek,
                is_success=success_list[global_index] if global_index < len(success_list) else False
            ))
        
        # 收集结果 - 确保按原始顺序收集
        task_results = [future.result() for future in futures]
    
    return task_results

def reserve_all_tasks(session_cache, users, current_dayofweek, success_list):
    """并发预约所有用户的任务"""
    # 计算总任务数（兼容新旧格式）
    total_tasks = 0
    for user in users:
        if "tasks" in user:
            total_tasks += len(user["tasks"])
        else:
            total_tasks += 1  # 旧格式每个用户是一个任务
    
    if not success_list:
        success_list = [False] * total_tasks
        
    # 计算每个用户的任务起始索引
    start_indices = []
    current_index = 0
    for user in users:
        start_indices.append(current_index)
        if "tasks" in user:
            current_index += len(user["tasks"])
        else:
            current_index += 1
    
    # 使用线程池并发执行预约
    futures = []
    with ThreadPoolExecutor(max_workers=min(len(session_cache), 4)) as executor:  # 限制并发线程数
        for idx, user in enumerate(users):
            username = user.get("username", "")
            
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
                task_count = len(user.get("tasks", [user]))
                for i in range(task_count):
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
            futures.append((future, idx))
    
    # 收集结果
    new_success_list = success_list.copy()
    for future, user_idx in futures:
        try:
            results = future.result()
            if results:
                start_index = start_indices[user_idx]
                # 只更新当前用户的任务结果
                for i, result in enumerate(results):
                    if start_index + i < len(new_success_list):
                        new_success_list[start_index + i] = result
        except Exception as e:
            logging.error(f"用户 {user_idx} 的任务处理异常: {str(e)}")
    
    return new_success_list

def main(users, action=False):
    logging.info("程序启动")
    
    if action:
        logging.info("GitHub Actions 模式 - 启用精确时间控制")
        
        # 第一步：等待到登录时间
        login_time = "21:50:00"
        logging.info(f"等待到登录时间: {login_time}")
        wait_until(login_time)
        
        # 获取凭证
        usernames, passwords = get_user_credentials(action)
        
        # 登录所有用户
        logging.info("开始账号登录流程")
        session_cache = login_all_users(users, usernames, passwords, action)
        logging.info(f"登录完成，共 {len(session_cache)} 个用户登录成功")
        
        # 第二步：等待到预约时间
        reserve_time = "22:00:00"
        logging.info(f"等待到预约时间: {reserve_time}")
        wait_until(reserve_time)
        logging.info("开始预约流程")
        
        current_dayofweek = get_current_dayofweek(action)
        
        # 计算总任务数
        total_tasks = 0
        for user in users:
            if "tasks" in user:
                total_tasks += len(user["tasks"])
            else:
                total_tasks += 1
        
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
            task_idx = 0
            for i, user in enumerate(users):
                user_tasks = user.get("tasks", [user])
                for j, task in enumerate(user_tasks):
                    if task_idx < len(success_list) and not success_list[task_idx]:
                        logging.warning(f"用户 {user.get('username', '')} 任务 {j} 预约失败")
                    task_idx += 1

    else:
        # 非GitHub Actions模式 - 立即执行
        logging.info("本地模式 - 立即执行")
        usernames, passwords = get_user_credentials(action)
        session_cache = login_all_users(users, usernames, passwords, action)
        current_dayofweek = get_current_dayofweek(action)
        
        # 计算总任务数
        total_tasks = 0
        for user in users:
            if "tasks" in user:
                total_tasks += len(user["tasks"])
            else:
                total_tasks += 1
        
        success_list = [False] * total_tasks
        success_list = reserve_all_tasks(session_cache, users, current_dayofweek, success_list)
        logging.info(f"预约结果: {success_list}")

def debug(users, action=False):
    logging.info(f"调试模式启动")
    logging.info(f"全局设置: SLEEPTIME={SLEEPTIME}, ENDTIME={ENDTIME}, ENABLE_SLIDER={ENABLE_SLIDER}, RESERVE_TOMORROW={RESERVE_TOMORROW}")
    
    usernames, passwords = get_user_credentials(action)
    
    session_cache = login_all_users(users, usernames, passwords, action)
    current_dayofweek = get_current_dayofweek(action)
    
    for username, session_info in session_cache.items():
        user = next((u for u in users if u.get("username") == username), None)
        if not user:
            continue
        
        # 获取用户任务列表
        user_tasks = user.get("tasks", [user])
            
        # 并行处理用户的所有任务
        with ThreadPoolExecutor(max_workers=len(user_tasks)) as executor:
            futures = []
            for task_index, task in enumerate(user_tasks):
                futures.append(executor.submit(
                    process_single_task,
                    session=session_info["session"],
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
