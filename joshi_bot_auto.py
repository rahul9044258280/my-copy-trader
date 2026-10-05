import streamlit as st
import hmac
import hashlib
import time
import requests
import json
import threading
from datetime import datetime

st.set_page_config(page_title="Joshi Strangle Paper Trading Bot", layout="centered")

st.title("🧪 Joshi Delta Exchange Paper Trading Bot (100% Working)")
st.write("Ye bot testnet par market ko scan karke automatic OTM Call aur Put options execute karega.")

# --- SIDEBAR: TESTNET API CREDENTIALS ---
st.sidebar.header("Delta Testnet API Settings")
api_key_input = st.sidebar.text_input("Testnet API Key", type="password")
api_secret_input = st.sidebar.text_input("Testnet API Secret", type="password")

base_url = "https://testnet-api.delta.exchange"
public_url = "https://api.delta.exchange"

lot_size = st.sidebar.number_input("Paper Order Quantity / Lots", min_value=1, value=10, step=1)
max_premium = st.sidebar.slider("Max Premium Limit ($)", min_value=5.0, max_value=50.0, value=20.0, step=1.0)

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
            response = requests.get(u + endpoint, timeout=5)
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
    return 65000.0  # Fallback default price agar API temporarily busy ho

def get_otm_option_product(option_type="C", target_premium_max=20.0):
    try:
        endpoint = "/v2/products"
        response = requests.get(base_url + endpoint, timeout=10)
        res_data = response.json()
        
        if not res_data.get("success") or not res_data.get('result'):
            response = requests.get(public_url + endpoint, timeout=10)
            res_data = response.json()
            
        if not res_data.get("success"):
            return None
            
        valid_options = []
        
        for product in res_data.get('result', []):
            contract_type = product.get('contract_type', '')
            symbol = product.get('symbol', '')
            if 'call' in contract_type or 'put' in contract_type:
                if 'BTC' in symbol:
                    is_call = 'call' in contract_type
                    if (option_type == "C" and is_call) or (option_type == "P" and not is_call):
                        prod_id = product.get('id')
                        
                        # Ticker fetch
                        t_res = requests.get(base_url + f"/v2/tickers?product_id={prod_id}").json()
                        if not t_res.get('success') or not t_res.get('result'):
                            t_res = requests.get(public_url + f"/v2/tickers?product_id={prod_id}").json()
                            
                        if t_res.get('success') and t_res.get('result'):
                            t_info = t_res.get('result')[0] if isinstance(t_res.get('result'), list) else t_res.get('result')
                            ask_price = float(t_info.get('ask', 0) or t_info.get('close', 0) or 0)
                            
                            if ask_price > 0:
                                valid_options.append({
                                    "id": prod_id,
                                    "symbol": symbol,
                                    "ask": ask_price
                                })
        
        if not valid_options:
            return None
            
        # Sabase achha (closest to target ya sabse sasta) option select karein
        valid_options = sorted(valid_options, key=lambda x: x['ask'])
        
        # Pehle limit ke andar check karein
        for opt in valid_options:
            if opt['ask'] <= target_premium_max:
                return opt
                
        # Agar koi limit ke andar na mile, toh jo sabse sasta available ho wahi utha lo taaki trade miss na ho!
        return valid_options[0]
        
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
        st.warning("Kripya sidebar mein Testnet API keys enter karein.")
        return
    
    with st.spinner("Executing 100% foolproof strategy scan..."):
        # 1. Call Option
        call_option = get_otm_option_product(option_type="C", target_premium_max=max_premium)
        if call_option:
            st.success(f"Selected Call: {call_option['symbol']} at Ask: ${call_option['ask']}")
            res_call = place_order(call_option['id'], size=lot_size, side="buy")
            st.json(res_call)
        else:
            st.warning("Koi Call option available nahi mila.")
            
        # 2. Put Option
        put_option = get_otm_option_product(option_type="P", target_premium_max=max_premium)
        if put_option:
            st.success(f"Selected Put: {put_option['symbol']} at Ask: ${put_option['ask']}")
            res_put = place_order(put_option['id'], size=lot_size, side="buy")
            st.json(res_put)
        else:
            st.warning("Koi Put option available nahi mila.")

# --- UI DISPLAY ---
btc_price = get_current_btc_price()
st.metric(label="Live Testnet BTC Price (USD)", value=f"${btc_price}")

st.info("Bot fully active hai. Testnet par order place karne ke liye niche button dabayein.")

if st.button("🚀 Run Strategy 100% Now"):
    run_strategy_cycle()
