import json
import time
import argparse
import os
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from utils import reserve

get_current_time = lambda action: time.strftime("%H:%M:%S", time.localtime(time.time() + 8*3600)) if action else time.strftime("%H:%M:%S", time.localtime(time.time()))
get_current_dayofweek = lambda action: time.strftime("%A", time.localtime(time.time() + 8*3600)) if action else time.strftime("%A", time.localtime(time.time()))

SLEEPTIME = 0.2
ENDTIME = "21:31:00"
ENABLE_SLIDER = True
MAX_ATTEMPT = 1
RESERVE_TOMORROW = True  # 使用正确的变量名

def get_user_credentials(action):
    if action:
        try:
            usernames = os.environ['USERNAMES']
            passwords = os.environ['PASSWORDS']
            return usernames, passwords
        except KeyError:
            logging.error("Missing USERNAMES or PASSWORDS in environment variables")
            return "", ""
    return "", ""

def login_and_reserve(users, usernames, passwords, action, success_list=None):
    # 修复日志输出中的变量名
    logging.info(f"Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_TOMORROW: {RESERVE_TOMORROW}")
    
    if action and len(usernames.split(",")) != len(users):
        raise Exception("user number should match the number of config")
    if success_list is None:
        total_tasks = sum(len(user["tasks"]) for user in users)
        success_list = [False] * total_tasks
        
    current_dayofweek = get_current_dayofweek(action)
    session_cache = {}
    task_index = 0
    
    for index, user in enumerate(users):
        username = user["username"]
        password = user["password"]
        
        if action:
            cred_list = usernames.split(',')
            if index < len(cred_list):
                username = cred_list[index]
            else:
                logging.error(f"Not enough usernames in secrets for index {index}")
                continue
            
            cred_list = passwords.split(',')
            if index < len(cred_list):
                password = cred_list[index]
            else:
                logging.error(f"Not enough passwords in secrets for index {index}")
                continue
            
        if username not in session_cache:
            logging.info(f"----------- {username} login -----------")
            s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, 
                        enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_TOMORROW)
            s.get_login_status()
            s.login(username, password)
            s.requests.headers.update({'Host': 'office.chaoxing.com'})
            session_cache[username] = s
        else:
            s = session_cache[username]
            
        for task in user["tasks"]:
            times = task["time"]
            roomid = task["roomid"]
            seatid = task["seatid"]
            daysofweek = task["daysofweek"]
            
            if current_dayofweek not in daysofweek:
                logging.info(f"Task {task_index}: Today not set to reserve")
                task_index += 1
                continue
                
            if not success_list[task_index]:
                logging.info(f"----------- {username} -- {times} -- {seatid} try -----------")
                suc = s.submit(times, roomid, seatid, action)
                success_list[task_index] = suc
                
            task_index += 1
            
    return success_list

def main(users, action=False):
    current_time = get_current_time(action)
    logging.info(f"start time {current_time}, action {'on' if action else 'off'}")
    attempt_times = 0
    usernames, passwords = None, None
    if action:
        usernames, passwords = get_user_credentials(action)
        
    total_tasks = sum(len(user["tasks"]) for user in users)
    success_list = None
    
    while current_time < ENDTIME:
        attempt_times += 1
        success_list = login_and_reserve(users, usernames, passwords, action, success_list)
        print(f"attempt time {attempt_times}, time now {current_time}, success list {success_list}")
        current_time = get_current_time(action)
        
        if sum(success_list) == total_tasks:
            print(f"All tasks reserved successfully!")
            return

def debug(users, action=False):
    # 修复日志输出中的变量名
    logging.info(f"Global settings: \nSLEEPTIME: {SLEEPTIME}\nENDTIME: {ENDTIME}\nENABLE_SLIDER: {ENABLE_SLIDER}\nRESERVE_TOMORROW: {RESERVE_TOMORROW}")
    logging.info(f" Debug Mode start! , action {'on' if action else 'off'}")
    
    if action:
        usernames, passwords = get_user_credentials(action)
    
    current_dayofweek = get_current_dayofweek(action)
    session_cache = {}
    
    for index, user in enumerate(users):
        username = user["username"]
        password = user["password"]
        
        if action:
            cred_list = usernames.split(',')
            if index < len(cred_list):
                username = cred_list[index]
            else:
                logging.error(f"Not enough usernames in secrets for index {index}")
                continue
            
            cred_list = passwords.split(',')
            if index < len(cred_list):
                password = cred_list[index]
            else:
                logging.error(f"Not enough passwords in secrets for index {index}")
                continue
        
        if username not in session_cache:
            logging.info(f"----------- {username} login -----------")
            s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, 
                        enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_TOMORROW)
            s.get_login_status()
            s.login(username, password)
            s.requests.headers.update({'Host': 'office.chaoxing.com'})
            session_cache[username] = s
        else:
            s = session_cache[username]
        
        for task_index, task in enumerate(user["tasks"]):
            times = task["time"]
            roomid = task["roomid"]
            seatid = task["seatid"]
            daysofweek = task["daysofweek"]
            
            if type(seatid) == str:
                seatid = [seatid]
            
            if current_dayofweek not in daysofweek:
                logging.info(f"Task {task_index}: Today not set to reserve")
                continue
            
            logging.info(f"----------- {username} -- Task {task_index+1}: {times} -- {seatid} try -----------")
            suc = s.submit(times, roomid, seatid, action)
            if suc:
                logging.info(f"Task {task_index+1} reserved successfully!")

def get_roomid(args1, args2):
    username = input("请输入用户名：")
    password = input("请输入密码：")
    s = reserve(sleep_time=SLEEPTIME, max_attempt=MAX_ATTEMPT, enable_slider=ENABLE_SLIDER, reserve_next_day=RESERVE_TOMORROW)
    s.get_login_status()
    s.login(username=username, password=password)
    s.requests.headers.update({'Host': 'office.chaoxing.com'})
    encode = input("请输入deptldEnc：")
    s.roomid(encode)

if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    parser = argparse.ArgumentParser(prog='Chao Xing seat auto reserve')
    parser.add_argument('-u','--user', default=config_path, help='user config file')
    parser.add_argument('-m','--method', default="reserve" ,choices=["reserve", "debug", "room"], help='for debug')
    parser.add_argument('-a','--action', action="store_true",help='use --action to enable in github action')
    args = parser.parse_args()
    func_dict = {"reserve": main, "debug":debug, "room": get_roomid}
    with open(args.user, "r+") as data:
        usersdata = json.load(data)["reserve"]
    func_dict[args.method](usersdata, args.action)
