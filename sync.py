import os
import json
import gspread
import requests
import pandas as pd
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

MILESTONES = [1000, 1500, 1800, 2000, 2200]
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

    students_data = students_ws.get_all_records()
    students_df = pd.DataFrame(students_data)

    history_data = history_ws.get_all_records()
    history_df = pd.DataFrame(history_data) if history_data else pd.DataFrame()

    milestones_data = milestones_ws.get_all_records()
    milestones_df = pd.DataFrame(milestones_data) if milestones_data else pd.DataFrame()

    now = datetime.utcnow()
    date_str = now.strftime('%Y-%m-%d')
    ts_str = now.isoformat()

    new_history = []
    new_milestones = []
    total_students = 0

    for _, row in students_df.iterrows():
        student_id = str(row.get('ID', ''))
        chesscom = str(row.get('Chess.com Nickname', '')).strip()
        lichess = str(row.get('Lichess Nickname', '')).strip()
        name = row.get('Name', '')

        results = []
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

        if results:
            total_students += 1

        for res in results:
            new_history.append([student_id, res['platform'], res['gameType'], res['rating'], date_str, ts_str, res['username']])

            for ms in MILESTONES:
                if res['rating'] >= ms:
                    if not milestones_df.empty:
                        already = milestones_df[
                            (milestones_df['Student ID'].astype(str) == student_id) &
                            (milestones_df['Platform'] == res['platform']) &
                            (milestones_df['Milestone'].astype(str) == str(ms))
                        ]
                    else:
                        already = pd.DataFrame()

                    if already.empty:
                        if not history_df.empty:
                            prev = history_df[
                                (history_df['Student ID'].astype(str) == str(student_id)) &
                                (history_df['Platform'] == res['platform']) &
                                (history_df['Game Type'] == res['gameType'])
                            ]
                            if not prev.empty:
                                try:
                                    prev_rating = float(prev.iloc[-1]['Rating'])
                                    if prev_rating < ms:
                                        new_milestones.append([student_id, res['platform'], ms, date_str, name, res['username']])
                                except:
                                    pass

    if new_history:
        history_ws.append_rows(new_history)
        print(f"Added {len(new_history)} history records")

    if new_milestones:
        milestones_ws.append_rows(new_milestones)
        print(f"Added {len(new_milestones)} milestones")

    milestone_text = ""
    if new_milestones:
        milestone_text = f"\n🏆 *New milestones:*\n"
        for m in new_milestones:
            milestone_text += f"  • {m[4]} reached {m[2]} on {m[1]}\n"

    message = f"♟ *ChessMood Daily Sync Complete*\n✅ Synced {total_students} students\n📊 {len(new_history)} records saved{milestone_text}"
    send_slack(message)
    print("Done!")

if __name__ == "__main__":
    main()
