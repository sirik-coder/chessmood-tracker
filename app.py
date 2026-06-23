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

# Chess.com's API blocks requests without a descriptive User-Agent (Cloudflare 403).
API_HEADERS = {'User-Agent': 'ChessMood-Tracker/1.0 (contact: sirik@chessmood.com)'}

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

/* Sort button (popover trigger) — gold-tinted so it's clearly a button, not a faint white icon */
div[data-testid="stPopover"] button {
    background-color: rgba(240,184,75,0.12) !important;
    color: #f0b84b !important;
    border: 1px solid rgba(240,184,75,0.45) !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
}
div[data-testid="stPopover"] button:hover {
    background-color: rgba(240,184,75,0.22) !important;
    border-color: #f0b84b !important;
    color: #f0b84b !important;
}
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

@st.cache_data(ttl=600)
def load_students():
    ws = get_sheet("Students")
    rows = ws.get_all_records()
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df.columns = [c.strip() for c in df.columns]
    df = df[df['Membership Status'].str.lower() == 'active']
    return df.reset_index(drop=True)

@st.cache_data(ttl=600)
def load_history():
    ws = get_sheet("History")
    rows = ws.get_all_records()
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['Student ID','Platform','Game Type','Rating','Date','Timestamp','Username'])

@st.cache_data(ttl=600)
def load_milestones():
    ws = get_sheet("MilestonesLog")
    rows = ws.get_all_records()
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=['Student ID','Platform','Milestone','Date','Student Name','Username'])

@st.cache_data(ttl=600)
def load_hotstreaks():
    # HotStreaksLog is created by sync.py; return empty if it doesn't exist yet.
    try:
        ws = get_sheet("HotStreaksLog")
    except Exception:
        return pd.DataFrame()
    rows = ws.get_all_records()
    return pd.DataFrame(rows) if rows else pd.DataFrame()

def append_to_sheet(tab_name, rows):
    ws = get_sheet(tab_name)
    ws.append_rows(rows)

# ==================== CHESS APIs ====================
def fetch_chesscom(username):
    try:
        r = requests.get(f"https://api.chess.com/pub/player/{username}/stats", headers=API_HEADERS, timeout=10)
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
        r = requests.get(f"https://lichess.org/api/user/{username}", headers=API_HEADERS, timeout=10)
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

# ============ PRECOMPUTED LOOKUPS (cached — one pass instead of per-cell scans) ============
@st.cache_data(ttl=600)
def compute_rating_changes(history_df):
    """Return {(student_id, platform, game_type): {'diff','days','latest'}} in a single pass.
    Mirrors get_rating_change() exactly, but computed once for the whole sheet."""
    changes = {}
    if history_df is None or history_df.empty:
        return changes
    h = history_df.copy()
    h['_sid'] = h.iloc[:, 0].astype(str)
    h['_ts'] = pd.to_datetime(h['Timestamp'], errors='coerce')
    h = h.dropna(subset=['_ts'])
    for (sid, platform, gt), grp in h.groupby(['_sid', 'Platform', 'Game Type']):
        if len(grp) < 2:
            continue
        grp = grp.sort_values('_ts')
        latest = grp.iloc[-1]
        cutoff = latest['_ts'] - timedelta(days=STREAK_DAYS)
        window = grp[grp['_ts'] >= cutoff]
        if window.empty:
            continue
        first = window.iloc[0]
        try:
            diff = int(latest['Rating']) - int(first['Rating'])
        except (ValueError, TypeError):
            continue
        days = (latest['_ts'] - first['_ts']).days
        changes[(sid, platform, gt)] = {'diff': diff, 'days': days, 'latest': int(latest['Rating'])}
    return changes

@st.cache_data(ttl=600)
def compute_top_milestones(milestones_df):
    """Return {(student_id, platform): top_milestone_int} in a single pass."""
    tops = {}
    if milestones_df is None or milestones_df.empty:
        return tops
    m = milestones_df.copy()
    m['_sid'] = m.iloc[:, 0].astype(str)
    m['_plat'] = m.iloc[:, 1]
    for (sid, platform), grp in m.groupby(['_sid', '_plat']):
        try:
            tops[(sid, platform)] = int(grp['Milestone'].astype(int).max())
        except (ValueError, TypeError):
            continue
    return tops

