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

# --- 🔥 全局配置优化 ---
# 专门针对"人数过多"问题的参数调整
SLEEPTIME = 0.8         # 减少等待时间，但保持足够间隔避免被限制
LOGIN_TIME = "21:58:30" # 提前30秒登录，确保会话稳定
RESERVE_TIME = "22:00:00" # 准点开始抢座
ENDTIME = "22:02:00"    # 延长抢座时间窗口
ENABLE_SLIDER = True    # 🔥 必须启用滑块验证码处理
MAX_ATTEMPT = 8         # 🔥 大幅增加尝试次数，因为现在每次都用新验证码

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
        time.sleep(0.1)  # 缩短检查间隔，更精确
    logging.info(f"已到达指定时间 {target_time_str}，继续执行。")

# --- 核心逻辑函数 ---

def login_user(username, password):
    """登录单个用户并返回一个包含会话的 reserve 实例"""
    logging.info(f"----------- 🔐 正在登录用户 {username} -----------")
    try:
        s = reserve(
            sleep_time=SLEEPTIME,
            max_attempt=MAX_ATTEMPT,
            enable_slider=ENABLE_SLIDER,  # 🔥 关键：启用验证码处理
            reserve_next_day=True  # 在Actions中总是预约第二天
        )
        login_result = s.login(username, password)
        if not login_result[0]:
            logging.error(f"❌ 用户 {username} 登录失败: {login_result[1]}")
            return None
        logging.info(f"✅ 用户 {username} 登录成功。")
        return s
    except Exception as e:
        logging.error(f"💥 用户 {username} 登录过程中发生异常: {str(e)}")
        return None

def login_all_users(users, usernames_env, passwords_env, action):
    """并发登录所有用户并缓存会话实例"""
    session_cache = {}
    if not action:
        logging.info("🏠 本地模式，将使用 config.json 中的账号密码。")
        usernames_list = [u['username'] for u in users]
        passwords_list = [u['password'] for u in users]
    else:
        logging.info("⚡ Actions 模式，将使用 Secrets 中的账号密码。")
        usernames_list = usernames_env.split(',')
        passwords_list = passwords_env.split(',')

    if len(usernames_list) != len(users) or len(passwords_list) != len(users):
        logging.error("❌ 账号/密码数量与配置文件中的用户数不匹配！")
        return {}

    # 🔥 优化：减少并发数，避免触发限制
    max_login_workers = min(len(users), 3)  # 最多3个并发登录
    
    with ThreadPoolExecutor(max_workers=max_login_workers) as executor:
        future_to_user = {
            executor.submit(login_user, u, p): users[i]["username"]
            for i, (u, p) in enumerate(zip(usernames_list, passwords_list))
        }
        for future in as_completed(future_to_user):
            config_username = future_to_user[future]
            session = future.result()
            if session:
                session_cache[config_username] = session
                # 登录成功后短暂等待，避免会话冲突
                time.sleep(0.5)
    
    logging.info(f"🎯 登录流程结束，共 {len(session_cache)} 个用户成功登录。")
    return session_cache

def process_user_tasks(session, user_config, action):
    """为一个用户处理其所有预约任务"""
    username = user_config['username']
    current_day = get_current_dayofweek()
    tasks_to_run = [
        task for task in user_config['tasks'] if current_day in task['daysofweek']
    ]
    
    if not tasks_to_run:
        logging.info(f"📅 用户 {username}: 今天没有需要执行的预约任务。")
        return True # 视为成功

    logging.info(f"📋 用户 {username}: 今天有 {len(tasks_to_run)} 个任务需要执行。")
    
    all_tasks_successful = True
    for i, task in enumerate(tasks_to_run):
        times = task['time']
        roomid = task['roomid']
        seatid = task['seatid']
        
        logging.info(f"--- 🚀 开始为用户 {username} 执行第{i+1}个任务: 时间 {times}, 房间 {roomid}, 座位 {seatid} ---")
        
        # 🔥 关键优化：每个任务之间增加随机间隔
        if i > 0:
            wait_time = random.uniform(1, 3)
            logging.info(f"⏰ 任务间隔等待 {wait_time:.1f} 秒...")
            time.sleep(wait_time)
        
        success = session.submit(times, roomid, seatid, action)
        if not success:
            all_tasks_successful = False
            logging.error(f"❌ 用户 {username} 的第{i+1}个任务失败！")
        else:
            logging.info(f"✅ 用户 {username} 的第{i+1}个任务成功！")
            # 🔥 优化：如果一个任务成功，继续尝试其他任务（而不是立即返回）
            # 这样可以帮助用户预约多个时段的座位
            
    return all_tasks_successful

# --- 主函数和调试函数 ---

def main(users, action=False):
    """主执行函数"""
    logging.info("🎬 程序启动...")
    
    if action:
        wait_until(LOGIN_TIME)
    
    usernames_env, passwords_env = get_user_credentials(action)
    session_cache = login_all_users(users, usernames_env, passwords_env, action)

    if not session_cache:
        logging.critical("💀 没有任何用户登录成功，程序终止。")
        return

    if action:
        wait_until(RESERVE_TIME)

    logging.info("========== 🎯 开始执行预约任务 ==========")
    
    # 🔥 优化：进一步减少并发数，每次最多2个用户同时执行任务
    max_task_workers = min(len(users), 2)
    
    with ThreadPoolExecutor(max_workers=max_task_workers) as executor:
        future_to_user = {
            executor.submit(process_user_tasks, session, users[i], action): user['username']
            for i, user in enumerate(users) if (session := session_cache.get(user['username']))
        }
        
        for future in as_completed(future_to_user):
            username = future_to_user[future]
            try:
                result = future.result()
                if result:
                    logging.info(f"🎉 用户 {username} 的所有任务处理完毕，结果: 成功。")
                else:
                    logging.warning(f"⚠️ 用户 {username} 的部分或全部任务处理失败。")
            except Exception as e:
                logging.error(f"💥 处理用户 {username} 的任务时发生严重异常: {e}")

    logging.info("========== 🏁 所有预约任务处理完毕 ==========")


def debug(users, action=False):
    """调试函数"""
    logging.info("--- 🔧 调试模式启动 ---")
    main(users, action)
    logging.info("--- 🔧 调试模式结束 ---")

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
        logging.info(f"📚 成功加载 {len(usersdata)} 个用户配置。")
    except Exception as e:
        logging.error(f"💥 配置文件加载失败: {e}")
        exit(1)
    
    # 🔥 添加环境检查
    if args.action and ENABLE_SLIDER:
        fid_enc = os.getenv("FID_ENC", "").strip()
        if not fid_enc:
            logging.warning("⚠️ 未设置 FID_ENC 环境变量，将使用默认值")
        else:
            logging.info(f"✅ FID_ENC 环境变量已设置: {fid_enc[:10]}...")
    
    if args.method == "reserve":
        main(usersdata, args.action)
    else:
        debug(usersdata, args.action)
