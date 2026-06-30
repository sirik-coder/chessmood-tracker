import os
import json
import gspread
import requests
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

MILESTONES = [1000, 1500, 1800, 2000, 2200]
STREAK_THRESHOLD = 100   # rating points gained...
STREAK_DAYS = 30         # ...within this many days = a "hot streak"
# A genuine streak is many games worth a normal ~7-10 pts each. After a long break
# a player's rating is uncertain and each win can be worth tens of points (e.g. +100
# from 4 games). If the gain averages MORE than this many points per game, we treat
# it as post-break "recovery" noise and do NOT report it as a hot streak.
MAX_POINTS_PER_GAME = 15
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Chess.com's API blocks requests without a descriptive User-Agent (Cloudflare 403).
API_HEADERS = {'User-Agent': 'ChessMood-Tracker/1.0 (contact: sirik@chessmood.com)'}

def get_client():
    creds_json = os.environ['GCP_SERVICE_ACCOUNT_JSON']
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)

def get_sheet(client, tab_name):
    sheet_id = os.environ['SHEET_ID']
    spreadsheet = client.open_by_key(sheet_id)
    return spreadsheet.worksheet(tab_name)

def fetch_chesscom(username):
    try:
        r = requests.get(f"https://api.chess.com/pub/player/{username}/stats", headers=API_HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        d = r.json()
        out = {}
        for gt, key in [('rapid', 'chess_rapid'), ('blitz', 'chess_blitz'), ('classical', 'chess_daily')]:
            blk = d.get(key, {})
            rating = blk.get('last', {}).get('rating')
            if rating:
                best = blk.get('best', {})
                out[gt] = {'rating': rating, 'best': best.get('rating'), 'best_ts': best.get('date')}
        return out
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

def platform_prior_max(res):
    """The player's best rating in this game type strictly BEFORE today, from the platform's
    own all-time history. Lets us confirm a milestone is genuinely first-time-ever, since our
    own History only goes back to when tracking started. Returns None if it can't be determined
    (in which case we fall back to our tracked history and do NOT suppress)."""
    today = datetime.utcnow().date()
    if res['platform'] == 'Chess.com':
        # Chess.com's stats response already includes the all-time best + the date it was set.
        best, best_ts = res.get('best'), res.get('best_ts')
        if best and best_ts:
            try:
                if datetime.utcfromtimestamp(best_ts).date() < today:
                    return best
            except (ValueError, TypeError, OSError):
                return None
        return None
    # Lichess: full daily rating history is available; take the max recorded before today.
    try:
        r = requests.get(f"https://lichess.org/api/user/{res['username']}/rating-history",
                         headers=API_HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        target = {'rapid': 'Rapid', 'blitz': 'Blitz', 'classical': 'Classical'}.get(res['gameType'])
        for perf in r.json():
            if perf.get('name') == target:
                mx = None
                for p in perf.get('points', []):  # [year, month(0-based), day, rating]
                    try:
                        pdate = datetime(p[0], p[1] + 1, p[2]).date()
                    except (ValueError, TypeError, IndexError):
                        continue
                    if pdate < today:
                        mx = p[3] if mx is None else max(mx, p[3])
                return mx
        return None
    except:
        return None

def chesscom_games_since(username, game_type, since_dt):
    """Count RATED Chess.com games of this type played since since_dt. Returns None on failure."""
    tc = {'rapid': 'rapid', 'blitz': 'blitz', 'classical': 'daily'}.get(game_type)
    if not tc:
        return None
    try:
        r = requests.get(f"https://api.chess.com/pub/player/{username}/games/archives",
                         headers=API_HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        archives = r.json().get('archives', [])
        since_ts = int(since_dt.timestamp())
        count = 0
        for url in archives[-2:]:  # current + previous month covers the 30-day window
            ar = requests.get(url, headers=API_HEADERS, timeout=15)
            if ar.status_code != 200:
                continue
            for g in ar.json().get('games', []):
                if (g.get('time_class') == tc and g.get('rated')
                        and g.get('end_time', 0) >= since_ts):
                    count += 1
        return count
    except Exception:
        return None

def lichess_games_since(username, game_type, since_dt):
    """Count RATED Lichess games of this type played since since_dt. Returns None on failure."""
    perf = {'rapid': 'rapid', 'blitz': 'blitz', 'classical': 'classical'}.get(game_type)
    if not perf:
        return None
    try:
        since_ms = int(since_dt.timestamp() * 1000)
        r = requests.get(
            f"https://lichess.org/api/games/user/{username}",
            params={'since': since_ms, 'perfType': perf, 'rated': 'true',
                    'moves': 'false', 'tags': 'false', 'pgnInJson': 'false', 'max': 300},
            headers={**API_HEADERS, 'Accept': 'application/x-ndjson'},
            timeout=20, stream=True)
        if r.status_code != 200:
            return None
        count = 0
        for line in r.iter_lines():
            if line:
                count += 1
        return count
    except Exception:
        return None

def games_in_window(platform, username, game_type, since_dt):
    """Number of rated games played since since_dt — used to reject post-break 'recovery' jumps."""
    if platform == 'Chess.com':
        return chesscom_games_since(username, game_type, since_dt)
    return lichess_games_since(username, game_type, since_dt)

def get_email(row):
    """Find the student's email from the sheet row, matching any header that
    contains 'email' (e.g. 'Email', 'Email Address'). Returns '' if absent."""
    for key, val in row.items():
        if 'email' in str(key).strip().lower():
            v = str(val).strip()
            if v and v.lower() != 'nan':
                return v
    return ''

def send_slack(message):
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    if not webhook_url:
        return
    requests.post(webhook_url, json={"text": message}, timeout=10)

def main():
    print("Starting sync...")
    client = get_client()

    students_ws = get_sheet(client, 'Students')
    history_ws = get_sheet(client, 'History')
    milestones_ws = get_sheet(client, 'MilestonesLog')
    try:
        hotstreaks_ws = get_sheet(client, 'HotStreaksLog')
    except gspread.exceptions.WorksheetNotFound:
        hotstreaks_ws = client.open_by_key(os.environ['SHEET_ID']).add_worksheet(title='HotStreaksLog', rows=2000, cols=8)
        hotstreaks_ws.append_row(['Student ID', 'Platform', 'Game Type', 'Change', 'Days', 'Date', 'Name', 'Username'])

    students_data = students_ws.get_all_records()
    students_df = pd.DataFrame(students_data)
    # Track ONLY active members (our students) — matches the dashboard; skip none/paused/canceled.
    if not students_df.empty:
        students_df.columns = [c.strip() for c in students_df.columns]
        if 'Membership Status' in students_df.columns:
            students_df = students_df[students_df['Membership Status'].str.lower() == 'active'].reset_index(drop=True)

    history_data = history_ws.get_all_records()
    history_df = pd.DataFrame(history_data) if history_data else pd.DataFrame()

    milestones_data = milestones_ws.get_all_records()
    milestones_df = pd.DataFrame(milestones_data) if milestones_data else pd.DataFrame()

    hotstreaks_data = hotstreaks_ws.get_all_records()
    hotstreaks_df = pd.DataFrame(hotstreaks_data) if hotstreaks_data else pd.DataFrame()

    now = datetime.utcnow()
    date_str = now.strftime('%Y-%m-%d')
    ts_str = now.isoformat()

    new_history = []
    new_milestones = []
    new_hotstreaks = []
    total_students = 0

    # Hot streaks already notified within the last STREAK_DAYS days, so we don't repeat one daily.
    streak_cutoff_date = (now - timedelta(days=STREAK_DAYS)).strftime('%Y-%m-%d')
    recent_hot = set()
    if not hotstreaks_df.empty:
        for _, h in hotstreaks_df.iterrows():
            if str(h.get('Date', '')) >= streak_cutoff_date:
                recent_hot.add((str(h.get('Student ID', '')), h.get('Platform', ''), h.get('Game Type', '')))

    for _, row in students_df.iterrows():
        student_id = str(row.get('ID', ''))
        chesscom = str(row.get('Chess.com Nickname', '')).strip()
        lichess = str(row.get('Lichess Nickname', '')).strip()
        name = row.get('Name', '')
        email = get_email(row)

        results = []
        if chesscom:
            data = fetch_chesscom(chesscom)
            if data:
                for gt in ['rapid', 'blitz', 'classical']:
                    if gt in data:
                        info = data[gt]
                        results.append({'platform': 'Chess.com', 'gameType': gt, 'rating': info['rating'],
                                        'username': chesscom, 'best': info['best'], 'best_ts': info['best_ts']})

        if lichess:
            data = fetch_lichess(lichess)
            if data:
                for gt in ['rapid', 'blitz', 'classical']:
                    if data.get(gt):
                        results.append({'platform': 'Lichess', 'gameType': gt, 'rating': data[gt],
                                        'username': lichess, 'best': None, 'best_ts': None})

        if results:
            total_students += 1

        for res in results:
            new_history.append([student_id, res['platform'], res['gameType'], res['rating'], date_str, ts_str, res['username']])

            # First-time milestone detection — PER (student, platform, game type).
            # A milestone is "newly reached" only when the player's best PRIOR rating in this
            # exact game type was below it and the current rating is at/above it. Using the max
            # of all prior history (not just the last point, and not a platform-wide flag that
            # conflates rapid/blitz/classical) is what makes first-time detection correct.
            current_rating = res['rating']
            prev = None
            if not history_df.empty:
                p = history_df[
                    (history_df['Student ID'].astype(str) == student_id) &
                    (history_df['Platform'] == res['platform']) &
                    (history_df['Game Type'] == res['gameType'])
                ]
                if not p.empty:
                    prev = p

            # --- First-time milestone detection ---
            if prev is not None:
                prev_max = pd.to_numeric(prev['Rating'], errors='coerce').max()
                if pd.notna(prev_max):
                    candidate_ms = [ms for ms in MILESTONES if prev_max < ms <= current_rating]
                    if candidate_ms:
                        # Our History only goes back to tracking start, so a crossing here might not be
                        # the player's first time EVER (they may have reached it earlier, then dipped).
                        # Confirm against the platform's all-time history before flagging it.
                        plat_prior = platform_prior_max(res)
                        for ms in candidate_ms:
                            true_prior = prev_max if plat_prior is None else max(prev_max, plat_prior)
                            if true_prior < ms:
                                new_milestones.append({
                                    'sid': student_id,
                                    'platform': res['platform'],
                                    'gameType': res['gameType'],
                                    'ms': ms,
                                    'name': name,
                                    'email': email,
                                    'username': res['username'],
                                })

            # --- Hot streak detection: gained >= STREAK_THRESHOLD within the rolling window ---
            if prev is not None:
                w = prev.copy()
                w['_ts'] = pd.to_datetime(w['Timestamp'], errors='coerce')
                w = w.dropna(subset=['_ts'])
                w = w[w['_ts'] >= (now - timedelta(days=STREAK_DAYS))]
                if not w.empty:
                    first = w.sort_values('_ts').iloc[0]
                    try:
                        gain = int(current_rating - float(first['Rating']))
                        days = (pd.Timestamp(now) - first['_ts']).days
                    except (ValueError, TypeError):
                        gain = None
                    if gain is not None and gain >= STREAK_THRESHOLD:
                        key = (student_id, res['platform'], res['gameType'])
                        if key not in recent_hot:   # not already notified in the last STREAK_DAYS
                            # Reject post-break "recovery" jumps: count the games that actually
                            # produced the gain. A real streak is many games at a normal pace;
                            # +100 from a handful of games (tens of points each) is RD recovery.
                            ts0 = pd.Timestamp(first['_ts'])
                            if ts0.tzinfo is None:
                                ts0 = ts0.tz_localize('UTC')
                            ngames = games_in_window(res['platform'], res['username'],
                                                     res['gameType'], ts0.to_pydatetime())
                            looks_like_recovery = ngames is not None and (
                                ngames == 0 or (gain / ngames) > MAX_POINTS_PER_GAME)
                            if looks_like_recovery:
                                print(f"Skipped recovery jump: {name} +{gain} from {ngames} "
                                      f"games ({res['platform']} {res['gameType']})")
                            else:
                                recent_hot.add(key)
                                new_hotstreaks.append({
                                    'sid': student_id,
                                    'platform': res['platform'],
                                    'gameType': res['gameType'],
                                    'gain': gain,
                                    'days': days,
                                    'games': ngames,
                                    'name': name,
                                    'email': email,
                                    'username': res['username'],
                                })

    if new_history:
        history_ws.append_rows(new_history)
        print(f"Added {len(new_history)} history records")

    if new_milestones:
        milestone_rows = [[m['sid'], m['platform'], m['ms'], date_str, m['name'], m['username']] for m in new_milestones]
        milestones_ws.append_rows(milestone_rows)
        print(f"Added {len(new_milestones)} milestones")

    if new_hotstreaks:
        hot_rows = [[h['sid'], h['platform'], h['gameType'], h['gain'], h['days'], date_str, h['name'], h['username']] for h in new_hotstreaks]
        hotstreaks_ws.append_rows(hot_rows)
        print(f"Added {len(new_hotstreaks)} hot streaks")

    def profile_url(platform, username):
        return f"https://www.chess.com/member/{username}" if platform == 'Chess.com' else f"https://lichess.org/@/{username}"

    def email_tag(rec):
        return f" (✉ {rec['email']})" if rec.get('email') else ""

    milestone_text = ""
    if new_milestones:
        milestone_text = "\n🏆 *New milestones reached:*\n"
        for m in new_milestones:
            gt_label = m['gameType'].capitalize()
            milestone_text += f"  • *{m['name']}*{email_tag(m)} reached *{m['ms']}* in {gt_label} ({m['platform']}) — <{profile_url(m['platform'], m['username'])}|View profile ↗>\n"

    streak_text = ""
    if new_hotstreaks:
        streak_text = f"\n🔥 *New hot streaks (+{STREAK_THRESHOLD} in under {STREAK_DAYS} days):*\n"
        for h in new_hotstreaks:
            gt_label = h['gameType'].capitalize()
            games_part = f", {h['games']} games" if h.get('games') is not None else ""
            streak_text += f"  • *{h['name']}*{email_tag(h)} +{h['gain']} in {gt_label} over {h['days']}d{games_part} ({h['platform']}) — <{profile_url(h['platform'], h['username'])}|View profile ↗>\n"

    message = f"♟ *ChessMood Daily Sync Complete*\n✅ Synced {total_students} students\n📊 {len(new_history)} records saved{milestone_text}{streak_text}"
    send_slack(message)
    print("Done!")

if __name__ == "__main__":
    main()
