import streamlit as st
from SmartApi import SmartConnect
import pyotp
import yfinance as yf
import pandas as pd
import sqlite3
from datetime import datetime

# Page Configuration
st.set_page_config(page_title="Angel One Copy Trading Terminal", layout="wide")

# Custom Clean Dark Cinematic Theme
st.markdown("""
    <style>
    .main {background-color: #0e1117; color: #e0e0e0;}
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div>select {
        background-color: #161b22; color: #ffffff; border: 1px solid #30363d; border-radius: 6px;
    }
    .stButton>button {
        background-color: #00d09c; color: #0e1117; font-weight: bold; border-radius: 6px; border: none; width: 100%;
    }
    .stButton>button:hover {background-color: #00b386; color: #ffffff;}
    .block-container {padding-top: 2rem;}
    </style>
""", unsafe_allow_html=True)

# Initialize SQLite Database for Logging
def init_db():
    conn = sqlite3.connect('trade_logs.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            account_type TEXT,
            client_id TEXT,
            symbol TEXT,
            action TEXT,
            qty INTEGER,
            status TEXT,
            order_id TEXT
        )
    ''')
    conn.commit()
    return conn

db_conn = init_db()

def log_trade(account_type, client_id, symbol, action, qty, status, order_id):
    cursor = db_conn.cursor()
    cursor.execute('''
        INSERT INTO logs (timestamp, account_type, client_id, symbol, action, qty, status, order_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), account_type, client_id, symbol, action, qty, status, str(order_id)))
    db_conn.commit()

# App Header & Live Market Bar
st.title("⚡ Angel One Copy Trading Terminal")

ticker_col1, ticker_col2, ticker_col3 = st.columns(3)
try:
    nifty = yf.Ticker("^NSEI").history(period="1d")
    banknifty = yf.Ticker("^NSEBANK").history(period="1d")
    
    nifty_price = nifty['Close'].iloc[-1] if not nifty.empty else 0.0
    nifty_prev = nifty['Open'].iloc[0] if not nifty.empty else 0.0
    nifty_chg = nifty_price - nifty_prev
    
    bank_price = banknifty['Close'].iloc[-1] if not banknifty.empty else 0.0
    bank_prev = banknifty['Open'].iloc[0] if not banknifty.empty else 0.0
    bank_chg = bank_price - bank_prev

    with ticker_col1:
        st.metric("NIFTY 50", f"₹{nifty_price:,.2f}", f"{nifty_chg:+.2f}")
    with ticker_col2:
        st.metric("BANK NIFTY", f"₹{bank_price:,.2f}", f"{bank_chg:+.2f}")
    with ticker_col3:
        st.metric("System Status", "Live", "Connected")
except Exception:
    st.metric("Market Data", "Connecting...", "-")

st.markdown("---")

# Main Interface Tabs (No Side Clutter)
tab1, tab2, tab3 = st.tabs(["🔑 Account Credentials & Setup", "📊 Order Execution Terminal", "📜 Trade Logs & History"])

with tab1:
    st.subheader("Broker API Credentials Setup")
    
    col_m, col_s = st.columns(2)
    
    with col_m:
        st.markdown("### 👑 Master Account")
        master_api_key = st.text_input("Master API Key", type="password", key="m_key")
        master_client_id = st.text_input("Master Client ID", key="m_id")
        master_pwd = st.text_input("Master MPIN", type="password", key="m_pwd")
        master_totp_key = st.text_input("Master TOTP Secret", type="password", key="m_totp")

    with col_s:
        st.markdown("### 👥 Slave Accounts Configuration")
        num_slaves = st.number_input("Number of Slave Accounts", min_value=1, max_value=5, value=1, key="num_s")
        
        slave_configs = []
        for i in range(int(num_slaves)):
            with st.expander(f"Slave Account {i+1} Details"):
                s_key = st.text_input(f"API Key", key=f"s_key_{i}", type="password")
                s_id = st.text_input(f"Client ID", key=f"s_id_{i}")
                s_pwd = st.text_input(f"MPIN", key=f"s_pwd_{i}", type="password")
                s_totp = st.text_input(f"TOTP Secret", key=f"s_totp_{i}", type="password")
                slave_configs.append({"api_key": s_key, "client_id": s_id, "pwd": s_pwd, "totp": s_totp})

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🚀 Connect All Accounts Securely"):
        try:
            # Master Connection
            if master_api_key and master_client_id:
                totp_gen = pyotp.TOTP(master_totp_key).now() if master_totp_key else ""
                obj_master = SmartConnect(api_key=master_api_key)
                data_master = obj_master.generateSession(master_client_id, master_pwd, totp_gen)
                
                if data_master and data_master.get('status'):
                    st.session_state['master_obj'] = obj_master
                    st.session_state['master_id'] = master_client_id
                    st.success("Master Account Connected Successfully!")
                else:
                    st.error("Master Login Failed: Check credentials")
            
            # Slaves Connection
            st.session_state['slave_objs'] = []
            for idx, slave in enumerate(slave_configs):
                if slave["api_key"] and slave["client_id"]:
                    s_totp_gen = pyotp.TOTP(slave["totp"]).now() if slave["totp"] else ""
                    obj_slave = SmartConnect(api_key=slave["api_key"])
                    data_slave = obj_slave.generateSession(slave["client_id"], slave["pwd"], s_totp_gen)
                    
                    if data_slave and data_slave.get('status'):
                        st.session_state['slave_objs'].append({"obj": obj_slave, "id": slave["client_id"]})
                        st.success(f"Slave Account {idx+1} Connected Successfully!")
                    else:
                        st.error(f"Slave Account {idx+1} Failed: Check credentials")
        except Exception as e:
            st.error(f"Connection Error: {e}")

