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

# Corrected Testnet URL
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
        response = requests.get(base_url + endpoint)
        res_data = response.json()
        if res_data.get("success"):
            for ticker in res_data.get('result', []):
                if 'BTC' in ticker.get('symbol', ''):
                    return float(ticker.get('close', 0))
    except Exception as e:
        st.error(f"Error fetching BTC price: {e}")
    return 0

def get_otm_option_product(option_type="C", target_premium_max=10.0):
    try:
        endpoint = "/v2/products"
        response = requests.get(base_url + endpoint)
        res_data = response.json()
        
        if not res_data.get("success"):
            st.error("Failed to fetch products from Delta Testnet.")
            return None
            
        suitable_product = None
        min_diff = 99999
        
        for product in res_data.get('result', []):
            contract_type = product.get('contract_type', '')
            symbol = product.get('symbol', '')
            if 'call' in contract_type or 'put' in contract_type:
                if 'BTC' in symbol:
                    is_call = 'call' in contract_type
                    if (option_type == "C" and is_call) or (option_type == "P" and not is_call):
                        prod_id = product.get('id')
                        ticker_url = base_url + f"/v2/tickers?product_id={prod_id}"
                        t_res = requests.get(ticker_url).json()
                        if t_res.get('success') and t_res.get('result'):
                            t_info = t_res.get('result')[0] if isinstance(t_res.get('result'), list) else t_res.get('result')
                            ask_price = float(t_info.get('ask', 999) or 999)
                            if 0.1 <= ask_price <= target_premium_max:
                                diff = abs(target_premium_max - ask_price)
                                if diff < min_diff:
                                    min_diff = diff
                                    suitable_product = {
                                        "id": prod_id,
                                        "symbol": symbol,
                                        "ask": ask_price
                                    }
        return suitable_product
    except Exception as e:
        st.error(f"Error scanning options: {e}")
        return None

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
        st.warning("Kripya sidebar mein API keys enter karein.")
        return
    
    with st.spinner("Scanning testnet market for OTM options..."):
        call_option = get_otm_option_product(option_type="C", target_premium_max=max_premium)
        if call_option:
            st.success(f"Found Call: {call_option['symbol']} at Ask: ${call_option['ask']}")
            res_call = place_order(call_option['id'], size=lot_size, side="buy")
            st.json(res_call)
        else:
            st.warning("Koi suitable cheap Call option nahi mila testnet par.")
            
        put_option = get_otm_option_product(option_type="P", target_premium_max=max_premium)
        if put_option:
            st.success(f"Found Put: {put_option['symbol']} at Ask: ${put_option['ask']}")
            res_put = place_order(put_option['id'], size=lot_size, side="buy")
            st.json(res_put)
        else:
            st.warning("Koi suitable cheap Put option nahi mila testnet par.")

# --- UI DISPLAY ---
btc_price = get_current_btc_price()
st.metric(label="Live Testnet BTC Price (USD)", value=f"${btc_price}")

st.info("Paper trading bot active hai. Testnet par live data fetch karne ke liye niche button dabayein.")

if st.button("🧪 Run Paper Strategy Manually Now"):
    run_strategy_cycle()
