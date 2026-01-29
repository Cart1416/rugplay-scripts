import asyncio
import requests
import os
import json
import time
import datetime

import websockets

DEFAULT_CONFIG_PATH = "config.json"
WS_URL = "wss://ws.rugplay.com"

def load_config(path=DEFAULT_CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("check_interval_seconds", 30)
    cfg.setdefault("chatcoin", "RPCC")
    return cfg

cfg = load_config()
chatcoin = cfg.get("chatcoin", "RPCC")
COINS = [chatcoin]
websocket_mode = cfg.get("websocket_mode", True)

cookies = {
    'cf_clearance': cfg.get("cf_clearance"),
    '__Secure-better-auth.session_token': cfg.get("__Secure-better-auth.session_token"),
}

headers = {
    'User-Agent': os.getenv("USER_AGENT"),
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.5',
    'Referer': f'https://rugplay.com/coin/{chatcoin}',
    'Content-Type': 'application/json',
    'Origin': f'https://rugplay.com/coin/{chatcoin}',
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


def get_portfolio_data():
    data = requests.get('https://rugplay.com/api/portfolio/total', cookies=cookies, headers=headers)
    #print(data.json())
    return data.json()

def sell_coin(coin, amt):
    json_data = {
        'type': 'SELL',
        'amount': amt,
    }

    print(json_data)
    data = requests.post(f'https://rugplay.com/api/coin/{coin}/trade', cookies=cookies, headers=headers, json=json_data)
    print(data.json())
    return data.json()

def buy_coin(coin, amt):
    json_data = {
        'type': 'BUY',
        'amount': amt,
    }

    print(json_data)
    data = requests.post(f'https://rugplay.com/api/coin/{coin}/trade', cookies=cookies, headers=headers, json=json_data)
    print(data.json())
    return data.json()

def get_comments():
    data = requests.get(f'https://rugplay.com/api/coin/{chatcoin}/comments', cookies=cookies, headers=headers)
    if data.status_code == 429:
        return 429
    return data.json()

commentArray = ""

def post_comment_helper(message):
    json_data = {
        "content": message
    }
    if len(message) > 500:
        print("[WARN] Comment too long, truncating to 500 characters.")
        json_data["content"] = message[:497] + "..."
    data = requests.post(f'https://rugplay.com/api/coin/{chatcoin}/comments', cookies=cookies, headers=headers, json=json_data)
    print(data.status_code)
    try:
        return data.json()
    except ValueError:
        return {"status_code": data.status_code, "text": data.text}

def post_all_comments():
    global commentArray
    if commentArray:
        post_comment_helper(commentArray)
        print(commentArray)
    # erase the buffer after attempting to post all
    commentArray = ""
    return None

def post_comment(message):
    if not websocket_mode:
        global commentArray
        total_chars = len(commentArray)
        if total_chars >= 500 and commentArray != message + "\n":
            post_all_comments()
        commentArray += message + "\n"
        return None
    else:
        if len(message) > 500:
            message = message[:500]
        return post_comment_helper(message)


def get_coins_owned():
    data = get_portfolio_data()
    symbols = []
    quantitys = []
    if isinstance(data, dict):
        holdings = data.get("coinHoldings", [])
        if isinstance(holdings, list):
            for entry in holdings:
                if isinstance(entry, dict):
                    sym = entry.get("symbol")
                    quan = entry.get("quantity", 0)
                    if sym:
                        symbols.append(sym)
                    if quan:
                        quantitys.append(round(quan, 2))
    #return "Coins: " + ", ".join(symbols)
    comment = "Coins:\n"
    for i in range(len(symbols)):
        comment += f"*{symbols[i]}: {quantitys[i]}\n"
    return comment

def get_cash_balance():
    data = get_portfolio_data()
    cash = 0
    if isinstance(data, dict):
        cash = data.get("baseCurrencyBalance", 0)
    return cash


def parse_command(comment_text, username):
    comment_text = comment_text.strip().lower()
    if comment_text.startswith("!portfolio"):
        response = f"Cash: {get_cash_balance()}\n{get_coins_owned()}"
        post_comment(response)
    elif comment_text.startswith("!help"):
        help_text = (
            "Available commands:\n"
            "!portfolio - List owned coins\n"
            "!buy <COIN> <AMOUNT> - Buy specified amount of coin in dollars\n"
            "!sell <COIN> <AMOUNT> - Sell specified amount of coin in shares\n"
            "!daily - Get daily rewards\n"
            "!report <username> <untrustworthy/trustworthy> - Report a user as trustworthy or untrustworthy\n"
            "!getuser <username> - Check a user's trustworthiness\n"
            #f"Note: I currently check for new commands every {cfg.get('check_interval_seconds', 30)} seconds."
            #"Note: Ratelimits are high so I will respond within 1-5 minutes."
        )
        post_comment(help_text)
    elif comment_text.startswith("!daily"):
        response = requests.post('https://rugplay.com/api/rewards/claim', cookies=cookies, headers=headers)
        if response.status_code == 200:
            body = response.json()
            post_comment(f"Claimed reward successfully, next in 12h 00m.")
        elif response.status_code == 429:
            try:
                body = response.json()
            except ValueError:
                body = {}
            time_remain = None
            if isinstance(body, dict):
                time_remain = body.get("timeRemaining") or body.get("time_remaining") or body.get("timeLeft")
            if time_remain is None:
                post_comment("Daily reward not ready. Please wait before claiming again.")
            else:
                try:
                    post_comment(f"Daily reward not ready. Try again in {msToHoursMinutes(int(time_remain))}.")
                except Exception:
                    post_comment("Daily reward not ready. Try again later.")
        else:
            try:
                post_comment(f"Claim failed ({response.status_code}): {response.text}")
            except Exception:
                post_comment(f"Claim failed with status {response.status_code}.")
    elif comment_text.startswith("!buy "):
        parts = comment_text.split()
        if len(parts) == 3:
            coin = parts[1].upper()
            if coin.startswith("*"):
                coin = coin[1:]
            try:
                amt = parts[2]
                if (amt == "all" or amt == "max"):
                    portfolio = get_portfolio_data()
                    cash = portfolio.get("baseCurrencyBalance", 0)
                    response = buy_coin(coin, cash)
                    post_comment(f"Bought ${cash} of *{coin}: {response}")
                else:
                    amtf = float(parts[2])
                    response = buy_coin(coin, amtf)
                    post_comment(f"Bought ${amtf} of *{coin}: {response}")
            except ValueError:
                post_comment("Invalid amount specified for buy command.")
    elif comment_text.startswith("!sell "):
        parts = comment_text.split()
        if len(parts) == 3:
            coin = parts[1].upper()
            if coin.startswith("*"):
                coin = coin[1:]
            try:
                amt = parts[2]
                if (amt == "all" or amt == "max"):
                    portfolio = get_portfolio_data()
                    holdings = portfolio.get("coinHoldings", [])
                    coin_entry = next((entry for entry in holdings if entry.get("symbol") == coin), None)
                    if coin_entry:
                        shares = coin_entry.get("quantity", 0)
                        response = sell_coin(coin, shares)
                        post_comment(f"Sold all *{coin}: {response}")
                    else:
                        post_comment(f"You do not own any *{coin}.")
                else:
                    amtf = float(parts[2])
                    response = sell_coin(coin, amtf)
                    post_comment(f"Sold {amtf} *{coin}: {response}")
            except ValueError as e:
                post_comment(f"Invalid amount specified for sell command: {e}")
    elif comment_text.startswith("!report "):
        parts = comment_text.split()
        if len(parts) == 3:
            username = parts[1]
            if username.startswith("@"):
                username = username[1:]
            report_type = parts[2]
            if report_type == "trusted" or report_type == "good" or report_type == "trust":
                report_type = "trustworthy"
            elif report_type == "untrusted" or report_type == "bad" or report_type == "distrust":
                report_type = "untrustworthy"
            if report_type not in ["trustworthy", "untrustworthy"]:
                post_comment("Report type must be 'trustworthy' or 'untrustworthy'.")
                return
            # load or create data.json which holds user_reports
            data_path = "data.json"
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    store = json.load(f)
            except FileNotFoundError:
                store = {}
            if not isinstance(store, dict):
                store = {}
            user_reports = store.get("user_reports", {})
            if not isinstance(user_reports, dict):
                user_reports = {}
            reporter = username
            reporter_reports = user_reports.get(reporter, {"untrustworthy": [], "trustworthy": []})

            if report_type == "trustworthy" and username in reporter_reports.get("untrustworthy", []):
                reporter_reports["untrustworthy"].remove(username)

            elif report_type == "untrustworthy" and username in reporter_reports.get("trustworthy", []):
                reporter_reports["trustworthy"].remove(username)

            if username in reporter_reports.get(report_type, []):
                post_comment(f"You have already reported {username} as {report_type}.")
                return
            
            reporter_reports.setdefault(report_type, []).append(username)
            user_reports[reporter] = reporter_reports
            store["user_reports"] = user_reports
            try:
                with open(data_path, "w", encoding="utf-8") as f:
                    json.dump(store, f, indent=2, ensure_ascii=False)
                post_comment(f"Reported {username} as {report_type}.")
            except Exception as e:
                post_comment(f"[ERROR] failed to save report: {e}")
    elif comment_text.startswith("!getuser "):
        parts = comment_text.split()
        if len(parts) == 2:
            query_username = parts[1]
            if query_username.startswith("@"):
                query_username = query_username[1:]
            # load data.json which holds user_reports
            data_path = "data.json"
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    store = json.load(f)
            except FileNotFoundError:
                store = {}
            if not isinstance(store, dict):
                store = {}
            user_reports = store.get("user_reports", {})
            if not isinstance(user_reports, dict):
                user_reports = {}
            total_trustworthy = 0
            total_untrustworthy = 0
            for reporter, reports in user_reports.items():
                if not isinstance(reports, dict):
                    continue
                if query_username in reports.get("trustworthy", []):
                    total_trustworthy += 1
                if query_username in reports.get("untrustworthy", []):
                    total_untrustworthy += 1
            total = total_trustworthy + total_untrustworthy
            trustworthy_percentage = 0
            if total > 0:
                trustworthy_percentage = (total_trustworthy / total) * 100
            if total == 0:
                post_comment(f"User {query_username} has no reports.")
            else:
                post_comment(f"User {query_username} has a trustworthy rating of {trustworthy_percentage}% ({total_trustworthy} users voted trustworthy and {total_untrustworthy} voted untrustworthy")

def parse_comments():
    comments = get_comments()
    if comments == 429:
        print("[RATE LIMIT] Received 429 Too Many Requests. Waiting 3 minutes.")
        time.sleep(180)
        return
    # load or create data.json which holds comments_checked
    data_path = "data.json"
    try:
        with open(data_path, "r", encoding="utf-8") as f:
            store = json.load(f)
    except FileNotFoundError:
        store = {}
    if not isinstance(store, dict):
        store = {}
    checked = store.get("comments_checked", [])
    if not isinstance(checked, list):
        checked = []

    # normalize comments list
    comments_list = []
    if isinstance(comments, dict):
        comments_list = comments.get("comments", []) or []
    elif isinstance(comments, list):
        comments_list = comments
    else:
        comments_list = []

    # iterate new comments and mark them as checked
    for comment in comments_list:
        if not isinstance(comment, dict):
            continue
        cid = comment.get("id")
        if cid is None:
            continue
        if cid in checked:
            continue
        created_at = comment.get("createdAt")
        if not created_at:
            continue
        try:
            s = created_at
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            created_dt = datetime.datetime.fromisoformat(s)
        except Exception:
            try:
                created_dt = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%fZ")
                created_dt = created_dt.replace(tzinfo=datetime.timezone.utc)
            except Exception:
                print(f"[WARN] Could not parse createdAt: {created_at}")
                continue

        now = datetime.datetime.now(datetime.timezone.utc)
        age_seconds = (now - created_dt).total_seconds()
        if age_seconds > 10 * 60:
            # skip comments older than 10 minutes
            continue

        # mark as checked
        checked.append(cid)
        store["comments_checked"] = checked
        try:
            with open(data_path, "w", encoding="utf-8") as f:
                json.dump(store, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERROR] failed to save {data_path}: {e}")
        # parse command
        ctext = comment.get("content", "")
        username = comment.get("userName", "Unknown")
        parse_command(ctext, username)
        print(f"New comment to process: id={cid}")

async def listen_coin(coin: str):
    """Listen for comments for a single coin."""
    while True:  # Auto-reconnect loop
        try:
            async with websockets.connect(WS_URL) as ws:
                # Subscribe to the coin
                await ws.send(json.dumps({
                    "type": "set_coin",
                    "coinSymbol": coin
                }))

                print(f"Listening for comments on {coin}...")

                while True:
                    message = await ws.recv()
                    data = json.loads(message)

                    if data.get("type") == "new_comment":
                        comment_data = data.get("data", {})
                        username = comment_data.get("userName", "Unknown")
                        content = comment_data.get("content", "")

                        print(f"[{coin}] New comment from {username}: {content}")
                        parse_command(content, username)

        except websockets.ConnectionClosed:
            print(f"Connection for {coin} closed. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error for {coin}: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

async def main():
    # Start a listening task for each coin
    tasks = [listen_coin(coin) for coin in COINS]
    await asyncio.gather(*tasks)

def main_loop():
    while True:
        print("a")
        parse_comments()
        post_all_comments()
        time.sleep(int(cfg.get("check_interval_seconds", 30)))

if __name__ == '__main__':
    #post_comment("Bot restarted")
    if not websocket_mode:
        while True:
            try:
                main_loop()
            except Exception as e:
                print(F"[ERROR] {e}")
                continue
    else:
        asyncio.run(main())
