#%%
import sqlite3
import requests
import pandas as pd

# Create/connect to database
conn = sqlite3.connect('legislative_data.db')
cursor = conn.cursor()

#%%

# Make API call to get session people
api_key = "1044f606ddae7161c0dd3271961d7ffa"
example_session_id = 2007
example_person_name = "Terry Alexander"
example_people_id = 2202
example_roll_call_id = 1437226
example_roll_call_id_2 = 1423115 
example_roll_call_id_3 = 1440286
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
    return data['roll_call']['votes']  # fields: people_id, vote_id, vote_text
def drop_tables():
    cursor.execute('DROP TABLE IF EXISTS session_people')
    cursor.execute('DROP TABLE IF EXISTS rollcall_votes')
def create_tables():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS session_people (
        session_id INTEGER,
        people_id INTEGER,
        name TEXT NOT NULL
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS rollcall_votes (
        rollcall_id INTEGER,
        people_id INTEGER,
        vote_id INTEGER,
        vote_text TEXT,
        FOREIGN KEY (people_id) REFERENCES session_people(people_id)
    )''')
def add_session_people(session_id, people_data):    
    for p in people_data:
        cursor.execute('''
        INSERT OR IGNORE INTO session_people (session_id, people_id, name)
        VALUES (?, ?, ?)
        ''', (session_id, p['people_id'], p['name']))
def add_rollcall_votes(rollcall_id, votes_data):
    for v in votes_data:
        cursor.execute('''
        INSERT OR IGNORE INTO rollcall_votes (rollcall_id, people_id, vote_id, vote_text)
        VALUES (?, ?, ?, ?)
        ''', (rollcall_id, v['people_id'], v['vote_id'], v['vote_text']))
def create_spreadsheet(session_id, rollcall_ids):
    # Initialize empty DataFrame with names
    query = """
    SELECT name 
    FROM session_people
    WHERE session_id = ?
    ORDER BY name
    """
    cursor.execute(query, [session_id])
    df = pd.DataFrame(cursor.fetchall(), columns=['Name'])
    
    # Add each bill's votes as a new column
    for i, rollcall_id in enumerate(rollcall_ids):
        query = """
        SELECT sp.name, rv.vote_text
        FROM session_people sp
        JOIN rollcall_votes rv 
            ON sp.people_id = rv.people_id
        WHERE sp.session_id = ?
            AND rv.rollcall_id = ?
        ORDER BY sp.name
        """
        cursor.execute(query, [session_id, rollcall_id])
        votes = pd.DataFrame(cursor.fetchall(), columns=['Name', f'Bill{i+1}'])
        df = df.merge(votes[['Name', f'Bill{i+1}']], on='Name', how='left')
    
    # Write to Excel
    df.to_excel(f'votes_{session_id}.xlsx', index=False)
def pipeline(session_id, rollcall_ids):
    drop_tables()
    create_tables()
    session_people = fetch_people(session_id)
    add_session_people(session_id, session_people)
    for rid in rollcall_ids:
        votes = fetch_votes(rid)
        add_rollcall_votes(rid, votes)
    create_spreadsheet(session_id, rollcall_ids)
#%%
drop_tables()
create_tables()
#%%
add_session_people(example_session_id, fetch_people(example_session_id))
add_rollcall_votes(example_roll_call_id, fetch_votes(example_roll_call_id))
create_spreadsheet(example_session_id, [example_roll_call_id, example_roll_call_id_2])
#%%
pipeline(example_session_id, [example_roll_call_id, example_roll_call_id_2])


#%%
import tkinter as tk
root = tk.Tk()
root.title("Roll Call Creator")
root.geometry("500x800")
# Create a main frame
main_frame = tk.Frame(root)
main_frame.pack(padx=10, pady=10)
# Add a button for showing messages
msg_button = tk.Button(main_frame, text="I am a button used for output messages.")
msg_button.pack(pady=10)
# session_id entry field
session_entry = tk.Entry(main_frame, width=1000)
default_session_entry_msg = "Enter session id here (e.g. 2007 for SC 2023-2024)"
session_entry.insert(0, default_session_entry_msg)
session_entry.pack(pady=10)
# rollCallId entry field
rollCallId_entry = tk.Text(main_frame, width=1000, height=21)
default_roll_call_entry_msg = "Enter roll call IDs here (one per line)\ne.g.\n1437226\n1423115\n1440286"
rollCallId_entry.insert("1.0", default_roll_call_entry_msg)
rollCallId_entry.pack(pady=10)
# Update button command to print entry value
def validate_session_id():
    try:
        session_id = int(session_entry.get())
        return session_id
    except ValueError:
        return False
def validate_rollCallId():
    try:
        rollCallIds = [int(line) for line in rollCallId_entry.get("1.0", tk.END).splitlines()]
        return rollCallIds
    except ValueError:
        return False
def process():
    session_id = validate_session_id()
    if not session_id:
        msg_button.config(text="Please enter a valid session ID")
        session_entry.delete(0, tk.END)
        session_entry.insert(0, default_session_entry_msg)
        return
    rollCallIds = validate_rollCallId()
    if not rollCallIds:
        msg_button.config(text="Please enter a valid roll call ID")
        rollCallId_entry.delete("1.0", tk.END)
        rollCallId_entry.insert("1.0", default_roll_call_entry_msg)
        return
    drop_tables()
    create_tables()
    msg_button.config(text="Fetching session people...")
    session_people = fetch_people(session_id)
    add_session_people(session_id, session_people)
    for rid in rollCallIds:
        msg_button.config(text=f"Fetching votes for roll call {rid}...")
        votes = fetch_votes(rid)
        add_rollcall_votes(rid, votes)
    msg_button.config(text="Creating spreadsheet...")
    create_spreadsheet(session_id, rollCallIds)
    msg_button.config(text="Spreadsheet created!")
# Add a button
button = tk.Button(main_frame, text="Create Spreadsheet!", command=process)
button.pack(pady=10)
# Start the main loop
root.mainloop()