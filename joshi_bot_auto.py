import streamlit as st
from SmartApi import SmartConnect
import pyotp
import yfinance as yf
import pandas as pd
import sqlite3
from datetime import datetime

# Page Configuration
st.set_page_config(page_title="Angel One Bulk Copy Trading Terminal (Auto-Login)", layout="wide")

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

# Initialize SQLite Database
def init_db():
    conn = sqlite3.connect('trading_terminal.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id TEXT UNIQUE,
            password TEXT,
            totp_secret TEXT,
            api_key TEXT,
            account_type TEXT
        )
    ''')
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
st.title("⚡ Angel One Bulk Copy Trading Terminal (Auto 24-hr Refresh)")

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
        st.metric("System Status", "Auto-Login Ready", "Active")
except Exception:
    st.metric("Market Data", "Connecting...", "-")

st.markdown("---")

# Main Interface Tabs
tab1, tab2, tab3 = st.tabs(["👥 Client Manager & Auto-Login", "📊 Order Execution Terminal", "📜 Trade Logs"])

with tab1:
    col_m1, col_m2 = st.columns(2)
    
    with col_m1:
        st.subheader("➕ Naya Client Add Karein")
        with st.form("add_client_form"):
            new_client_id = st.text_input("Client ID / User ID")
            new_password = st.text_input("Password / MPIN", type="password")
            new_totp = st.text_input("TOTP Secret Key (Google Auth Key)")
            new_api_key = st.text_input("API Key")
            new_acc_type = st.selectbox("Account Type", ["slave", "master"])
            
            submit_client = st.form_submit_button("💾 Save Client to Database")
            if submit_client:
                if new_client_id and new_api_key:
                    try:
                        cursor = db_conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO clients (client_id, password, totp_secret, api_key, account_type)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (new_client_id, new_password, new_totp, new_api_key, new_acc_type))
                        db_conn.commit()
                        st.success(f"Client {new_client_id} successfully saved!")
                    except Exception as db_err:
                        st.error(f"Error: {db_err}")
                else:
                    st.warning("Client ID aur API Key zaroori hai!")

    with col_m2:
        st.subheader("🔄 Daily Auto-Login (24-hr Token Refresh)")
        st.info("Roz subah market khulne par aapko kisi se poochne ki zaroorat nahi hai. Yeh button database me saved saare clients ke credentials aur TOTP use karke automatic session generate kar lega.")
        
        if st.button("🚀 1-Click Auto-Login All 1000+ Clients"):
            cursor = db_conn.cursor()
            cursor.execute("SELECT client_id, password, totp_secret, api_key, account_type FROM clients")
            all_rows = cursor.fetchall()
            
            master_objs = []
            slave_objs = []
            
            progress_bar = st.progress(0)
            total_accs = len(all_rows)
            
            if total_accs == 0:
                st.warning("Pehle clients database me add karein!")
            else:
                success_count = 0
                fail_count = 0
                for index, row in enumerate(all_rows):
                    try:
                        c_id, pwd, totp_sec, api_k, acc_type = row
                        # Automatically generate live TOTP using pyotp without manual entry
                        totp_gen = pyotp.TOTP(totp_sec).now() if totp_sec else ""
                        
                        smart_obj = SmartConnect(api_key=api_k)
                        session_data = smart_obj.generateSession(c_id, pwd, totp_gen)
                        
                        if session_data and session_data.get('status'):
                            if acc_type == 'master':
                                master_objs.append({"obj": smart_obj, "id": c_id})
                            else:
                                slave_objs.append({"obj": smart_obj, "id": c_id})
                            success_count += 1
                        else:
                            fail_count += 1
                    except Exception:
                        fail_count += 1
                        
                    progress_bar.progress((index + 1) / total_accs)
                
                st.session_state['master_objs_bulk'] = master_objs
                st.session_state['slave_objs_bulk'] = slave_objs
                st.success(f"Auto-Login Complete! Success: {success_count} | Failed: {fail_count}")
                st.info(f"Connected Masters: {len(master_objs)} | Connected Slaves: {len(slave_objs)}")

    st.markdown("### 📋 Saved Accounts Database List")
    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT client_id, account_type, api_key FROM clients")
        saved_clients = cursor.fetchall()
        if saved_clients:
            df_saved = pd.DataFrame(saved_clients, columns=["Client ID", "Account Type", "API Key"])
            st.dataframe(df_saved, use_container_width=True)
            
            if st.button("🗑️ Clear All Saved Accounts"):
                cursor.execute("DELETE FROM clients")
                db_conn.commit()
                st.success("Saare accounts hata diye gaye hain!")
                st.rerun()
        else:
            st.info("Abhi tak koi account saved nahi hai.")
    except Exception:
        pass

with tab2:
    st.subheader("⚡ Master Order Execution & Mirroring")
    exec_col1, exec_col2 = st.columns(2)
    
    with exec_col1:
        symbol = st.text_input("Trading Symbol", value="SBIN-EQ")
        symbol_token = st.text_input("Symbol Token", value="3045")
        qty = st.number_input("Quantity per Account", min_value=1, value=1)
        transaction_type = st.selectbox("Action", ["BUY", "SELL"])
        order_type = st.selectbox("Order Type", ["MARKET", "LIMIT"])
        price = st.number_input("Limit Price", value=0.0)

    with exec_col2:
        st.markdown("### 📋 Active Status")
        active_masters = len(st.session_state.get('master_objs_bulk', []))
        active_slaves = len(st.session_state.get('slave_objs_bulk', []))
        st.info(f"**Target Symbol:** {symbol}\n\n**Active Masters:** {active_masters}\n\n**Active Slaves:** {active_slaves}")
        
        if st.button("🔥 Execute & Copy Across All"):
            if active_masters > 0 and active_slaves > 0:
                order_params = {
                    "variety": "NORMAL", "tradingsymbol": symbol, "symboltoken": symbol_token,
                    "transactiontype": transaction_type, "exchange": "NSE", "ordertype": order_type,
                    "producttype": "DELIVERY", "duration": "DAY", "price": str(price) if order_type == "LIMIT" else "0",
                    "squareoff": "0", "stoploss": "0", "quantity": str(qty)
                }
                for master in st.session_state['master_objs_bulk']:
                    try:
                        m_res = master["obj"].placeOrder(order_params)
                        st.success(f"Master ({master['id']}) Placed! ID: {m_res}")
                        log_trade("Master", master['id'], symbol, transaction_type, qty, "SUCCESS", m_res)
                    except Exception as me:
                        st.error(f"Master Error: {me}")
                        log_trade("Master", master['id'], symbol, transaction_type, qty, "FAILED", str(me))
                
                for slave in st.session_state['slave_objs_bulk']:
                    try:
                        s_res = slave["obj"].placeOrder(order_params)
                        log_trade("Slave", slave['id'], symbol, transaction_type, qty, "SUCCESS", s_res)
                    except Exception as se:
                        log_trade("Slave", slave['id'], symbol, transaction_type, qty, "FAILED", str(se))
                st.success("Trade successfully mirrored to all slave accounts!")
            else:
                st.warning("Pehle 'Auto-Login All' button click karke sessions activate karein!")

with tab3:
    st.subheader("📜 Execution History & Logs")
    if st.button("🔄 Refresh Logs"): pass
    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT timestamp, account_type, client_id, symbol, action, qty, status, order_id FROM logs ORDER BY id DESC LIMIT 50")
        rows = cursor.fetchall()
        if rows:
            df_logs = pd.DataFrame(rows, columns=["Timestamp", "Account Type", "Client ID", "Symbol", "Action", "Qty", "Status", "Order ID"])
            st.dataframe(df_logs, use_container_width=True)
        else:
            st.info("Abhi tak koi logs available nahi hain.")
    except Exception:
        st.write("Error loading logs.")
