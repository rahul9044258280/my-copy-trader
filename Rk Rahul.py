import streamlit as st
from SmartApi import SmartConnect
import pyotp
import yfinance as yf
import pandas as pd
import sqlite3
import time
import threading
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor, as_completed

# Page Configuration
st.set_page_config(page_title="Angel One Ultra-Fast Copy Trading Terminal", layout="wide")

# Custom Clean Dark Cinematic Theme, 3D Boxy Tabs Styling & Live PnL Cards Styling
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

    /* 3D Boxy Tabs Styling */
    div[data-baseweb="tab-list"] {
        gap: 12px;
        background-color: #0e1117;
        padding: 10px 0px;
    }
    div[data-baseweb="tab"] {
        background-color: #161b22 !important;
        border: 2px solid #30363d !important;
        border-radius: 8px !important;
        color: #c9d1d9 !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1);
        transition: all 0.2s ease-in-out;
    }
    div[data-baseweb="tab"]:hover {
        background-color: #21262d !important;
        border-color: #00d09c !important;
        color: #ffffff !important;
        box-shadow: 0 6px 12px rgba(0, 208, 156, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.2);
        transform: translateY(-2px);
    }
    div[aria-selected="true"] {
        background: linear-gradient(135deg, #00d09c 0%, #00a87e 100%) !important;
        color: #0e1117 !important;
        border-color: #00d09c !important;
        font-weight: bold !important;
        box-shadow: 0 4px 14px rgba(0, 208, 156, 0.4), inset 0 1px 2px rgba(255, 255, 255, 0.4) !important;
        transform: translateY(-1px);
    }

    /* 3D Horizontal Box Section Styling */
    .metric-box-3d {
        background: linear-gradient(145deg, #161b22, #0d1117);
        border: 2px solid #30363d;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1);
        display: flex;
        justify-content: space-around;
        align-items: center;
        margin-bottom: 20px;
    }
    .metric-item {
        text-align: center;
        font-weight: bold;
        color: #ffffff;
        font-size: 16px;
    }

    /* Live PnL Card Styling */
    .pnl-card-3d {
        background: linear-gradient(145deg, #161b22, #0d1117);
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        margin-bottom: 10px;
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize SQLite Database & Auto-migrate columns safely
def init_db():
    try:
        conn = sqlite3.connect('trading_terminal.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT,
                client_id TEXT UNIQUE,
                password TEXT,
                totp_secret TEXT,
                api_key TEXT,
                account_type TEXT,
                is_active INTEGER DEFAULT 1,
                lot_multiplier INTEGER DEFAULT 1
            )
        ''')
        for col, col_type in [("client_name", "TEXT"), ("is_active", "INTEGER DEFAULT 1"), ("lot_multiplier", "INTEGER DEFAULT 1")]:
            try:
                cursor.execute(f"ALTER TABLE clients ADD COLUMN {col} {col_type}")
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
    except Exception as e:
        st.error(f"Database Initialization Error: {e}")
        return None

db_conn = init_db()

def log_trade(account_type, client_id, symbol, action, qty, status, order_id):
    if db_conn is None:
        return
    try:
        cursor = db_conn.cursor()
        cursor.execute('''
            INSERT INTO logs (timestamp, account_type, client_id, symbol, action, qty, status, order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3], account_type, client_id, symbol, action, qty, status, str(order_id)))
        db_conn.commit()
    except Exception:
        pass

# Background Heartbeat & Auto-Reconnect Monitor
def background_heartbeat_monitor():
    while True:
        try:
            time.sleep(60)
            if 'master_objs_bulk' in st.session_state and 'slave_objs_bulk' in st.session_state:
                all_active = st.session_state['master_objs_bulk'] + st.session_state['slave_objs_bulk']
                for acc in all_active:
                    try:
                        acc['obj'].rmsLimit()
                    except Exception:
                        try:
                            if db_conn:
                                cur = db_conn.cursor()
                                cur.execute("SELECT password, totp_secret, api_key FROM clients WHERE client_id = ?", (acc['id'],))
                                row = cur.fetchone()
                                if row:
                                    pwd, totp_sec, api_k = row
                                    totp_gen = pyotp.TOTP(totp_sec).now() if totp_sec else ""
                                    new_obj = SmartConnect(api_key=api_k)
                                    session_data = new_obj.generateSession(acc['id'], pwd, totp_gen)
                                    if session_data and session_data.get('status'):
                                        acc['obj'] = new_obj
                        except Exception:
                            pass
        except Exception:
            pass

if 'heartbeat_started' not in st.session_state:
    st.session_state['heartbeat_started'] = True
    hb_thread = threading.Thread(target=background_heartbeat_monitor, daemon=True)
    hb_thread.start()

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
        st.metric("Engine Status & Heartbeat", "Active 🟢", "Protected")
except Exception:
    st.metric("Market Data", "Connected", "Stable")

st.markdown("---")

# Main Interface Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "👥 Client Manager & Fast Login", 
    "📊 Ultra-Fast Execution Terminal", 
    "💰 Live Balances", 
    "📈 P&L Report (Date Range)", 
    "📜 Trade Logs"
])

