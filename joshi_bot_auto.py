import streamlit as st
import hmac
import hashlib
import time
import requests
import json
from datetime import datetime

st.set_page_config(page_title="Joshi Strangle Paper Trading Bot", layout="centered")

st.title("⚡ Joshi Delta Exchange Paper Trading Bot (Ultra-Fast)")
st.write("Ye bot lightning-fast speed se testnet par options scan karke orders execute karega.")

# --- SIDEBAR: TESTNET API CREDENTIALS ---
st.sidebar.header("Delta Testnet API Settings")
api_key_input = st.sidebar.text_input("Testnet API Key", type="password")
api_secret_input = st.sidebar.text_input("Testnet API Secret", type="password")

base_url = "https://testnet-api.delta.exchange"
public_url = "https://api.delta.exchange"

lot_size = st.sidebar.number_input("Paper Order Quantity / Lots", min_value=1, value=10, step=1)
# Max Premium Limit ab 100+ yani $500 tak set hai
max_premium = st.sidebar.slider("Max Premium Limit ($)", min_value=10.0, max_value=500.0, value=100.0, step=10.0)

def get_delta_signature(method, endpoint, payload_str=''):
    timestamp = str(int(time.time()))
    signature_data = timestamp + method + endpoint + payload_str
    signature = hmac.new(
        api_secret_input.encode('utf-8'),
        signature_data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return timestamp, signature

def get_current_btc_price():
    for u in [base_url, public_url]:
        try:
            endpoint = "/v2/tickers"
            response = requests.get(u + endpoint, timeout=3)
            res_data = response.json()
            if res_data.get("success"):
                for ticker in res_data.get('result', []):
                    sym = ticker.get('symbol', '')
                    if 'BTC' in sym and ('USD' in sym or 'USDT' in sym):
                        val = float(ticker.get('close', 0) or ticker.get('spot_price', 0))
                        if val > 0:
                            return val
        except:
            continue
    return 86000.0

def get_best_options_ultra_fast(target_premium_max=100.0):
    try:
        # Step 1: Ek hi call mein saare products aur tickers ek saath uthao (Super Fast)
        prod_res = requests.get(base_url + "/v2/products", timeout=5).json()
        if not prod_res.get("success"):
            prod_res = requests.get(public_url + "/v2/products", timeout=5).json()
            
        tick_res = requests.get(base_url + "/v2/tickers", timeout=5).json()
        if not tick_res.get("success"):
            tick_res = requests.get(public_url + "/v2/tickers", timeout=5).json()
            
        if not prod_res.get("success") or not tick_res.get("success"):
            st.error("Market data fetch karne mein error aaya.")
            return None, None

        # Tickers ko product_id ke hisaab se map kar lo dictionary mein
        ticker_map = {}
        for t in tick_res.get('result', []):
            pid = t.get('product_id')
            if pid:
                ticker_map[int(pid)] = float(t.get('ask', 0) or t.get('close', 0) or 0)

        call_options = []
        put_options = []

        # Step 2: Local loop mein bina kisi delay ke instant filter karo
        for product in prod_res.get('result', []):
            contract_type = str(product.get('contract_type', '')).lower()
            symbol = str(product.get('symbol', '')).upper()
            prod_id = product.get('id')
            
            if prod_id and ('call' in contract_type or 'put' in contract_type or 'option' in contract_type):
                if 'BTC' in symbol:
                    ask_price = ticker_map.get(int(prod_id), 0)
                    if ask_price > 0:
                        is_call = 'call' in contract_type or 'c' in symbol.split('-')[-1].lower()
                        opt_data = {"id": prod_id, "symbol": symbol, "ask": ask_price}
                        
                        if is_call:
                            call_options.append(opt_data)
                        else:
                            put_options.append(opt_data)

        # Sort by price (sabase saste options pehle)
        call_options = sorted(call_options, key=lambda x: x['ask'])
        put_options = sorted(put_options, key=lambda x: x['ask'])

        # Best Call selection (limit ke andar ya jo available ho)
        best_call = None
        for c in call_options:
            if c['ask'] <= target_premium_max:
                best_call = c
                break
        if not best_call and call_options:
            best_call = call_options[0] # Fallback to cheapest available

        # Best Put selection
        best_put = None
        for p in put_options:
            if p['ask'] <= target_premium_max:
                best_put = p
                break
        if not best_put and put_options:
            best_put = put_options[0] # Fallback to cheapest available

        return best_call, best_put

    except Exception as e:
        st.error(f"Ultra-fast scanning error: {e}")
        return None, None

def place_order(product_id, size, side):
    endpoint = "/v2/orders"
    payload = {
        "product_id": int(product_id),
        "size": int(size),
        "side": side.lower(),
        "order_type": "market"
    }
    payload_str = json.dumps(payload)
    timestamp, signature = get_delta_signature("POST", endpoint, payload_str)
    
    headers = {
        "api-key": api_key_input,
        "signature": signature,
        "timestamp": timestamp,
        "Content-Type": "application/json"
    }
    
    response = requests.post(base_url + endpoint, data=payload_str, headers=headers)
    return response.json()

def run_strategy_cycle():
    if not api_key_input or not api_secret_input:
        st.warning("Kripya sidebar mein Testnet API keys enter karein.")
        return
    
    start_time = time.time()
    with st.spinner("⚡ Ultra-fast market scanning and order execution..."):
        call_opt, put_opt = get_best_options_ultra_fast(target_premium_max=max_premium)
        
        if call_opt:
            st.success(f"Found Call: {call_opt['symbol']} @ ${call_opt['ask']}")
            res_call = place_order(call_opt['id'], size=lot_size, side="buy")
            st.json(res_call)
        else:
            st.warning("Koi Call option nahi mila.")
            
        if put_opt:
            st.success(f"Found Put: {put_opt['symbol']} @ ${put_opt['ask']}")
            res_put = place_order(put_opt['id'], size=lot_size, side="buy")
            st.json(res_put)
        else:
            st.warning("Koi Put option nahi mila.")
            
        elapsed = time.time() - start_time
        st.info(f"⚡ Scan & Execute completed in {elapsed:.2f} seconds!")

# --- UI DISPLAY ---
btc_price = get_current_btc_price()
st.metric(label="Live Testnet BTC Price (USD)", value=f"${btc_price}")

st.info("Bot fully optimized hai. Instant paper trade execute karne ke liye button dabayein.")

if st.button("🚀 Run Ultra-Fast Strategy Now"):
    run_strategy_cycle()