@st.cache_data(ttl=600)
def build_base(_students_df, _history_df, _milestones_df, sig):
    """Build the flat per-(student, platform, game-type) table + hot-streak count once.
    The DataFrame args are underscore-prefixed so Streamlit skips hashing them; `sig`
    (a cheap row-count tuple) is the cache key — so this only rebuilds when data changes,
    not on every filter/sort/paging rerun."""
    changes = compute_rating_changes(_history_df)
    tops = compute_top_milestones(_milestones_df)

    streaks = 0
    if not _history_df.empty and not _students_df.empty:
        for s in _students_df.to_dict('records'):
            sid = str(s.get('ID', ''))
            for platform in ['Chess.com', 'Lichess']:
                for gt in ['rapid', 'blitz', 'classical']:
                    ch = changes.get((sid, platform, gt))
                    if ch and ch['diff'] >= STREAK_THRESHOLD:
                        streaks += 1

    rows = []
    for s in _students_df.to_dict('records'):
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
                ch = changes.get((sid, platform, gt))
                top_ms = tops.get((sid, platform))
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
    return pd.DataFrame(rows), streaks

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

    # Build the flat table + hot-streak count once (cached on data size) so reruns from
    # filters / sort / paging don't rebuild ~4,000 rows every time.
    data_sig = (len(students_df), len(history_df), len(milestones_df))
    base_df, streaks = build_base(students_df, history_df, milestones_df, data_sig)

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

    # Click-to-view detail tables for the Hot Streaks and Milestones cards.
    # Rendered as HTML so the Platform cell can link to the player's account AND rows reached
    # TODAY are highlighted green with a "NEW" tag.
    st.markdown("""
    <style>
    .cm-tbl { width:100%; border-collapse:collapse; font-size:14px; }
    .cm-tbl th { text-align:left; color:#7a8099; font-weight:600; font-size:11px; text-transform:uppercase;
                 letter-spacing:.5px; padding:6px 10px; border-bottom:1px solid #2a2f40; }
    .cm-tbl td { padding:8px 10px; border-bottom:1px solid #1c1f29; color:#e8eaf0; }
    .cm-tbl a { color:#5b9cf6; text-decoration:none; }
    .cm-tbl tr.cm-new td { background:rgba(62,207,142,0.12); }
    .cm-tbl tr.cm-new td:first-child { border-left:3px solid #3ecf8e; }
    .cm-new-tag { background:#3ecf8e; color:#0d0f14; font-size:10px; font-weight:700;
                  padding:1px 6px; border-radius:6px; margin-left:8px; }
    </style>
    """, unsafe_allow_html=True)

    def _esc(v):
        return str(v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def _platform_cell(platform, username):
        u = _esc(str(username).lstrip('@'))
        url = f"https://www.chess.com/member/{u}" if platform == 'Chess.com' else f"https://lichess.org/@/{u}"
        return f'<a href="{url}" target="_blank">{_esc(platform)} ↗</a>'

    today_str = now.strftime('%Y-%m-%d')
    # Hot streaks the sync logged TODAY (so we know which are new) — keyed (sid, platform, gametype).
    hotlog = load_hotstreaks()
    new_hot_keys = set()
    if not hotlog.empty and 'Date' in hotlog.columns:
        for _, h in hotlog[hotlog['Date'].astype(str) == today_str].iterrows():
            new_hot_keys.add((str(h.get('Student ID', '')), str(h.get('Platform', '')), str(h.get('Game Type', '')).lower()))

    with st.expander(f"🔥 View hot streaks ({streaks})", expanded=False):
        hs = base_df[base_df['Hot Streak'] == True].sort_values('Rating Change', ascending=False) if 'Hot Streak' in base_df.columns else pd.DataFrame()
        if not hs.empty:
            body = []
            for _, r in hs.iterrows():
                is_new = (str(r['_sid']), r['Platform'], str(r['Game Type']).lower()) in new_hot_keys
                cls = ' class="cm-new"' if is_new else ''
                tag = '<span class="cm-new-tag">NEW</span>' if is_new else ''
                rc = r['Rating Change']
                rc_str = f"+{int(rc)}" if pd.notna(rc) else "—"
                days = int(r['Days']) if pd.notna(r['Days']) else "—"
                body.append(
                    f'<tr{cls}><td>{_esc(r["Student"])}{tag}</td>'
                    f'<td>{_platform_cell(r["Platform"], r["Username"])}</td>'
                    f'<td>{_esc(r["Game Type"])}</td><td>{rc_str}</td><td>{days}</td></tr>'
                )
            st.html('<table class="cm-tbl"><thead><tr><th>Student</th><th>Platform</th><th>Game Type</th>'
                    '<th>Rating Change</th><th>Days</th></tr></thead><tbody>' + ''.join(body) + '</tbody></table>')
        else:
            st.caption(f"No hot streaks right now (+{STREAK_THRESHOLD} in under {STREAK_DAYS} days).")

    with st.expander(f"🏆 View milestones this month ({ms_this_month})", expanded=False):
        if ms_this_month > 0:
            mtm = milestones_df[milestones_df['Date'] >= month_start].copy()
            namecol = 'Student Name' if 'Student Name' in mtm.columns else ('Name' if 'Name' in mtm.columns else None)
            if 'Milestone' in mtm.columns:
                mtm = mtm.sort_values('Milestone', ascending=False)
            body = []
            for _, r in mtm.iterrows():
                is_new = str(r.get('Date', '')) == today_str
                cls = ' class="cm-new"' if is_new else ''
                tag = '<span class="cm-new-tag">NEW</span>' if is_new else ''
                student = _esc(r.get(namecol, '')) if namecol else ''
                body.append(
                    f'<tr{cls}><td>{student}{tag}</td>'
                    f'<td>{_platform_cell(r.get("Platform", ""), r.get("Username", ""))}</td>'
                    f'<td>{_esc(r.get("Milestone", ""))}</td><td>{_esc(r.get("Date", ""))}</td></tr>'
                )
            st.html('<table class="cm-tbl"><thead><tr><th>Student</th><th>Platform</th><th>Milestone</th>'
                    '<th>Date</th></tr></thead><tbody>' + ''.join(body) + '</tbody></table>')
        else:
            st.caption("No milestones reached yet this month.")

    search = st.text_input("🔍 Search by name or username...")

    # Build table
    if students_df.empty:
        st.info("No active students found in the sheet.")
        return

    # Base table is prebuilt & cached above; reference it (filters are applied next).
    df = base_df

    # Apply search
    if search:
        mask = df['Student'].str.contains(search, case=False, na=False) | df['Username'].str.contains(search, case=False, na=False)
        df = df[mask]

    # ---- Sort control (icon button) sits next to the results count, above the list ----
    sort_options = ["Default", "Biggest gains first", "Alphabetical"]
    _, sort_col = st.columns([8, 1.6])
    with sort_col:
        with st.popover("↕ Sort", use_container_width=True):
            sort_mode = st.radio("Sort by", sort_options, key="student_sort_mode")

    unique_students = int(df['_sid'].nunique()) if not df.empty else 0

    # ---- Group the (already filtered) rows into one card per student (single O(n) pass) ----
    groups = []
    if not df.empty:
        order, by_sid = [], {}
        for r in df.to_dict('records'):
            sid = r['_sid']
            if sid not in by_sid:
                by_sid[sid] = {'name': r['Student'], 'plat': {}, 'rows': [], 'max_gain': None}
                order.append(sid)
            grp = by_sid[sid]
            grp['rows'].append(r)
            grp['plat'].setdefault(r['Platform'], r['Profile'])
            rc = r['Rating Change']
            if rc is not None and pd.notna(rc):
                grp['max_gain'] = rc if grp['max_gain'] is None else max(grp['max_gain'], rc)
        groups = [
            {'name': by_sid[s]['name'], 'platforms': list(by_sid[s]['plat'].items()),
             'rows': by_sid[s]['rows'], 'max_gain': by_sid[s]['max_gain']}
            for s in order
        ]

    if sort_mode == "Biggest gains first":
        groups.sort(key=lambda x: (x['max_gain'] is not None, x['max_gain'] if x['max_gain'] is not None else 0), reverse=True)
    elif sort_mode == "Alphabetical":
        groups.sort(key=lambda x: str(x['name']).lower())

    # Layout styling for the grouped cards (badges / pills / milestone classes are reused unchanged)
    st.markdown("""
    <style>
    .cm-student { border-bottom:1px solid #1c1f29; }
    .cm-student > summary { cursor:pointer; padding:8px 2px; font-weight:600; color:#e8eaf0; font-size:15px; }
    .cm-student > summary:hover { background:#12151c; }
    .cm-name { margin-right:12px; }
    .cm-detail { padding:4px 0 12px 24px; }
    .cm-detail-row { display:flex; align-items:center; gap:16px; padding:4px 0; }
    .cm-gt { color:#7a8099; font-size:13px; min-width:140px; }
    </style>
    """, unsafe_allow_html=True)

    ms_icons = {2200: '👑', 2000: '⭐', 1800: '★', 1500: '◆', 1000: '●'}

    def pill_html(row):
        rc = row['Rating Change']
        if rc is not None and pd.notna(rc):
            sign = '+' if rc > 0 else ''
            if row['Hot Streak']:
                return f'<span class="pill-hot">🔥 {sign}{rc}</span> <span style="font-size:11px;color:#4a5068">{row["Days"]}d</span>'
            elif rc > 0:
                return f'<span class="pill-good">{sign}{rc}</span>'
            return f'<span style="color:#4a5068">{sign}{rc}</span>'
        return '<span style="color:#4a5068">—</span>'

    def ms_html(row):
        if row['Milestone'] is not None and pd.notna(row['Milestone']) and row['Milestone'] != '':
            try:
                ms = int(float(row['Milestone']))
            except (ValueError, TypeError):
                ms = None
            if ms:
                return f'<span class="ms-{ms}">{ms_icons.get(ms, "")} {ms}</span>'
        return '<span style="color:#4a5068">—</span>'

    def badge_html(platform, profile):
        badge_class = 'badge-chesscom' if platform == 'Chess.com' else 'badge-lichess'
        icon = '♟' if platform == 'Chess.com' else '⚡'
        return f'<a href="{profile}" target="_blank"><span class="{badge_class}">{icon} {platform} ↗</span></a>'

    # ---- One collapsible card per student, paginated so only ~PER_PAGE render per view ----
    PER_PAGE = 50
    with st.expander(f"👥 View Students ({unique_students})", expanded=False):
        if not groups:
            st.caption("No students match your filters.")
        else:
            total = len(groups)
            n_pages = (total + PER_PAGE - 1) // PER_PAGE
            page = 1
            if n_pages > 1:
                # Key encodes the filters so the page resets to 1 whenever the result set changes.
                page_key = f"pg_{sort_mode}_{search}"
                info_col, pg_col = st.columns([3, 1])
                with pg_col:
                    page = int(st.number_input("Page", min_value=1, max_value=n_pages, value=1, step=1, key=page_key))
                with info_col:
                    lo = (page - 1) * PER_PAGE + 1
                    hi = min(page * PER_PAGE, total)
                    st.caption(f"Showing {lo}–{hi} of {total} · page {page}/{n_pages}")
            page_groups = groups[(page - 1) * PER_PAGE: page * PER_PAGE]
            cards = []
            for grp in page_groups:
                badges = ' '.join(badge_html(p, url) for p, url in grp['platforms'])
                detail = []
                for row in grp['rows']:
                    p_icon = '♟' if row['Platform'] == 'Chess.com' else '⚡'
                    detail.append(
                        f'<div class="cm-detail-row">'
                        f'<span class="cm-gt">{p_icon} {row["Game Type"]}</span>'
                        f'<span>{pill_html(row)}</span>'
                        f'<span>{ms_html(row)}</span>'
                        f'</div>'
                    )
                cards.append(
                    f'<details class="cm-student">'
                    f'<summary><span class="cm-name">{grp["name"]}</span>{badges}</summary>'
                    f'<div class="cm-detail">{"".join(detail)}</div>'
                    f'</details>'
                )
            st.html(''.join(cards))
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