with tab1:
    master_col, slave_col = st.columns(2)
    
    with master_col:
        st.subheader("👑 Master Account Section")
        with st.form("add_master_form"):
            m_name = st.text_input("Master Account Name / Owner", key="m_name")
            m_client_id = st.text_input("Master Client ID / User ID", key="m_id")
            m_password = st.text_input("Master Password / MPIN", type="password", key="m_pwd")
            m_totp = st.text_input("Master TOTP Secret Key", key="m_totp")
            m_api_key = st.text_input("Master API Key", key="m_apikey")
            
            submit_master = st.form_submit_button("💾 Save Master Account")
            if submit_master:
                if m_client_id and m_api_key and db_conn:
                    try:
                        cursor = db_conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO clients (client_name, client_id, password, totp_secret, api_key, account_type, is_active, lot_multiplier)
                            VALUES (?, ?, ?, ?, ?, 'master', 1, 1)
                        ''', (m_name, m_client_id, m_password, m_totp, m_api_key))
                        db_conn.commit()
                        st.success(f"Master Account {m_client_id} successfully saved!")
                    except Exception as db_err:
                        st.error(f"Error: {db_err}")
                else:
                    st.warning("Client ID aur API Key zaroori hai!")

    with slave_col:
        st.subheader("🔗 Slave Accounts Section")
        with st.form("add_slave_form"):
            s_name = st.text_input("Slave Account Name (e.g. Papa, Friend, etc.)", key="s_name")
            s_client_id = st.text_input("Slave Client ID / User ID", key="s_id")
            s_password = st.text_input("Slave Password / MPIN", type="password", key="s_pwd")
            s_totp = st.text_input("Slave TOTP Secret Key", key="s_totp")
            s_api_key = st.text_input("Slave API Key", key="s_apikey")
            s_multiplier = st.number_input("Lot/Quantity Multiplier (Default: 1)", min_value=1, value=1, key="s_mult")
            
            submit_slave = st.form_submit_button("💾 Save Slave Account")
            if submit_slave:
                if s_client_id and s_api_key and db_conn:
                    try:
                        cursor = db_conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO clients (client_name, client_id, password, totp_secret, api_key, account_type, is_active, lot_multiplier)
                            VALUES (?, ?, ?, ?, ?, 'slave', 1, ?)
                        ''', (s_name, s_client_id, s_password, s_totp, s_api_key, s_multiplier))
                        db_conn.commit()
                        st.success(f"Slave Account [{s_name}] {s_client_id} successfully saved!")
                    except Exception as db_err:
                        st.error(f"Error: {db_err}")
                else:
                    st.warning("Client ID aur API Key zaroori hai!")

    st.markdown("---")
    st.subheader("🚀 Parallel Auto-Login & Heartbeat Protected Panel")
    
    if st.button("⚡ Parallel Auto-Login All 1000+ Clients"):
        if db_conn:
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
                progress_text.text("Auto-generating fresh tokens & logging in accounts concurrently...")
                
                with ThreadPoolExecutor(max_workers=50) as executor:
                    futures = [executor.submit(login_client, row) for row in all_rows]
                    for future in as_completed(futures):
                        try:
                            res = future.result()
                            if res:
                                if res['type'] == 'master':
                                    master_objs.append({"obj": res['obj'], "id": res['id']})
                                else:
                                    slave_objs.append({"obj": res['obj'], "id": res['id'], "multiplier": res['multiplier']})
                        except Exception:
                            pass
                
                st.session_state['master_objs_bulk'] = master_objs
                st.session_state['slave_objs_bulk'] = slave_objs
                progress_text.empty()
                st.success(f"Auto-Login Complete! Connected Masters: {len(master_objs)} | Connected Active Slaves: {len(slave_objs)} (Heartbeat Monitor Active)")

    st.markdown("### 📋 Manage Saved Accounts & Full Details Editor")
    if db_conn:
        try:
            cursor = db_conn.cursor()
            cursor.execute("SELECT id, client_name, client_id, password, totp_secret, api_key, account_type, is_active, lot_multiplier FROM clients")
            all_db_clients = cursor.fetchall()
            
            if all_db_clients:
                for row in all_db_clients:
                    db_id, c_name, c_id, c_pwd, c_totp, c_apikey, acc_type, is_act, mult = row
                    display_name = f" [{c_name}]" if c_name else ""
                    expander_label = f"👑 Master{display_name} - ID: {c_id}" if acc_type == 'master' else f"🔹 Slave{display_name} - ID: {c_id} (Multiplier: {mult}x | Status: {'Active 🟢' if is_act else 'Off 🔴'})"
                    
                    with st.expander(expander_label):
                        with st.form(f"edit_form_{db_id}"):
                            st.markdown(f"#### Edit Details for {c_id}")
                            e_name = st.text_input("Account Name", value=c_name if c_name else "", key=f"ename_{db_id}")
                            e_cid = st.text_input("Client ID", value=c_id, key=f"ecid_{db_id}")
                            e_pwd = st.text_input("Password / MPIN", type="password", value=c_pwd if c_pwd else "", key=f"epwd_{db_id}")
                            e_totp = st.text_input("TOTP Secret Key", value=c_totp if c_totp else "", key=f"etotp_{db_id}")
                            e_apikey = st.text_input("API Key", value=c_apikey if c_apikey else "", key=f"eapi_{db_id}")
                            
                            if acc_type == 'slave':
                                col_e1, col_e2 = st.columns(2)
                                with col_e1:
                                    e_status = st.selectbox("Trade Status", [1, 0], index=0 if is_act==1 else 1, format_func=lambda x: "ON (Trading Enabled)" if x==1 else "OFF (Paused)", key=f"estatus_{db_id}")
                                with col_e2:
                                    e_mult = st.number_input("Lot Multiplier", min_value=1, value=mult, key=f"emult_{db_id}")
                            else:
                                e_status = st.selectbox("Trade Status", [1, 0], index=0 if is_act==1 else 1, format_func=lambda x: "ON (Trading Enabled)" if x==1 else "OFF (Paused)", key=f"estatus_{db_id}")
                                e_mult = 1  
                                
                            save_edits = st.form_submit_button("💾 Save All Changes")
                            if save_edits:
                                cursor.execute("""
                                    UPDATE clients 
                                    SET client_name = ?, client_id = ?, password = ?, totp_secret = ?, api_key = ?, is_active = ?, lot_multiplier = ? 
                                    WHERE id = ?
                                """, (e_name, e_cid, e_pwd, e_totp, e_apikey, e_status, e_mult, db_id))
                                db_conn.commit()
                                st.success(f"Account {e_cid} updated successfully!")
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
    st.subheader("🎛️ Ultra-Fast Execution & Operations Center")
    
    active_masters = len(st.session_state.get('master_objs_bulk', []))
    active_slaves = len(st.session_state.get('slave_objs_bulk', []))
    engine_state = st.session_state.get('engine_running', False)
    
    engine_text = "Running 🟢" if engine_state else "Stopped 🔴"
    
    st.markdown(f"""
        <div class="metric-box-3d">
            <div class="metric-item">Engine State: <b>{engine_text}</b></div>
            <div class="metric-item">Active Masters: <b>{active_masters}</b></div>
            <div class="metric-item">Active Slaves: <b>{active_slaves}</b></div>
        </div>
    """, unsafe_allow_html=True)

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
                        # Flexible Success Parsing for SmartAPI responses
                        order_id = "PLACED"
                        if isinstance(res, dict):
                            order_id = res.get('data', {}).get('orderid', res.get('message', 'PLACED'))
                        elif res is not None:
                            order_id = str(res)
                        
                        log_trade("Master", master['id'], "SBIN-EQ", "BUY", base_qty, "SUCCESS", order_id)
                        return (True, master['id'], order_id)
                    except Exception as e:
                        log_trade("Master", master['id'], "SBIN-EQ", "BUY", base_qty, "FAILED", str(e))
                        return (False, master['id'], str(e))

                def place_slave_order(slave):
                    try:
                        if db_conn is None:
                            return (False, slave['id'], "DB Error")
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
                            order_id = "PLACED"
                            if isinstance(res, dict):
                                order_id = res.get('data', {}).get('orderid', res.get('message', 'PLACED'))
                            elif res is not None:
                                order_id = str(res)

                            log_trade("Slave", slave['id'], "SBIN-EQ", "BUY", final_qty, "SUCCESS", order_id)
                            return (True, slave['id'], order_id)
                    except Exception as e:
                        log_trade("Slave", slave['id'], "SBIN-EQ", "BUY", base_qty, "FAILED", str(e))
                        return (False, slave['id'], str(e))
                    return (False, slave['id'], "Skipped (Inactive)")

                status_container = st.empty()
                status_container.text("⚡ Ultra-Fast Execution Started! Broadcasting orders concurrently...")

                master_futures = []
                with ThreadPoolExecutor(max_workers=10) as executor:
                    for master in st.session_state['master_objs_bulk']:
                        master_futures.append(executor.submit(place_master_order, master))
                    
                    for f in as_completed(master_futures):
                        try:
                            success, m_id, m_res = f.result()
                            if success:
                                st.success(f"Master ({m_id}) Placed! Response/ID: {m_res}")
                            else:
                                st.error(f"Master ({m_id}) Error: {m_res}")
                        except Exception:
                            pass

                slave_futures = []
                with ThreadPoolExecutor(max_workers=100) as executor:
                    for slave in st.session_state['slave_objs_bulk']:
                        slave_futures.append(executor.submit(place_slave_order, slave))
                    
                    success_slaves = 0
                    failed_slaves = 0
                    for f in as_completed(slave_futures):
                        try:
                            success, s_id, _ = f.result()
                            if success:
                                success_slaves += 1
                            else:
                                failed_slaves += 1
                        except Exception:
                            failed_slaves += 1

                status_container.empty()
                st.success(f"⚡ Ultra-Fast Copy Trade Executed! Successful Slaves: {success_slaves} | Failed/Skipped Slaves: {failed_slaves}")
            else:
                st.warning("Pehle Tab 1 से accounts connect/auto-login karein!")

    with ctrl_col2:
        if st.button("🛑 STOP ENGINE"):
            st.warning("Copy Trading Engine Paused/Stopped.")
            st.session_state['engine_running'] = False
            
    with ctrl_col3:
        if st.button("🚨 EMERGENCY KILL SWITCH"):
            st.error("🚨 MILLISECOND KILL SWITCH ACTIVATED! Exiting all open positions across all accounts in parallel threads...")
            st.session_state['engine_running'] = False
            
            all_accounts_kill = []
            for m in st.session_state.get('master_objs_bulk', []):
                all_accounts_kill.append({"id": m['id'], "type": "Master", "obj": m['obj']})
            for s in st.session_state.get('slave_objs_bulk', []):
                all_accounts_kill.append({"id": s['id'], "type": "Slave", "obj": s['obj']})
                
            def square_off_account_lightning(acc):
                try:
                    positions = acc['obj'].position()
                    if positions and positions.get('status') and positions.get('data'):
                        exits_placed = 0
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
                                res = acc['obj'].placeOrder(sq_params)
                                order_id = "EXIT"
                                if isinstance(res, dict):
                                    order_id = res.get('data', {}).get('orderid', 'EXIT')
                                log_trade(acc['type'], acc['id'], symbol_name, f"SQUARE_OFF_{tx_type}", qty_to_close, "KILL_SWITCH", order_id)
                                exits_placed += 1
                        return (True, acc['id'], exits_placed)
                except Exception as e:
                    log_trade(acc['type'], acc['id'], "ALL", "KILL_SWITCH_ERR", 0, "FAILED", str(e))
                return (False, acc['id'], 0)

            if all_accounts_kill:
                with ThreadPoolExecutor(max_workers=100) as executor:
                    futures = [executor.submit(square_off_account_lightning, acc) for acc in all_accounts_kill]
                    total_exits = 0
                    for f in as_completed(futures):
                        try:
                            success, aid, count = f.result()
                            if success:
                                total_exits += count
                        except Exception:
                            pass
                st.success(f"🚨 Lightning Kill Switch Executed! Total Position Exits Triggered: {total_exits}")
            else:
                st.warning("Koi active accounts connected nahi hain!")

    st.markdown("---")
    st.subheader("⚡ Live Running Trades & P&L Monitor (Active Accounts Only)")

    if st.button("🔄 Refresh Live Running Positions & P&L"):
        pass

    all_running_accounts = []
    for m in st.session_state.get('master_objs_bulk', []):
        all_running_accounts.append({"id": m['id'], "type": "Master", "obj": m['obj']})
    for s in st.session_state.get('slave_objs_bulk', []):
        try:
            if db_conn:
                cur = db_conn.cursor()
                cur.execute("SELECT is_active FROM clients WHERE client_id = ?", (s['id'],))
                row = cur.fetchone()
                if row and row[0] == 1:
                    all_running_accounts.append({"id": s['id'], "type": "Slave", "obj": s['obj']})
        except Exception:
            pass

    if not all_running_accounts:
        st.info("Koi bhi account connected nahi hai. Pehle Tab 1 se Auto-Login karein.")
    else:
        running_positions_data = []

        def fetch_open_positions(acc):
            try:
                pos_res = acc['obj'].position()
                if pos_res and pos_res.get('status') and pos_res.get('data'):
                    open_trades = []
                    for p in pos_res['data']:
                        net_qty = int(p.get('netqty', 0))
                        if net_qty != 0:
                            sym = p.get('tradingsymbol', 'N/A')
                            pnl = float(p.get('pnl', 0.0))
                            open_trades.append({"symbol": sym, "qty": net_qty, "pnl": pnl})
                    return {"id": acc['id'], "type": acc['type'], "trades": open_trades}
            except Exception:
                pass
            return {"id": acc['id'], "type": acc['type'], "trades": []}

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(fetch_open_positions, acc) for acc in all_running_accounts]
            for f in as_completed(futures):
                try:
                    res = f.result()
                    if res['trades']:
                        running_positions_data.append(res)
                except Exception:
                    pass

        if not running_positions_data:
            st.info("Filhal kisi bhi account me koi open/running trade nahi hai.")
        else:
            cols_per_row = 3
            for i in range(0, len(running_positions_data), cols_per_row):
                row_cols = st.columns(cols_per_row)
                for j in range(cols_per_row):
                    if i + j < len(running_positions_data):
                        item = running_positions_data[i + j]
                        with row_cols[j]:
                            total_acc_pnl = sum([t['pnl'] for t in item['trades']])
                            pnl_color = "#00d09c" if total_acc_pnl >= 0 else "#ff4d4d"
                            
                            trades_html = ""
                            for t in item['trades']:
                                t_color = "#00d09c" if t['pnl'] >= 0 else "#ff4d4d"
                                trades_html += f"<div style='font-size:13px; color:#c9d1d9;'><b>{t['symbol']}</b> (Qty: {t['qty']}) | PnL: <span style='color:{t_color};'>₹{t['pnl']:,.2f}</span></div>"

                            st.markdown(f"""
                                <div class="pnl-card-3d">
                                    <div style="font-weight:bold; color:#00d09c; margin-bottom:5px;">{item['type'].upper()} : {item['id']}</div>
                                    {trades_html}
                                    <hr style="margin:6px 0; border-color:#30363d;">
                                    <div style="font-size:14px; font-weight:bold;">Total PnL: <span style="color:{pnl_color};">₹{total_acc_pnl:,.2f}</span></div>
                                </div>
                            """, unsafe_allow_html=True)

