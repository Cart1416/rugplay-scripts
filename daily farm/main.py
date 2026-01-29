import requests
import os
import json
import time
import datetime

DEFAULT_CONFIG_PATH = "config.json"

def load_config(path=DEFAULT_CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("check_interval_seconds", 30)
    return cfg

cfg = load_config()
accounts = cfg.get("accounts")
if not isinstance(accounts, list):
    print("No 'accounts' list found in config, exiting.")
    exit(1)

check_interval = int(cfg.get("check_interval_seconds", 30))

headers = {
    'User-Agent': os.getenv("USER_AGENT"),
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': f'https://rugplay.com',
    'Content-Type': 'application/json',
    'Origin': f'https://rugplay.com/',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'Priority': 'u=0',
}

def msToHoursMinutes(ms):
    seconds = ms // 1000
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"

def claim_daily_reward(account):
    """Claim daily reward for a single account dict.

    account should contain keys: display_name, cf_clearance, __Secure-better-auth.session_token
    """
    display_name = account.get("display_name", "No name")
    cookies = {
        'cf_clearance': account.get("cf_clearance"),
        '__Secure-better-auth.session_token': account.get("__Secure-better-auth.session_token"),
    }

    response = requests.post('https://rugplay.com/api/rewards/claim', cookies=cookies, headers=headers)
    if response.status_code == 200:
        try:
            body = response.json()
            # Use safe access to json fields
            reward_amount = body.get('rewardAmount') if isinstance(body, dict) else None
        except Exception:
            reward_amount = None
        if reward_amount is not None:
            print(f"[{display_name}] Claimed {reward_amount} successfully, next in 12h 00m.")
        else:
            print(f"[{display_name}] Claimed successfully, next in 12h 00m.")
    elif response.status_code == 429:
        try:
            body = response.json()
        except ValueError:
            body = {}
        time_remain = None
        if isinstance(body, dict):
            time_remain = body.get("timeRemaining") or body.get("time_remaining") or body.get("timeLeft")
        if time_remain is None:
            print(f"[{display_name}] Daily reward not ready. Please wait before claiming again.")
        else:
            try:
                print(f"[{display_name}] Daily reward not ready. Try again in {msToHoursMinutes(int(time_remain))}.")
            except Exception:
                print(f"[{display_name}] Daily reward not ready. Try again later.")
    else:
        try:
            print(f"[{display_name}] Claim failed ({response.status_code}): {response.text}")
        except Exception:
            print(f"[{display_name}] Claim failed with status {response.status_code}.")

def main_loop():
    while True:
        for account in accounts:
            try:
                claim_daily_reward(account)
            except Exception as e:
                print(f"[ERROR][{account.get('display_name','No name')}] {e}")
            # small delay between accounts to avoid hitting rate limits
            time.sleep(1)
        # wait until next cycle
        time.sleep(check_interval)

if __name__ == '__main__':
    while True:
        try:
            main_loop()
        except Exception as e:
            print(F"[ERROR] {e}")
            continue
