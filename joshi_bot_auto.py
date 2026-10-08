import streamlit as st
from SmartApi import SmartConnect
import pyotp
import yfinance as yf
import pandas as pd
import sqlite3
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed

# Page Configuration
st.set_page_config(page_title="Angel One Ultra-Fast Copy Trading Terminal", layout="wide")

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
    try:
        cursor = db_conn.cursor()
        cursor.execute('''
            INSERT INTO logs (timestamp, account_type, client_id, symbol, action, qty, status, order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3], account_type, client_id, symbol, action, qty, status, str(order_id)))
        db_conn.commit()
    except Exception:
        pass

# App Header & Live Market Bar
st.title("⚡ Angel One Ultra-Fast Copy Trading Terminal (Control Center)")

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
        st.metric("Engine Status", "Control Panel Active", "Active")
except Exception:
    st.metric("Market Data", "Connecting...", "-")

st.markdown("---")

# Main Interface Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "👥 Client Manager & Fast Login", 
    "💰 Live Balances", 
    "📈 P&L Report (Date Range)", 
    "📊 Ultra-Fast Execution Terminal", 
    "📜 Trade Logs"
])

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
        st.subheader("🚀 Parallel Auto-Login")
        st.info("Multi-threaded login engine jo saare accounts ko ek sath authenticate karega.")
        
        if st.button("⚡ Parallel Login All 1000+ Clients"):
            cursor = db_conn.cursor()
            cursor.execute("SELECT client_id, password, totp_secret, api_key, account_type FROM clients")
            all_rows = cursor.fetchall()
            
            if not all_rows:
                st.warning("Pehle clients database me add karein!")
            else:
                master_objs = []
                slave_objs = []
                
                def login_client(row):
                    try:
                        c_id, pwd, totp_sec, api_k, acc_type = row
                        totp_gen = pyotp.TOTP(totp_sec).now() if totp_sec else ""
                        smart_obj = SmartConnect(api_key=api_k)
                        session_data = smart_obj.generateSession(c_id, pwd, totp_gen)
                        if session_data and session_data.get('status'):
                            return {"obj": smart_obj, "id": c_id, "type": acc_type}
                    except Exception:
                        pass
                    return None

                progress_text = st.empty()
                progress_text.text("Logging in accounts concurrently...")
                
                with ThreadPoolExecutor(max_workers=50) as executor:
                    futures = [executor.submit(login_client, row) for row in all_rows]
                    for future in as_completed(futures):
                        res = future.result()
                        if res:
                            if res['type'] == 'master':
                                master_objs.append({"obj": res['obj'], "id": res['id']})
                            else:
                                slave_objs.append({"obj": res['obj'], "id": res['id']})
                
                st.session_state['master_objs_bulk'] = master_objs
                st.session_state['slave_objs_bulk'] = slave_objs
                progress_text.empty()
                st.success(f"Login Complete! Connected Masters: {len(master_objs)} | Connected Slaves: {len(slave_objs)}")

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
    except Exception:
        pass

with tab2:
    st.subheader("💰 Live Master & Slave Account Balances")
    st.write("Yahan aap saare connected accounts ka live margin aur net available balance ek click me dekh sakte hain.")
    
    if st.button("🔄 Fetch Live Balances (All Accounts)"):
        all_accounts = []
        for m in st.session_state.get('master_objs_bulk', []):
            all_accounts.append({"id": m['id'], "type": "Master", "obj": m['obj']})
        for s in st.session_state.get('slave_objs_bulk', []):
            all_accounts.append({"id": s['id'], "type": "Slave", "obj": s['obj']})
            
        if not all_accounts:
            st.warning("Pehle Tab 1 se accounts login/connect karein!")
        else:
            balance_results = []
            
            def fetch_balance(acc):
                try:
                    rms = acc['obj'].rmsLimit()
                    if rms and rms.get('status'):
                        data = rms.get('data', {})
                        net = data.get('net', 'N/A')
                        available_cash = data.get('availablecash', 'N/A')
                        return {"Client ID": acc['id'], "Type": acc['type'], "Net Balance": net, "Available Cash": available_cash, "Status": "Success"}
                    else:
                        return {"Client ID": acc['id'], "Type": acc['type'], "Net Balance": "Error", "Available Cash": "Error", "Status": "Failed"}
                except Exception as e:
                    return {"Client ID": acc['id'], "Type": acc['type'], "Net Balance": "Exception", "Available Cash": str(e), "Status": "Failed"}

            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(fetch_balance, acc) for acc in all_accounts]
                for f in as_completed(futures):
                    balance_results.append(f.result())
            
            df_balances = pd.DataFrame(balance_results)
            st.dataframe(df_balances, use_container_width=True)

with tab3:
    st.subheader("📈 Profit & Loss (P&L) Report with Date Range")
    st.write("Har account ke execution logs aur trade performance ko diye gaye date range ke mutabiq analyze karein.")
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("Start Date", value=date.today())
    with col_d2:
        end_date = st.date_input("End Date", value=date.today())
        
    if st.button("📊 Generate P&L Report"):
        try:
            cursor = db_conn.cursor()
            query = """
                SELECT client_id, account_type, symbol, action, qty, status, timestamp 
                FROM logs 
                WHERE date(timestamp) BETWEEN date(?) AND date(?)
            """
            cursor.execute(query, (str(start_date), str(end_date)))
            rows = cursor.fetchall()
            
            if rows:
                df_pnl = pd.DataFrame(rows, columns=["Client ID", "Account Type", "Symbol", "Action", "Qty", "Status", "Timestamp"])
                st.markdown("### 📋 Filtered Execution & Performance Records")
                st.dataframe(df_pnl, use_container_width=True)
                
                st.markdown("### 📊 Summary per Client ID")
                summary_df = df_pnl.groupby(['Client ID', 'Account Type', 'Status']).size().reset_index(name='Total Trades')
                st.dataframe(summary_df, use_container_width=True)
            else:
                st.info("Chuni gayi date range me koi trade logs available nahi hain.")
        except Exception as pnl_err:
            st.error(f"Error generating report: {pnl_err}")

with tab4:
    st.subheader("🎛️ Control & Operations Center")
    
    # 3 Control Buttons added as requested from reference image
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns(3)
    with ctrl_col1:
        if st.button("▶ START COPY TRADING"):
            st.success("Copy Trading Engine Activated!")
            st.session_state['engine_running'] = True
    with ctrl_col2:
        if st.button("🛑 STOP ENGINE"):
            st.warning("Copy Trading Engine Paused/Stopped.")
            st.session_state['engine_running'] = False
    with ctrl_col3:
        if st.button("🚨 EMERGENCY KILL SWITCH"):
            st.error("EMERGENCY KILL SWITCH ACTIVATED! All operations halted.")
            st.session_state['engine_running'] = False

    st.markdown("---")
    st.subheader("⚡ Master Order Execution & Ultra-Fast Mirroring")
    exec_col1, exec_col2 = st.columns(2)
    
    with exec_col1:
        symbol = st.text_input("Trading Symbol", value="SBIN-EQ")
        symbol_token = st.text_input("Symbol Token", value="3045")
        qty = st.number_input("Quantity per Account", min_value=1, value=1)
        transaction_type = st.selectbox("Action", ["BUY", "SELL"])
        order_type = st.selectbox("Order Type", ["MARKET", "LIMIT"])
        price = st.number_input("Limit Price", value=0.0)

    with exec_col2:
        st.markdown("### 📋 System Readiness")
        active_masters = len(st.session_state.get('master_objs_bulk', []))
        active_slaves = len(st.session_state.get('slave_objs_bulk', []))
        engine_state = st.session_state.get('engine_running', True)
        
        st.info(f"**Engine State:** {'Running 🟢' if engine_state else 'Stopped 🔴'}\n\n**Target Symbol:** {symbol}\n\n**Active Masters:** {active_masters}\n\n**Active Slaves:** {active_slaves}")
        
        if st.button("🔥 FIRE ULTRA-FAST COPY TRADE"):
            if not engine_state:
                st.error("Engine is currently stopped or kill switch is active! Start engine first.")
            elif active_masters > 0 and active_slaves > 0:
                order_params = {
                    "variety": "NORMAL", "tradingsymbol": symbol, "symboltoken": symbol_token,
                    "transactiontype": transaction_type, "exchange": "NSE", "ordertype": order_type,
                    "producttype": "DELIVERY", "duration": "DAY", "price": str(price) if order_type == "LIMIT" else "0",
                    "squareoff": "0", "stoploss": "0", "quantity": str(qty)
                }
                
                def place_single_order(client_item, acc_type):
                    try:
                        res = client_item["obj"].placeOrder(order_params)
                        log_trade(acc_type, client_item['id'], symbol, transaction_type, qty, "SUCCESS", res)
                        return (True, client_item['id'], res)
                    except Exception as e:
                        log_trade(acc_type, client_item['id'], symbol, transaction_type, qty, "FAILED", str(e))
                        return (False, client_item['id'], str(e))

                status_container = st.empty()
                status_container.text("🚀 Executing master and broadcasting to all slaves simultaneously...")

                master_futures = []
                with ThreadPoolExecutor(max_workers=10) as executor:
                    for master in st.session_state['master_objs_bulk']:
                        master_futures.append(executor.submit(place_single_order, master, "Master"))
                    
                    for f in as_completed(master_futures):
                        success, m_id, m_res = f.result()
                        if success:
                            st.success(f"Master ({m_id}) Placed! Order ID: {m_res}")
                        else:
                            st.error(f"Master ({m_id}) Error: {m_res}")

                slave_futures = []
                with ThreadPoolExecutor(max_workers=100) as executor:
                    for slave in st.session_state['slave_objs_bulk']:
                        slave_futures.append(executor.submit(place_single_order, slave, "Slave"))
                    
                    success_slaves = 0
                    failed_slaves = 0
                    for f in as_completed(slave_futures):
                        success, s_id, _ = f.result()
                        if success:
                            success_slaves += 1
                        else:
                            failed_slaves += 1

                status_container.empty()
                st.success(f"⚡ Ultra-Fast Copy Complete! Successful Slaves: {success_slaves} | Failed Slaves: {failed_slaves}")
            else:
                st.warning("Pehle accounts connect karein!")

with tab5:
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