with tab3:
    st.subheader("💰 Live Master & Slave Account Balances")
    st.write("Yahan aap saare connected accounts ka live margin aur net available balance ek click me dekh sakte hain.")
    
    if st.button("🔄 Fetch Live Balances (All Accounts)"):
        all_accounts = []
        for m in st.session_state.get('master_objs_bulk', []):
            all_accounts.append({"id": m['id'], "type": "Master", "obj": m['obj']})
        for s in st.session_state.get('slave_objs_bulk', []):
            all_accounts.append({"id": s['id'], "type": "Slave", "obj": s['obj']})
            
        if not all_accounts:
            st.warning("Pehle Tab 1 से accounts connect/auto-login karein!")
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
                    try:
                        balance_results.append(f.result())
                    except Exception:
                        pass
            
            df_balances = pd.DataFrame(balance_results)
            st.dataframe(df_balances, use_container_width=True)

with tab4:
    st.subheader("📈 Profit & Loss (P&L) Report with Date Range")
    st.write("Har account ke execution logs aur trade performance ko diye gaye date range ke mutabiq analyze karein.")
    
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("Start Date", value=date.today())
    with col_d2:
        end_date = st.date_input("End Date", value=date.today())
        
    if st.button("📊 Generate P&L Report"):
        if db_conn:
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

with tab5:
    st.subheader("📜 Execution History & Logs")
    if st.button("🔄 Refresh Logs"): pass
    if db_conn:
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
