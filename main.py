import json
import time
import argparse
import os
import logging
import datetime
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 日志记录配置 ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --- 从 utils 导入必要的模块 ---
from utils import reserve, get_user_credentials

# --- 全局配置 ---
# 您可以在这里调整脚本的核心参数
SLEEPTIME = 0.2         # 每个任务失败后的等待时间（秒）
LOGIN_TIME = "21:59:30" # 在 Actions 中，开始登录的时间（北京时间）
RESERVE_TIME = "22:00:00" # 在 Actions 中，开始抢座的时间（北京时间）
ENDTIME = "22:01:00"    # 在 Actions 中，抢座流程的结束时间
ENABLE_SLIDER = True   # 您的学校是否有滑块验证码？True 或 False
MAX_ATTEMPT = 3         # 每个座位最大尝试次数

# --- 时间处理函数 ---
def get_current_time():
    """获取当前北京时间 H:M:S"""
    return datetime.datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%H:%M:%S")

def get_current_dayofweek():
    """获取当前星期几（英文）"""
    return datetime.datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%A")

def wait_until(target_time_str):
    """等待直到指定的北京时间"""
    logging.info(f"等待直到北京时间 {target_time_str}...")
    while get_current_time() < target_time_str:
        time.sleep(0.5)
    logging.info(f"已到达指定时间 {target_time_str}，继续执行。")

# --- 核心逻辑函数 ---

def login_user(username, password):
    """登录单个用户并返回一个包含会话的 reserve 实例"""
    logging.info(f"----------- 正在登录用户 {username} -----------")
    try:
        s = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,
            reserve_next_day=True  # 在Actions中总是预约第二天
        )
        login_result = s.login(username, password)
        if not login_result[0]:
            logging.error(f"用户 {username} 登录失败: {login_result[1]}")
            return None
        logging.info(f"用户 {username} 登录成功。")
        return s
    except Exception as e:
        logging.error(f"用户 {username} 登录过程中发生异常: {str(e)}")
        return None

def login_all_users(users, usernames_env, passwords_env, action):
    """并发登录所有用户并缓存会话实例"""
    session_cache = {}
    if not action:
        logging.info("本地模式，将使用 config.json 中的账号密码。")
        usernames_list = [u['username'] for u in users]
        passwords_list = [u['password'] for u in users]
    else:
        logging.info("Actions 模式，将使用 Secrets 中的账号密码。")
        usernames_list = usernames_env.split(',')
        passwords_list = passwords_env.split(',')

    if len(usernames_list) != len(users) or len(passwords_list) != len(users):
        logging.error("账号/密码数量与配置文件中的用户数不匹配！")
        return {}

    with ThreadPoolExecutor(max_workers=len(users)) as executor:
        future_to_user = {
            executor.submit(login_user, u, p): users[i]["username"]
            for i, (u, p) in enumerate(zip(usernames_list, passwords_list))
        }
        for future in as_completed(future_to_user):
            config_username = future_to_user[future]
            session = future.result()
            if session:
                session_cache[config_username] = session
    
    logging.info(f"登录流程结束，共 {len(session_cache)} 个用户成功登录。")
    return session_cache

def process_user_tasks(session, user_config, action):
    """为一个用户处理其所有预约任务"""
    username = user_config['username']
    current_day = get_current_dayofweek()
    tasks_to_run = [
        task for task in user_config['tasks'] if current_day in task['daysofweek']
    ]
    
    if not tasks_to_run:
        logging.info(f"用户 {username}: 今天没有需要执行的预约任务。")
        return True # 视为成功

    logging.info(f"用户 {username}: 今天有 {len(tasks_to_run)} 个任务需要执行。")
    
    all_tasks_successful = True
    for task in tasks_to_run:
        times = task['time']
        roomid = task['roomid']
        seatid = task['seatid']
        
        logging.info(f"--- 开始为用户 {username} 执行任务: 时间 {times}, 房间 {roomid}, 座位 {seatid} ---")
        success = session.submit(times, roomid, seatid, action)
        if not success:
            all_tasks_successful = False
            logging.error(f"--- 用户 {username} 的任务: 时间 {times} 失败！ ---")
        else:
            logging.info(f"--- 用户 {username} 的任务: 时间 {times} 成功！ ---")
            # 如果一个任务成功，可以认为该用户今天的任务已完成，避免重复预约
            return True 
            
    return all_tasks_successful

# --- 主函数和调试函数 ---

def main(users, action=False):
    """主执行函数"""
    logging.info("程序启动...")
    
    if action:
        wait_until(LOGIN_TIME)
    
    usernames_env, passwords_env = get_user_credentials(action)
    session_cache = login_all_users(users, usernames_env, passwords_env, action)

    if not session_cache:
        logging.critical("没有任何用户登录成功，程序终止。")
        return

    if action:
        wait_until(RESERVE_TIME)

    logging.info("========== 开始执行预约任务 ==========")
    
    with ThreadPoolExecutor(max_workers=len(users)) as executor:
        future_to_user = {
            executor.submit(process_user_tasks, session, users[i], action): user['username']
            for i, user in enumerate(users) if (session := session_cache.get(user['username']))
        }
        
        for future in as_completed(future_to_user):
            username = future_to_user[future]
            try:
                result = future.result()
                if result:
                    logging.info(f"用户 {username} 的所有任务处理完毕，结果: 成功。")
                else:
                    logging.error(f"用户 {username} 的部分或全部任务处理失败。")
            except Exception as e:
                logging.error(f"处理用户 {username} 的任务时发生严重异常: {e}")

    logging.info("========== 所有预约任务处理完毕 ==========")


def debug(users, action=False):
    """调试函数"""
    logging.info("--- 调试模式启动 ---")
    main(users, action)
    logging.info("--- 调试模式结束 ---")

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    parser = argparse.ArgumentParser(prog='超星座位自动预约')
    parser.add_argument('-u', '--user', default=config_path, help='用户配置文件路径')
    parser.add_argument('-m', '--method', default="reserve", choices=["reserve", "debug"], help='运行模式: reserve 或 debug')
    parser.add_argument('-a', '--action', action="store_true", help='启用 GitHub Actions 模式')
    args = parser.parse_args()
    
    try:
        with open(args.user, "r", encoding="utf-8") as data:
            usersdata = json.load(data)["reserve"]
        logging.info(f"成功加载 {len(usersdata)} 个用户配置。")
    except Exception as e:
        logging.error(f"配置文件加载失败: {e}")
        exit(1)
    
    if args.method == "reserve":
        main(usersdata, args.action)
    else:
        debug(usersdata, args.action)
