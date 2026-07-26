
import yfinance as yf
import pandas as pd
import requests
import os
import time
from datetime import datetime

# CONFIG
BB_PERIOD = 20
BB_STD = 1.5
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8739270737:AAFjGYmP4NfD46sBD01JDt01mcp0W1pFp_U")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")  # will auto-detect if empty
CALLMEBOT_PHONE = os.getenv("CALLMEBOT_PHONE", "")
CALLMEBOT_APIKEY = os.getenv("CALLMEBOT_APIKEY", "")

def get_chat_id():
    """Auto-find your chat ID after you send /start to your bot"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        r = requests.get(url, timeout=10).json()
        if r.get("result"):
            # get last chat id
            last = r["result"][-1]
            chat_id = last["message"]["chat"]["id"]
            print(f"Found chat_id: {chat_id}")
            return str(chat_id)
    except Exception as e:
        print(f"get_chat_id error: {e}")
    return None

def load_stocks():
    files = ["nse_500_plus_fno.txt", "nse_1000.txt", "nse_500_plus_fno.csv"]
    for fname in files:
        if os.path.exists(fname):
            try:
                with open(fname) as f:
                    stocks = [s.strip().upper() for s in f if s.strip() and not s.startswith("Symbol")]
                    # ensure .NS
                    out=[]
                    for s in stocks:
                        if ".NS" not in s:
                            s = s.split(",")[0].strip()
                            if ".NS" not in s:
                                s = s + ".NS"
                        out.append(s)
                    return list(dict.fromkeys(out))
            except: pass
    return ["RELIANCE.NS","TCS.NS","INFY.NS"]

def check_signal(df):
    if len(df) < 25:
        return False, None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df['SMA'] = df['Close'].rolling(BB_PERIOD).mean()
    df['STD'] = df['Close'].rolling(BB_PERIOD).std()
    df['Lower'] = df['SMA'] - BB_STD * df['STD']
    try:
        c1 = df.iloc[-2]
        c2 = df.iloc[-1]
        if pd.isna(c1['Lower']) or pd.isna(c2['Lower']):
            return False, None
        cond1 = c1['Low'] < c1['Lower']
        cond2 = c2['Close'] > c2['Lower']
        cond3 = c2['Volume'] > c1['Volume']
        if cond1 and cond2 and cond3:
            info = {
                'ltp': round(float(c2['Close']),2),
                'lower': round(float(c2['Lower']),2),
                'vol_change': round((float(c2['Volume'])/float(c1['Volume'])-1)*100,1) if c1['Volume'] else 0,
                'date': c2.name.strftime("%Y-%m-%d") if hasattr(c2.name, 'strftime') else str(c2.name)
            }
            return True, info
    except Exception as e:
        print(f"check err: {e}")
    return False, None

def scan():
    stocks = load_stocks()
    matches=[]
    print(f"Scanning {len(stocks)} stocks...")
    for i, sym in enumerate(stocks):
        try:
            df = yf.download(sym, period="3mo", interval="1d", progress=False, auto_adjust=True)
            if df.empty or len(df) < 25:
                continue
            sig, info = check_signal(df)
            if sig:
                matches.append((sym, info))
                print(f"FOUND: {sym} {info}")
            if i % 40 ==0:
                print(f"{i}/{len(stocks)} done, found {len(matches)}")
                time.sleep(0.8)
        except Exception as e:
            print(f"err {sym} {e}")
            time.sleep(0.3)
            continue
    return matches

def send_telegram(matches, chat_id):
    if not TELEGRAM_TOKEN:
        print("No telegram token")
        return False
    if not chat_id:
        chat_id = get_chat_id() or TELEGRAM_CHAT_ID
    if not chat_id:
        print("No chat_id found - please send /start to your bot @ab_77_screener_2026_bot first")
        return False
    
    if not matches:
        msg = f"🔍 *Bollinger Screener* {datetime.now().strftime('%d-%b %Y')}\nNo stocks matched today.\nScanned {len(load_stocks())} liquid NSE stocks."
    else:
        msg = f"🚀 *Bollinger Buy Alert* - {datetime.now().strftime('%d-%b %Y')} \n{len(matches)} stocks matched:\n\n"
        for sym, info in matches[:40]:
            name = sym.replace(".NS","")
            msg += f"• {name} - LTP {info['ltp']} (BB Low {info['lower']}) Vol +{info['vol_change']}%\n"
        msg += f"\nScan: Low[-2] < BB Lower & Close[-1] > BB Lower & Vol ↑"
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
        r = requests.post(url, json=payload, timeout=15)
        print("Telegram response:", r.text[:300])
        return True
    except Exception as e:
        print("Telegram failed:", e)
        return False

def send_whatsapp(matches):
    if not CALLMEBOT_PHONE or not CALLMEBOT_APIKEY:
        print("WhatsApp creds not set, skipping")
        return False
    if not matches:
        txt = f"Bollinger Screener {datetime.now().strftime('%d-%b')}: No match. Scanned {len(load_stocks())} stocks."
    else:
        lines = [f"Bollinger Buy Alert {datetime.now().strftime('%d-%b')} - {len(matches)} stocks:"]
        for sym, info in matches[:25]:
            lines.append(f"{sym.replace('.NS','')} LTP {info['ltp']} Vol +{info['vol_change']}%")
        txt = "\n".join(lines)
    try:
        import urllib.parse
        url = f"https://api.callmebot.com/whatsapp.php?phone={CALLMEBOT_PHONE}&text={urllib.parse.quote(txt)}&apikey={CALLMEBOT_APIKEY}"
        r = requests.get(url, timeout=15)
        print("WhatsApp:", r.text[:200])
        return True
    except Exception as e:
        print("WA fail", e)
        return False

if __name__ == "__main__":
    # Step 1: get chat id if not set
    chat_id = TELEGRAM_CHAT_ID or get_chat_id()
    if not chat_id:
        print("IMPORTANT: Open Telegram, search @ab_77_screener_2026_bot and send /start")
        print("Then run again in 10 seconds")
        # wait 15 sec for user to send /start if first time
        print("Waiting 15 sec for you to send /start...")
        time.sleep(15)
        chat_id = get_chat_id()
    
    matches = scan()
    if matches:
        pd.DataFrame([{"Symbol": s, **info} for s,info in matches]).to_csv("today_signals.csv", index=False)
    
    if chat_id:
        send_telegram(matches, chat_id)
    send_whatsapp(matches)
    print("DONE")
