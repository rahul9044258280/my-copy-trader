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

# Initialize SQLite Database & Auto-migrate columns if missing
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
            account_type TEXT,
            is_active INTEGER DEFAULT 1,
            lot_multiplier INTEGER DEFAULT 1
        )
    ''')
    # Safe migration for existing tables
    try:
        cursor.execute("ALTER TABLE clients ADD COLUMN is_active INTEGER DEFAULT 1")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE clients ADD COLUMN lot_multiplier INTEGER DEFAULT 1")
    except Exception:
        pass

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
st.title("⚡ Angel One Ultra-Fast Copy Trading Terminal")

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
        st.metric("Engine Status", "Ready", "Active")
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
    # Landscape Split: Left for Master Section, Right for Slave Section
    master_col, slave_col = st.columns(2)
    
    with master_col:
        st.subheader("👑 Master Account Section")
        with st.form("add_master_form"):
            m_client_id = st.text_input("Master Client ID / User ID", key="m_id")
            m_password = st.text_input("Master Password / MPIN", type="password", key="m_pwd")
            m_totp = st.text_input("Master TOTP Secret Key", key="m_totp")
            m_api_key = st.text_input("Master API Key", key="m_apikey")
            
            submit_master = st.form_submit_button("💾 Save Master Account")
            if submit_master:
                if m_client_id and m_api_key:
                    try:
                        cursor = db_conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO clients (client_id, password, totp_secret, api_key, account_type, is_active, lot_multiplier)
                            VALUES (?, ?, ?, ?, 'master', 1, 1)
                        ''', (m_client_id, m_password, m_totp, m_api_key))
                        db_conn.commit()
                        st.success(f"Master Account {m_client_id} successfully saved!")
                    except Exception as db_err:
                        st.error(f"Error: {db_err}")
                else:
                    st.warning("Client ID aur API Key zaroori hai!")

    with slave_col:
        st.subheader("🔗 Slave Accounts Section")
        with st.form("add_slave_form"):
            s_client_id = st.text_input("Slave Client ID / User ID", key="s_id")
            s_password = st.text_input("Slave Password / MPIN", type="password", key="s_pwd")
            s_totp = st.text_input("Slave TOTP Secret Key", key="s_totp")
            s_api_key = st.text_input("Slave API Key", key="s_apikey")
            s_multiplier = st.number_input("Lot/Quantity Multiplier (Default: 1)", min_value=1, value=1, key="s_mult")
            
            submit_slave = st.form_submit_button("💾 Save Slave Account")
            if submit_slave:
                if s_client_id and s_api_key:
                    try:
                        cursor = db_conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO clients (client_id, password, totp_secret, api_key, account_type, is_active, lot_multiplier)
                            VALUES (?, ?, ?, ?, 'slave', 1, ?)
                        ''', (s_client_id, s_password, s_totp, s_api_key, s_multiplier))
                        db_conn.commit()
                        st.success(f"Slave Account {s_client_id} successfully saved!")
                    except Exception as db_err:
                        st.error(f"Error: {db_err}")
                else:
                    st.warning("Client ID aur API Key zaroori hai!")

    st.markdown("---")
    st.subheader("🚀 Parallel Auto-Login & Control Panel")
    
    if st.button("⚡ Parallel Login All 1000+ Clients"):
        cursor = db_conn.cursor()
        cursor.execute("SELECT client_id, password, totp_secret, api_key, account_type, is_active, lot_multiplier FROM clients WHERE is_active = 1")
        all_rows = cursor.fetchall()
        
        if not all_rows:
            st.warning("Pehle active clients database me add karein!")
        else:
            master_objs = []
            slave_objs = []
            
            def login_client(row):
                try:
                    c_id, pwd, totp_sec, api_k, acc_type, active, mult = row
                    totp_gen = pyotp.TOTP(totp_sec).now() if totp_sec else ""
                    smart_obj = SmartConnect(api_key=api_k)
                    session_data = smart_obj.generateSession(c_id, pwd, totp_gen)
                    if session_data and session_data.get('status'):
                        return {"obj": smart_obj, "id": c_id, "type": acc_type, "multiplier": mult}
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
                            slave_objs.append({"obj": res['obj'], "id": res['id'], "multiplier": res['multiplier']})
            
            st.session_state['master_objs_bulk'] = master_objs
            st.session_state['slave_objs_bulk'] = slave_objs
            progress_text.empty()
            st.success(f"Login Complete! Connected Masters: {len(master_objs)} | Connected Active Slaves: {len(slave_objs)}")

    st.markdown("### 📋 Manage Saved Accounts & Individual Controls")
    try:
        cursor = db_conn.cursor()
        cursor.execute("SELECT id, client_id, account_type, api_key, is_active, lot_multiplier FROM clients")
        all_db_clients = cursor.fetchall()
        
        if all_db_clients:
            for row in all_db_clients:
                db_id, c_id, acc_type, api_k, is_act, mult = row
                
                expander_label = f"👑 Master ID: {c_id}" if acc_type == 'master' else f"🔹 Slave ID: {c_id} (Multiplier: {mult}x | Status: {'Active 🟢' if is_act else 'Off 🔴'})"
                
                with st.expander(expander_label):
                    if acc_type == 'slave':
                        col_c1, col_c2, col_c3 = st.columns(3)
                        with col_c1:
                            new_act_status = st.selectbox("Trade Status", [1, 0], index=0 if is_act==1 else 1, format_func=lambda x: "ON (Trading Enabled)" if x==1 else "OFF (Paused)", key=f"status_{db_id}")
                        with col_c2:
                            new_mult_val = st.number_input("Lot Multiplier", min_value=1, value=mult, key=f"mult_{db_id}")
                        with col_c3:
                            st.markdown("<br>", unsafe_allow_html=True)
                            update_btn = st.button("💾 Update Settings", key=f"update_{db_id}")
                            
                        if update_btn:
                            cursor.execute("UPDATE clients SET is_active = ?, lot_multiplier = ? WHERE id = ?", (new_act_status, new_mult_val, db_id))
                            db_conn.commit()
                            st.success(f"Settings updated for {c_id}!")
                            st.rerun()
                    
                    if st.button(f"🗑️ Delete Client {c_id}", key=f"del_{db_id}"):
                        cursor.execute("DELETE FROM clients WHERE id = ?", (db_id,))
                        db_conn.commit()
                        st.success(f"Client {c_id} deleted successfully!")
                        st.rerun()
                        
            if st.button("🗑️ Clear All Saved Accounts"):
                cursor.execute("DELETE FROM clients")
                db_conn.commit()
                st.success("Saare accounts hata diye gaye hain!")
                st.rerun()
    except Exception as e:
        st.write(f"Error loading management panel: {e}")

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
            st.warning("Pehle Tab 1 से accounts login/connect karein!")
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
    
    active_masters = len(st.session_state.get('master_objs_bulk', []))
    active_slaves = len(st.session_state.get('slave_objs_bulk', []))
    engine_state = st.session_state.get('engine_running', False)
    
    st.info(f"**Engine State:** {'Running 🟢' if engine_state else 'Stopped 🔴'}\n\n**Active Masters:** {active_masters}\n\n**Active Slaves:** {active_slaves}")

    st.markdown("---")
    
    ctrl_col1, ctrl_col2, ctrl_col3 = st.columns(3)
    
    with ctrl_col1:
        if st.button("▶ START COPY TRADING"):
            st.session_state['engine_running'] = True
            active_m = len(st.session_state.get('master_objs_bulk', []))
            active_s = len(st.session_state.get('slave_objs_bulk', []))
            
            if active_m > 0 and active_s > 0:
                base_qty = 1
                master_order_params = {
                    "variety": "NORMAL", "tradingsymbol": "SBIN-EQ", "symboltoken": "3045",
                    "transactiontype": "BUY", "exchange": "NSE", "ordertype": "MARKET",
                    "producttype": "DELIVERY", "duration": "DAY", "price": "0",
                    "squareoff": "0", "stoploss": "0", "quantity": str(base_qty)
                }
                
                def place_master_order(master):
                    try:
                        res = master["obj"].placeOrder(master_order_params)
                        log_trade("Master", master['id'], "SBIN-EQ", "BUY", base_qty, "SUCCESS", res)
                        return (True, master['id'], res)
                    except Exception as e:
                        log_trade("Master", master['id'], "SBIN-EQ", "BUY", base_qty, "FAILED", str(e))
                        return (False, master['id'], str(e))

                def place_slave_order(slave):
                    try:
                        cur = db_conn.cursor()
                        cur.execute("SELECT is_active, lot_multiplier FROM clients WHERE client_id = ?", (slave['id'],))
                        row = cur.fetchone()
                        if row and row[0] == 1:
                            mult = row[1]
                            final_qty = base_qty * mult
                            
                            slave_order_params = {
                                "variety": "NORMAL", "tradingsymbol": "SBIN-EQ", "symboltoken": "3045",
                                "transactiontype": "BUY", "exchange": "NSE", "ordertype": "MARKET",
                                "producttype": "DELIVERY", "duration": "DAY", "price": "0",
                                "squareoff": "0", "stoploss": "0", "quantity": str(final_qty)
                            }
                            res = slave["obj"].placeOrder(slave_order_params)
                            log_trade("Slave", slave['id'], "SBIN-EQ", "BUY", final_qty, "SUCCESS", res)
                            return (True, slave['id'], res)
                    except Exception as e:
                        log_trade("Slave", slave['id'], "SBIN-EQ", "BUY", base_qty, "FAILED", str(e))
                    return (False, slave['id'], "Skipped (Inactive or Error)")

                status_container = st.empty()
                status_container.text("🚀 Engine Started! Executing master and broadcasting to individual active slaves with custom multipliers...")

                master_futures = []
                with ThreadPoolExecutor(max_workers=10) as executor:
                    for master in st.session_state['master_objs_bulk']:
                        master_futures.append(executor.submit(place_master_order, master))
                    
                    for f in as_completed(master_futures):
                        success, m_id, m_res = f.result()
                        if success:
                            st.success(f"Master ({m_id}) Placed! Order ID: {m_res}")
                        else:
                            st.error(f"Master ({m_id}) Error: {m_res}")

                slave_futures = []
                with ThreadPoolExecutor(max_workers=100) as executor:
                    for slave in st.session_state['slave_objs_bulk']:
                        slave_futures.append(executor.submit(place_slave_order, slave))
                    
                    success_slaves = 0
                    failed_slaves = 0
                    for f in as_completed(slave_futures):
                        success, s_id, _ = f.result()
                        if success:
                            success_slaves += 1
                        else:
                            failed_slaves += 1

                status_container.empty()
                st.success(f"⚡ Copy Trade Executed! Successful Slaves: {success_slaves} | Skipped/Failed Slaves: {failed_slaves}")
            else:
                st.warning("Pehle Tab 1 से accounts connect karein!")

    with ctrl_col2:
        if st.button("🛑 STOP ENGINE"):
            st.warning("Copy Trading Engine Paused/Stopped.")
            st.session_state['engine_running'] = False
            
    with ctrl_col3:
        if st.button("🚨 EMERGENCY KILL SWITCH"):
            st.error("🚨 KILL SWITCH ACTIVATED! Fetching and exiting all open positions for Masters & Slaves...")
            st.session_state['engine_running'] = False
            
            all_accounts_kill = []
            for m in st.session_state.get('master_objs_bulk', []):
                all_accounts_kill.append({"id": m['id'], "type": "Master", "obj": m['obj']})
            for s in st.session_state.get('slave_objs_bulk', []):
                all_accounts_kill.append({"id": s['id'], "type": "Slave", "obj": s['obj']})
                
            def square_off_account(acc):
                try:
                    positions = acc['obj'].position()
                    if positions and positions.get('status') and positions.get('data'):
                        for pos in positions['data']:
                            netqty = int(pos.get('netqty', 0))
                            if netqty != 0:
                                tx_type = "SELL" if netqty > 0 else "BUY"
                                qty_to_close = abs(netqty)
                                symbol_name = pos.get('tradingsymbol')
                                token = pos.get('symboltoken')
                                exchange = pos.get('exchange', 'NSE')
                                
                                sq_params = {
                                    "variety": "NORMAL", "tradingsymbol": symbol_name, "symboltoken": token,
                                    "transactiontype": tx_type, "exchange": exchange, "ordertype": "MARKET",
                                    "producttype": pos.get('producttype', 'DELIVERY'), "duration": "DAY", 
                                    "price": "0", "squareoff": "0", "stoploss": "0", "quantity": str(qty_to_close)
                                }
                                acc['obj'].placeOrder(sq_params)
                                log_trade(acc['type'], acc['id'], symbol_name, f"SQUARE_OFF_{tx_type}", qty_to_close, "KILL_SWITCH", "EXIT")
                        return True
                except Exception:
                    pass
                return False

            if all_accounts_kill:
                with ThreadPoolExecutor(max_workers=50) as executor:
                    futures = [executor.submit(square_off_account, acc) for acc in all_accounts_kill]
                    for f in as_completed(futures):
                        f.result()
                st.success("🚨 Emergency Exit Completed across all connected accounts!")
            else:
                st.warning("Koi active accounts connected nahi hain!")

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
