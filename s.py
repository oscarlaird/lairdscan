#%%
# python3 -m pip install pandas nest_asyncio pandas fastapi uvicorn[standard] openpyxl --break-system-packages
import sqlite3
import requests
import pandas as pd
from cpac_scanner import fetch_ratings
import base64
import json

# Create/connect to database
conn = sqlite3.connect(':memory:')
cursor = conn.cursor()

#%%
api_key = "1044f606ddae7161c0dd3271961d7ffa"
example_session_id = 2007
example_person_name = "Terry Alexander"
example_people_id = 2202
example_roll_call_id = 1437226
example_roll_call_id_2 = 1423115 
example_roll_call_id_3 = 1440286
example_roll_call_ids = [example_roll_call_id, example_roll_call_id_2, example_roll_call_id_3]
def fetch_sessions_list(state, year):
    # https://api.legiscan.com/?key=1044f606ddae7161c0dd3271961d7ffa&op=getSessionList&state=AZ
    url = f"https://api.legiscan.com/?key={api_key}&op=getSessionList&state={state}"
    response = requests.get(url, timeout=5)
    response.raise_for_status()  # Raises an HTTPError for bad responses
    data = response.json()
    session_ids = [s['session_id'] for s in data['sessions'] if (str(year) in s['session_title'])]
    print(f"Found {len(session_ids)} sessions for {state} in {year}")
    return session_ids
def fetch_people(session_id):
    url = f"https://api.legiscan.com/?key={api_key}&op=getSessionPeople&id={session_id}"
    response = requests.get(url, timeout=5)
    response.raise_for_status()  # Raises an HTTPError for bad responses
    data = response.json()
    return data['sessionpeople']['people']  # fields: people_id, name
def fetch_votes(roll_call_id):
    url = f"https://api.legiscan.com/?key={api_key}&op=getRollCall&id={roll_call_id}"
    response = requests.get(url, timeout=5)
    response.raise_for_status()  # Raises an HTTPError for bad responses
    data = response.json()
    return data['roll_call']  # fields: people_id, vote_id, vote_text
def fetch_bill(bill_id):
    url = f"https://api.legiscan.com/?key={api_key}&op=getBill&id={bill_id}"
    response = requests.get(url, timeout=5)
    response.raise_for_status()  # Raises an HTTPError for bad responses
    data = response.json()
    return data['bill']
def drop_tables():
    cursor.execute('DROP TABLE IF EXISTS session_people')
    cursor.execute('DROP TABLE IF EXISTS rollcall_votes')
    cursor.execute('DROP TABLE IF EXISTS cpac_people')
    cursor.execute('DROP TABLE IF EXISTS bills')
