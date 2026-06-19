import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import requests
import pandas as pd
from datetime import datetime, timedelta
import json
import time

# ==================== CONFIG ====================
MILESTONES = [1000, 1500, 1800, 2000, 2200]
STREAK_THRESHOLD = 100
STREAK_DAYS = 30
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

st.set_page_config(
    page_title="ChessMood Students Progress Tracker",
    page_icon="♟",
    layout="wide"
)

# ==================== STYLING ====================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.stApp { background-color: #0d0f14; color: #e8eaf0; }

.main-title {
    font-family: 'Bebas Neue', sans-serif;
    font-size: 28px;
    letter-spacing: 2px;
    color: #e8eaf0;
}
.main-title span { color: #f0b84b; }

.stat-box {
    background: #161920;
    border: 1px solid #2a2f40;
    border-radius: 14px;
    padding: 20px 24px;
    margin-bottom: 16px;
}
.stat-label {
    font-size: 11px;
    color: #4a5068;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-weight: 600;
    margin-bottom: 8px;
}
.stat-value {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 32px;
    font-weight: 600;
    color: #e8eaf0;
}
.gold { color: #f0b84b; }
.green { color: #3ecf8e; }
.purple { color: #a78bfa; }
.blue { color: #5b9cf6; }

.alert-banner {
    background: linear-gradient(135deg, rgba(240,184,75,0.12), rgba(240,184,75,0.05));
    border: 1px solid rgba(240,184,75,0.3);
    border-radius: 14px;
    padding: 16px 24px;
    margin-bottom: 20px;
}
.alert-title { color: #f0b84b; font-weight: 600; font-size: 15px; margin-bottom: 4px; }
.alert-body { color: #7a8099; font-size: 13px; }

.pill-hot {
    background: rgba(240,184,75,0.15);
    color: #f0b84b;
    border: 1px solid rgba(240,184,75,0.3);
    padding: 3px 10px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 700;
}
.pill-good {
    background: rgba(62,207,142,0.12);
    color: #3ecf8e;
    padding: 3px 10px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 700;
}
.badge-chesscom {
    background: rgba(129,212,77,0.12);
    color: #81d44d;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
}
.badge-lichess {
    background: rgba(91,156,246,0.12);
    color: #5b9cf6;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
}
.ms-2200 { background: rgba(240,184,75,0.25); color: #f0b84b; border: 1px solid rgba(240,184,75,0.5); padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; }
.ms-2000 { background: rgba(240,184,75,0.2); color: #f0b84b; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; }
.ms-1800 { background: rgba(91,156,246,0.15); color: #5b9cf6; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; }
.ms-1500 { background: rgba(167,139,250,0.15); color: #a78bfa; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; }
.ms-1000 { background: rgba(62,207,142,0.12); color: #3ecf8e; padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; }

div[data-testid="stDataFrame"] { background: #161920; border-radius: 16px; }
</style>
""", unsafe_allow_html=True)

# ==================== GOOGLE SHEETS ====================
@st.cache_resource
def get_gsheet_client():
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def get_sheet(tab_name):
    client = get_gsheet_client()
    sheet_id = st.secrets["sheet"]["id"]
    spreadsheet = client.open_by_key(sheet_id)
    return spreadsheet.worksheet(tab_name)

def load_students():
    ws = get_sheet("Students")
    rows = ws.get_all_records()
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df.columns = [c.strip() for c in df.columns]
    df = df[df['Membership Status'].str.lower() == 'active']
    return df.reset_index(drop=True)

def load_history():
    ws = get_sheet("History")
    rows = ws.get_all_records()
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['Student ID','Platform','Game Type','Rating','Date','Timestamp','Username'])

def load_milestones():
    ws = get_sheet("MilestonesLog")
    rows = ws.get_all_records()
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['Student ID','Platform','Milestone','Date','Student Name','Username'])

def append_to_sheet(tab_name, rows):
    ws = get_sheet(tab_name)
    ws.append_rows(rows)

# ==================== CHESS APIs ====================
def fetch_chesscom(username):
    try:
        r = requests.get(f"https://api.chess.com/pub/player/{username}/stats", timeout=10)
        if r.status_code != 200:
            return None
        d = r.json()
        return {
            'rapid': d.get('chess_rapid', {}).get('last', {}).get('rating'),
            'blitz': d.get('chess_blitz', {}).get('last', {}).get('rating'),
            'classical': d.get('chess_daily', {}).get('last', {}).get('rating'),
        }
    except:
        return None

def fetch_lichess(username):
    try:
        r = requests.get(f"https://lichess.org/api/user/{username}", timeout=10)
        if r.status_code != 200:
            return None
        d = r.json()
        perfs = d.get('perfs', {})
        return {
            'rapid': perfs.get('rapid', {}).get('rating'),
            'blitz': perfs.get('blitz', {}).get('rating'),
            'classical': perfs.get('classical', {}).get('rating'),
        }
    except:
        return None

# ==================== SYNC ====================
def sync_all(students_df, history_df, milestones_df):
    now = datetime.utcnow()
    date_str = now.strftime('%Y-%m-%d')
    ts_str = now.isoformat()
    new_history = []
    new_milestones = []

    progress = st.progress(0)
    status = st.empty()
    total = len(students_df)

    for i, row in students_df.iterrows():
        progress.progress((i + 1) / total)
        status.text(f"Syncing {row['Name']} ({i+1}/{total})...")

        student_id = str(row.get('ID', ''))
        results = []

        chesscom = str(row.get('Chess.com Nickname', '')).strip()
        lichess = str(row.get('Lichess Nickname', '')).strip()

        if chesscom:
            data = fetch_chesscom(chesscom)
            if data:
                for gt in ['rapid', 'blitz', 'classical']:
                    if data.get(gt):
                        results.append({'platform': 'Chess.com', 'gameType': gt, 'rating': data[gt], 'username': chesscom})

        if lichess:
            data = fetch_lichess(lichess)
            if data:
                for gt in ['rapid', 'blitz', 'classical']:
                    if data.get(gt):
                        results.append({'platform': 'Lichess', 'gameType': gt, 'rating': data[gt], 'username': lichess})

        for res in results:
            new_history.append([student_id, res['platform'], res['gameType'], res['rating'], date_str, ts_str, res['username']])
            for ms in MILESTONES:
                if res['rating'] >= ms:
                    already = milestones_df[
                        (milestones_df.iloc[:, 0].astype(str) == student_id) &
                        (milestones_df.iloc[:, 1] == res['platform']) &
                        (milestones_df['Milestone'].astype(str) == str(ms))
                    ]
                    if already.empty:
                        prev_entries = history_df[
                            (history_df.iloc[:, 0].astype(str) == str(student_id)) &
                            (history_df['Platform'] == res['platform']) &
                            (history_df['Game Type'] == res['gameType'])
                        ]
                        if not prev_entries.empty:
                            try:
                                prev_rating = float(prev_entries.iloc[-1]['Rating'])
                                if prev_rating < ms:
                                    new_milestones.append([student_id, res['platform'], ms, date_str, row['Name'], res['username']])
                            except (ValueError, TypeError):
                                pass

        time.sleep(0.05)

    if new_history:
        append_to_sheet('History', new_history)
    if new_milestones:
        append_to_sheet('MilestonesLog', new_milestones)

    progress.empty()
    status.empty()
    return len(new_history), len(new_milestones)

# ==================== DATA HELPERS ====================
def get_rating_change(student_id, platform, game_type, history_df):
    entries = history_df[
        (history_df.iloc[:, 0].astype(str) == str(student_id)) &
        (history_df['Platform'] == platform) &
        (history_df['Game Type'] == game_type)
    ].copy()
    if len(entries) < 2:
        return None
    entries['Timestamp'] = pd.to_datetime(entries['Timestamp'], errors='coerce')
    entries = entries.sort_values('Timestamp')
    latest = entries.iloc[-1]
    cutoff = latest['Timestamp'] - timedelta(days=STREAK_DAYS)
    window = entries[entries['Timestamp'] >= cutoff]
    if window.empty:
        return None
    first = window.iloc[0]
    diff = int(latest['Rating']) - int(first['Rating'])
    days = (latest['Timestamp'] - first['Timestamp']).days
    return {'diff': diff, 'days': days, 'latest': int(latest['Rating'])}

def get_top_milestone(student_id, platform, milestones_df):
    mils = milestones_df[
        (milestones_df.iloc[:, 0].astype(str) == str(student_id)) &
        (milestones_df.iloc[:, 1] == platform)
    ]['Milestone'].astype(int).tolist()
    return max(mils) if mils else None

# ==================== MAIN APP ====================
def main():
    # Header
    st.markdown('<div class="main-title">♟ Chess<span>Mood</span> Students Progress Tracker</div>', unsafe_allow_html=True)
    st.markdown("---")

    # Load data
    with st.spinner("Loading data..."):
        try:
            students_df = load_students()
            history_df = load_history()
            milestones_df = load_milestones()
        except Exception as e:
            st.error(f"Could not connect to Google Sheet: {e}")
            st.stop()

    # Sync button
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("↻ Sync Now", type="primary"):
            with st.spinner("Syncing all students..."):
                h_count, m_count = sync_all(students_df, history_df, milestones_df)
                st.success(f"Synced! {h_count} ratings fetched, {m_count} new milestones found.")
                st.cache_data.clear()
                st.rerun()

    # Stats row
    now = datetime.utcnow()
    month_start = now.replace(day=1).strftime('%Y-%m-%d')

    streaks = 0
    if not history_df.empty and not students_df.empty:
        for _, s in students_df.iterrows():
            sid = str(s.get('ID', ''))
            for platform in ['Chess.com', 'Lichess']:
                for gt in ['rapid', 'blitz', 'classical']:
                    ch = get_rating_change(sid, platform, gt, history_df)
                    if ch and ch['diff'] >= STREAK_THRESHOLD:
                        streaks += 1

    ms_this_month = 0
    if not milestones_df.empty:
        ms_this_month = len(milestones_df[milestones_df['Date'] >= month_start])

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="stat-box"><div class="stat-label">Total Students</div><div class="stat-value">{len(students_df)}</div><div style="font-size:12px;color:#3ecf8e">active members only</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-box"><div class="stat-label">Hot Streaks (30d)</div><div class="stat-value gold">{streaks}</div><div style="font-size:12px;color:#f0b84b">+100 in under 30 days</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="stat-box"><div class="stat-label">Milestones Hit</div><div class="stat-value purple">{ms_this_month}</div><div style="font-size:12px;color:#a78bfa">this month</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="stat-box"><div class="stat-label">Platforms Tracked</div><div class="stat-value">2</div><div style="font-size:12px;color:#7a8099">Chess.com · Lichess</div></div>', unsafe_allow_html=True)

    # Filters
    st.markdown("### Filters")
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        filter_type = st.selectbox("Show", ["All", "🔥 Hot Streaks", "🏆 Milestones"])
    with col_f2:
        filter_platform = st.selectbox("Platform", ["All", "Chess.com", "Lichess"])
    with col_f3:
        filter_game = st.selectbox("Game Type", ["All", "Rapid", "Blitz", "Classical"])

    search = st.text_input("🔍 Search by name or username...")

    # Build table
    if students_df.empty:
        st.info("No active students found in the sheet.")
        return

    rows = []
    for _, s in students_df.iterrows():
        sid = str(s.get('ID', ''))
        name = s.get('Name', '')
        chesscom = str(s.get('Chess.com Nickname', '')).strip()
        lichess = str(s.get('Lichess Nickname', '')).strip()

        platforms = []
        if chesscom:
            platforms.append(('Chess.com', chesscom))
        if lichess:
            platforms.append(('Lichess', lichess))

        for platform, username in platforms:
            for gt in ['rapid', 'blitz', 'classical']:
                ch = get_rating_change(sid, platform, gt, history_df)
                top_ms = get_top_milestone(sid, platform, milestones_df)
                profile_url = f"https://chess.com/member/{username}" if platform == 'Chess.com' else f"https://lichess.org/@/{username}"
                rows.append({
                    'Student': name,
                    'Username': f"@{username}",
                    'Platform': platform,
                    'Profile': profile_url,
                    'Game Type': gt.capitalize(),
                    'Rating Change': ch['diff'] if ch else None,
                    'Days': ch['days'] if ch else None,
                    'Milestone': top_ms,
                    'Hot Streak': ch and ch['diff'] >= STREAK_THRESHOLD,
                    '_sid': sid,
                })

    df = pd.DataFrame(rows)

    # Apply filters
    if search:
        mask = df['Student'].str.contains(search, case=False, na=False) | df['Username'].str.contains(search, case=False, na=False)
        df = df[mask]
    if filter_type == "🔥 Hot Streaks":
        df = df[df['Hot Streak'] == True]
    if filter_type == "🏆 Milestones":
        df = df[df['Milestone'].notna()]
    if filter_platform != "All":
        df = df[df['Platform'] == filter_platform]
    if filter_game != "All":
        df = df[df['Game Type'] == filter_game]

    # Display
    st.markdown(f"**{len(df)} results**")

    ms_icons = {2200: '👑', 2000: '⭐', 1800: '★', 1500: '◆', 1000: '●'}

    for _, row in df.iterrows():
            col1, col2, col3, col4, col5, col6 = st.columns([3, 2, 1.5, 2, 2, 1])
            with col1:
                st.markdown(f"**{row['Student']}**  \n`{row['Username']}`")
            with col2:
                badge_class = 'badge-chesscom' if row['Platform'] == 'Chess.com' else 'badge-lichess'
                icon = '♟' if row['Platform'] == 'Chess.com' else '⚡'
                st.markdown(f'<a href="{row["Profile"]}" target="_blank"><span class="{badge_class}">{icon} {row["Platform"]} ↗</span></a>', unsafe_allow_html=True)
            with col3:
                st.markdown(f"<span style='color:#7a8099;font-size:13px'>{row['Game Type']}</span>", unsafe_allow_html=True)
            with col4:
                if row['Rating Change'] is not None:
                    sign = '+' if row['Rating Change'] > 0 else ''
                    if row['Hot Streak']:
                        st.markdown(f'<span class="pill-hot">🔥 {sign}{row["Rating Change"]}</span> <span style="font-size:11px;color:#4a5068">{row["Days"]}d</span>', unsafe_allow_html=True)
                    elif row['Rating Change'] > 0:
                        st.markdown(f'<span class="pill-good">{sign}{row["Rating Change"]}</span>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<span style="color:#4a5068">{sign}{row["Rating Change"]}</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span style="color:#4a5068">—</span>', unsafe_allow_html=True)
            with col5:
                if row['Milestone']:
                    try:
                        ms = int(float(row['Milestone']))
                    except (ValueError, TypeError):
                        ms = None
                    if ms:
                        ms_class = f'ms-{ms}'
                        icon = ms_icons.get(ms, '')
                        st.markdown(f'<span class="{ms_class}">{icon} {ms}</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span style="color:#4a5068">—</span>', unsafe_allow_html=True)
            with col6:
                pass
    with st.sidebar:
            st.markdown("### 🏆 Milestones This Month")
            for ms in [2200, 2000, 1800, 1500, 1000]:
                count = 0
                if not milestones_df.empty:
                    count = len(milestones_df[
                        (milestones_df['Date'] >= month_start) &
                        (milestones_df['Milestone'].astype(str) == str(ms))
                    ])
                st.metric(label=f"{ms_icons.get(ms,'')} {ms}+", value=count)

            st.markdown("---")
            st.markdown("### ⚙ Settings")
            st.markdown(f"**Students tracked:** {len(students_df)}")
            st.markdown(f"**History records:** {len(history_df)}")
if __name__ == "__main__":
    main()
