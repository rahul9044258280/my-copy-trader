import streamlit as st
import hmac
import hashlib
import time
import requests
import json
import threading
from datetime import datetime

st.set_page_config(page_title="Joshi Strangle Paper Trading Bot", layout="centered")

st.title("🧪 Joshi Delta Exchange Paper Trading Bot (Testnet)")
st.write("Ye bot background mein automatic har 12 ghante mein Delta Testnet par virtual/paper trades execute karega.")

# --- SIDEBAR: TESTNET API CREDENTIALS ---
st.sidebar.header("Delta Testnet API Settings")
api_key_input = st.sidebar.text_input("Testnet API Key", type="password")
api_secret_input = st.sidebar.text_input("Testnet API Secret", type="password")

# CRITICAL CHANGE: LIVE URL KI JAGAH TESTNET URL
base_url = "https://testnet-api.delta.exchange"

lot_size = st.sidebar.number_input("Paper Order Quantity / Lots", min_value=1, value=10, step=1)
max_premium = st.sidebar.slider("Max Premium Limit ($)", min_value=5.0, max_value=20.0, value=10.0, step=0.5)

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
    try:
        endpoint = "/v2/tickers"
        response = requests.get(base_url + endpoint).json()
        for ticker in response.get('result', []):
            if ticker.get('symbol') == 'BTCUSD':
                return float(ticker.get('close', 0))
    except Exception as e:
        print(f"Error fetching BTC price: {e}")
    return 0

def get_otm_option_product(option_type="C", target_premium_max=10.0):
    try:
        endpoint = "/v2/products"
        response = requests.get(base_url + endpoint).json()
        
        suitable_product = None
        min_diff = 99999
        
        for product in response.get('result', []):
            if product.get('contract_type') in ['call_options', 'put_options']:
                if 'BTC' in product.get('symbol', ''):
                    is_call = product.get('contract_type') == 'call_options'
                    if (option_type == "C" and is_call) or (option_type == "P" and not is_call):
                        ticker_url = base_url + f"/v2/tickers/{product.get('symbol')}"
                        t_res = requests.get(ticker_url).json()
                        if t_res.get('success'):
                            ask_price = float(t_res.get('result', {}).get('ask', 999))
                            if 1.0 <= ask_price <= target_premium_max:
                                diff = abs(target_premium_max - ask_price)
                                if diff < min_diff:
                                    min_diff = diff
                                    suitable_product = {
                                        "id": product.get('id'),
                                        "symbol": product.get('symbol'),
                                        "ask": ask_price
                                    }
        return suitable_product
    except Exception as e:
        print(f"Error scanning options: {e}")
        return None

def place_order(product_id, size, side):
    endpoint = "/v2/orders"
    payload = {
        "product_id": product_id,
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
        print("Testnet API Keys missing in background task.")
        return
    
    print(f"--- [Paper Bot] Running Strategy Cycle at {datetime.now()} ---")
    
    # 1. Buy OTM Call (Paper)
    call_option = get_otm_option_product(option_type="C", target_premium_max=max_premium)
    if call_option:
        res_call = place_order(call_option['id'], size=lot_size, side="buy")
        print("Paper Call Order Placed:", res_call)
        
    # 2. Buy OMT Put (Paper)
    put_option = get_otm_option_product(option_type="P", target_premium_max=max_premium)
    if put_option:
        res_put = place_order(put_option['id'], size=lot_size, side="buy")
        print("Paper Put Order Placed:", res_put)

def background_scheduler():
    while True:
        try:
            run_strategy_cycle()
        except Exception as e:
            print(f"Scheduler Error: {e}")
        time.sleep(43200) # 12 hours

if 'bot_started' not in st.session_state:
    st.session_state['bot_started'] = True
    t = threading.Thread(target=background_scheduler, daemon=True)
    t.start()
    st.success("Paper Trading Background Scheduler started successfully!")

# --- UI DISPLAY ---
btc_price = get_current_btc_price()
st.metric(label="Live Testnet BTC Price (USD)", value=f"${btc_price}")

st.info("Paper trading bot active hai. Ye testnet par bina asli paisa lagaye automated trades execute karega.")

if st.button("🧪 Run Paper Strategy Manually Now"):
    with st.spinner("Executing paper trade cycle..."):
        run_strategy_cycle()
        st.success("Manual paper trade cycle completed!")