def create_tables():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS session_people (
        state TEXT,
        people_id INTEGER,
        name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        role TEXT NOT NULL,
        party TEXT,
        UNIQUE(state, name)
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS rollcall_votes (
        rollcall_id INTEGER,
        people_id INTEGER,
        vote_id INTEGER,
        vote_text TEXT,
        bill_id INTEGER,
        FOREIGN KEY (people_id) REFERENCES session_people(people_id)
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cpac_people (
        name TEXT,
        party TEXT,
        previous_year_score FLOAT,
        old_lifetime_score FLOAT,
        years_of_service INTEGER,
        state TEXT, 
        year INTEGER           
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bills (
        bill_id INTEGER PRIMARY KEY,
        bill_number TEXT,
        title TEXT,
        state TEXT,
        description TEXT,
        approved BOOL,
        approved_text TEXT,
        link TEXT
    )''')
def add_session_people(state, people_data, house_or_senate):    
    for p in people_data:
        if p['committee_id']>0:
            continue
        if house_or_senate=='senate':
            if p['role']=='Rep':
                continue
        if house_or_senate=='house':
            if p['role']=='Sen':
                continue
        cursor.execute('''
        INSERT OR IGNORE INTO session_people (state, people_id, name, last_name, role, party)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (state, p['people_id'], p['name'], p['last_name'], p['role'], p['party']))
def add_rollcall_votes(rollcall_id, rollcall_data):
    bill_id = rollcall_data['bill_id']
    for v in rollcall_data['votes']:
        cursor.execute('''
        INSERT OR IGNORE INTO rollcall_votes (rollcall_id, people_id, vote_id, vote_text, bill_id)
        VALUES (?, ?, ?, ?, ?)
        ''', (rollcall_id, v['people_id'], v['vote_id'], v['vote_text'], bill_id))
def add_cpac_people(state, year, cpac_people_data, house_or_senate):
    for c in cpac_people_data:
        name=c['name']
        party=c['history'][0]['party']
        previous_year_score=c['acuRatings'][0]['rating'] if len(c['acuRatings'])>0 else None
        old_lifetime_score=c['acuLifetimeRatings'][0]['rating'] if len(c['acuLifetimeRatings'])>0 else None
        years_of_service=c['yearsRated']['aggregate']['count']
        if house_or_senate=='senate':
            if c['history'][0]['chamber']=='house':
                continue
        if house_or_senate=='house':
            if c['history'][0]['chamber']=='senate':
                continue
        cursor.execute('''
        INSERT OR IGNORE INTO cpac_people (name, party, previous_year_score, old_lifetime_score, years_of_service, state, year)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, party, previous_year_score, old_lifetime_score, years_of_service, state, year))                                             
def add_bill(bill_id, bill_data):
    link = bill_data['url']
    bill_number = bill_data['bill_number']
    title = bill_data['title']
    state = bill_data['state']
    actions = [h['action'] for h in bill_data['history']]
    approved = any('approved' in a.lower() for a in actions)
    description = bill_data['description']
    cursor.execute('''
    INSERT OR IGNORE INTO bills (bill_id, bill_number, title, state, description, approved, link)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (bill_id, bill_number, title, state, description, approved, link))
def create_spreadsheet(good_rollcall_ids, bad_rollcall_ids, state, year):
    # Initialize empty DataFrame with names
    query = """
    SELECT name, last_name, role, party 
    FROM session_people
    WHERE state = ?
    ORDER BY last_name
    """
    cursor.execute(query, [state])
    df = pd.DataFrame(cursor.fetchall(), columns=['Name', 'last_name', 'role', 'party'])

    #Get cpac ratings
    query = """
    SELECT name AS cpac_name, party AS cpac_party, previous_year_score, old_lifetime_score, years_of_service
    FROM cpac_people
    WHERE state = ? AND year = ?
    """
    cpac_year = year - 1
    cursor.execute(query, [state, cpac_year])
    cpac_df = pd.DataFrame(cursor.fetchall(), columns=['cpac_name', 'cpac_party', 'previous_year_score', 'old_lifetime_score', 'years_of_service'])
    df = pd.merge(df, cpac_df, left_on='Name', right_on='cpac_name', how='outer')
    df = df.sort_values(by='last_name', ascending=True)

    # Add each bill's votes as a new column
    for i, rollcall_id in enumerate(good_rollcall_ids + bad_rollcall_ids):
        query = """
        SELECT b.bill_number FROM rollcall_votes rv JOIN bills b ON rv.bill_id = b.bill_id WHERE rv.rollcall_id = ?
        """
        result = cursor.execute(query, [rollcall_id]).fetchone()
        bill_number = result[0] if result else f'Bill{i+1}'
        query = """
        SELECT sp.name, rv.vote_text
        FROM session_people sp
        JOIN rollcall_votes rv 
            ON sp.people_id = rv.people_id
        WHERE sp.state = ?
            AND rv.rollcall_id = ?
        """
        cursor.execute(query, [state, rollcall_id])
        votes = pd.DataFrame(cursor.fetchall(), columns=['Name', bill_number])
        df = df.merge(votes[['Name', bill_number]], on='Name', how='left')
        # Add score column based on vote text
        vote_text_map = {'Yea': '+', 'Nay': '-', 'NV': 'x'} if rollcall_id in good_rollcall_ids else {'Yea': '-', 'Nay': '+', 'NV': 'x'}
        df[bill_number] = df[bill_number].map(vote_text_map)

    # Add bills
    query = """
    SELECT bill_id, bill_number, title, state, description, approved, link
    FROM bills
    """
    cursor.execute(query)
    bills_df = pd.DataFrame(cursor.fetchall(), columns=['bill_id', 'bill_number', 'title', 'state', 'description', 'approved', 'link'])
    # add a column for the number of yeas and nays
    query = """
    SELECT bill_id,
        SUM(CASE WHEN vote_text = 'Yea' THEN 1 ELSE 0 END) AS yeas,
        SUM(CASE WHEN vote_text = 'Nay' THEN 1 ELSE 0 END) AS nays
    FROM rollcall_votes
    GROUP BY bill_id
    """
    cursor.execute(query)
    yeas_nays_df = pd.DataFrame(cursor.fetchall(), columns=['bill_id', 'yeas', 'nays'])
    bills_df = pd.merge(bills_df, yeas_nays_df, on='bill_id', how='left')
    # Add a column showing if bill passed and vote counts
    bills_df['passed'] = bills_df.apply(lambda row: f'The bill {"passed" if row["yeas"] > row["nays"] else "failed"} with a vote of {row["yeas"]} yeas and {row["nays"]} nays', axis=1)

    # Write to Excel
    file_name = f'votes_{state}_{year}.xlsx'
    with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Votes', index=False)
        bills_df.to_excel(writer, sheet_name='Bills', index=False)
    return file_name


def validate_year(year: str):
    try:
        year = int(year)
        return year
    except ValueError:
        return False 
def validate_state(state: str):
    try:
        assert len(state)==2
        return state
    except AssertionError:
        return False     
def validate_rollcalls(rollcalls: str):
    try:
        urls = [line.strip() for line in rollcalls.splitlines()]
        rollCallIds = [int(url.split("id/")[-1]) for url in urls if url]
        return rollCallIds
    except ValueError as e:
        print(f"Error validating roll calls: {e}")
        return False
async def process(state: str, year: str, chamber: str, good_rollcalls: str, bad_rollcalls: str, websocket, manager):
    # session_ids = validate_session_id()
    # if not session_ids:
    #     msg_button.config(text="Please enter a valid session ID")
    #     session_entry.delete(0, tk.END)
    #     session_entry.insert(0, default_session_entry_msg)
    #     return
    if manager:
        await manager.send_message("Processing...", websocket)
    good_rollcall_ids = validate_rollcalls(good_rollcalls)
    bad_rollcall_ids = validate_rollcalls(bad_rollcalls)
    year = validate_year(year)
    state = validate_state(state)
    session_ids = fetch_sessions_list(state, year)
    drop_tables()
    create_tables()
    house_or_senate_flag = 0 if chamber=="senate" else 1
    for session_id in session_ids:
        session_people = fetch_people(session_id)
        house_or_senate = "senate" if house_or_senate_flag==0 else "house"
        add_session_people(state, session_people, house_or_senate)
        if manager:
            await manager.send_message(f"Processed session {session_id}", websocket)

    for rid in good_rollcall_ids+bad_rollcall_ids:
        if manager:
            await manager.send_message(f"Processing roll call {rid}...", websocket)
        print(f"Fetching votes for roll call {rid}...")
        rollcall_data = fetch_votes(rid)
        add_rollcall_votes(rid, rollcall_data)
        if manager:
            await manager.send_message(f"Processed roll call {rid}...", websocket)
        print(f"Fetching bill {rid}...")
        bill_id = rollcall_data['bill_id']
        bill_data = fetch_bill(bill_id)
        add_bill(bill_id, bill_data)

    print("Fetching CPAC (acu) Ratings...")
    if manager:
        await manager.send_message("Fetching CPAC (acu) Ratings...", websocket)
    cpac_year = year - 1;
    data = fetch_ratings(state, cpac_year)
    add_cpac_people(state, cpac_year, data, house_or_senate)

    print("Creating spreadsheet...")
    if manager:
        await manager.send_message("Creating spreadsheet...", websocket)
    file_name = create_spreadsheet(good_rollcall_ids, bad_rollcall_ids, state, year)
    print("Spreadsheet created!")
    if manager:
        await manager.send_message("Spreadsheet created!", websocket)
    return file_name

#%%
import nest_asyncio
nest_asyncio.apply()
import asyncio
asyncio.run(process("AZ", "2024", "senate", "1437226", "1423115", None, None))

#%%
import nest_asyncio
nest_asyncio.apply()
from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel
from typing import Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os
from fastapi import WebSocket
from fastapi import WebSocket
from typing import List

# Add these new variables
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

manager = ConnectionManager()

class RollCallData(BaseModel):
    state: str
    year: str
    chamber: str
    goodRollCalls: str
    badRollCalls: str

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            try:
                # Process the data and get the file path
                file_name = await process(
                    data["state"], 
                    data["year"], 
                    data["chamber"], 
                    data["goodRollCalls"], 
                    data["badRollCalls"],
                    websocket,
                    manager
                )
                
                # Read the file and send it as base64
                with open(file_name, 'rb') as file:
                    file_bytes = file.read()
                    base64_bytes = base64.b64encode(file_bytes).decode('utf-8')
                    await manager.send_message(json.dumps({
                        "type": "file",
                        "data": base64_bytes,
                        "filename": file_name
                    }), websocket)
                
                # Clean up the file
                # os.remove(file_name)
                
            except Exception as e:
                await manager.send_message(json.dumps({
                    "type": "error",
                    "message": str(e)
                }), websocket)
    except:
        await manager.disconnect(websocket)

if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=5000)

# %%