with tab2:
    st.subheader("⚡ Master Order Execution & Copy Trading Panel")
    
    exec_col1, exec_col2 = st.columns(2)
    
    with exec_col1:
        symbol = st.text_input("Trading Symbol (e.g., SBIN-EQ)", value="SBIN-EQ")
        symbol_token = st.text_input("Symbol Token", value="3045")
        qty = st.number_input("Quantity", min_value=1, value=1)
        transaction_type = st.selectbox("Action", ["BUY", "SELL"])
        order_type = st.selectbox("Order Type", ["MARKET", "LIMIT"])
        price = st.number_input("Limit Price", value=0.0)

    with exec_col2:
        st.markdown("### 📋 Execution Summary")
        st.info(f"**Target Symbol:** {symbol}\n\n**Order Qty:** {qty}\n\n**Action Type:** {transaction_type}\n\n**Connected Slaves:** {len(st.session_state.get('slave_objs', []))}")
        
        if st.button("🔥 Execute Master & Mirror to Slaves"):
            if 'master_obj' in st.session_state and 'slave_objs' in st.session_state:
                try:
                    order_params = {
                        "variety": "NORMAL",
                        "tradingsymbol": symbol,
                        "symboltoken": symbol_token,
                        "transactiontype": transaction_type,
                        "exchange": "NSE",
                        "ordertype": order_type,
                        "producttype": "DELIVERY",
                        "duration": "DAY",
                        "price": str(price) if order_type == "LIMIT" else "0",
                        "squareoff": "0",
                        "stoploss": "0",
                        "quantity": str(qty)
                    }
                    
                    # Execute Master Order
                    master_res = st.session_state['master_obj'].placeOrder(order_params)
                    st.success(f"Master Order Placed! Order ID: {master_res}")
                    log_trade("Master", st.session_state['master_id'], symbol, transaction_type, qty, "SUCCESS", master_res)
                    
                    # Mirror to Slaves
                    for slave in st.session_state['slave_objs']:
                        try:
                            slave_res = slave["obj"].placeOrder(order_params)
                            st.info(f"Copied to Slave ({slave['id']}) | Order ID: {slave_res}")
                            log_trade("Slave", slave["id"], symbol, transaction_type, qty, "SUCCESS", slave_res)
                        except Exception as se:
                            st.error(f"Slave {slave['id']} Error: {se}")
                            log_trade("Slave", slave["id"], symbol, transaction_type, qty, "FAILED", str(se))
                            
                except Exception as me:
                    st.error(f"Master Order Failed: {me}")
                    log_trade("Master", st.session_state.get('master_id', 'N/A'), symbol, transaction_type, qty, "FAILED", str(me))
            else:
                st.warning("Pehle 'Account Credentials & Setup' tab me jaakar accounts connect kijiye!")

with tab3:
    st.subheader("📜 Live Execution History & Logs")
    if st.button("🔄 Refresh Log Data"):
        pass
        
    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT timestamp, account_type, client_id, symbol, action, qty, status, order_id FROM logs ORDER BY id DESC LIMIT 20")
        rows = cursor.fetchall()
        if rows:
            df_logs = pd.DataFrame(rows, columns=["Timestamp", "Account Type", "Client ID", "Symbol", "Action", "Qty", "Status", "Order ID"])
            st.dataframe(df_logs, use_container_width=True)
        else:
            st.info("Abhi tak koi trade execute nahi hua hai.")
    except Exception:
        st.write("Logs load karne me error aaya.")
