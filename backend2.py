#%%
import sqlite3
import requests
import pandas as pd

#%%
from cpac_scanner import fetch_ratings
#%%

# Create/connect to database
conn = sqlite3.connect('legislative_data.db')
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
    cursor.execute('DROP TABLE IF EXISTS cpac_people')
def create_tables():
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS session_people (
        state TEXT,
        people_id INTEGER,
        name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        role TEXT NOT NULL,
        party TEXT
    )''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS rollcall_votes (
        rollcall_id INTEGER,
        people_id INTEGER,
        vote_id INTEGER,
        vote_text TEXT,
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
def add_rollcall_votes(rollcall_id, votes_data):
    for v in votes_data:
        cursor.execute('''
        INSERT OR IGNORE INTO rollcall_votes (rollcall_id, people_id, vote_id, vote_text)
        VALUES (?, ?, ?, ?)
        ''', (rollcall_id, v['people_id'], v['vote_id'], v['vote_text']))
def add_cpac_people(state, year, cpac_people_data, house_or_senate):
    for c in cpac_people_data:
        name=c['name']
        party=c['history'][0]['party']
        previous_year_score=c['acuRatings'][0]['rating']
        old_lifetime_score=c['acuLifetimeRatings'][0]['rating']
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
def create_spreadsheet(rollcall_ids, state, year):
    # Initialize empty DataFrame with names
    query = """
    SELECT name, last_name, role, party 
    FROM session_people
    WHERE state = ?
    ORDER BY last_name
    """
    cursor.execute(query, [state])
    df = pd.DataFrame(cursor.fetchall(), columns=['Name', 'last_name', 'role', 'party'])

    # Add each bill's votes as a new column
    for i, rollcall_id in enumerate(rollcall_ids):
        query = """
        SELECT sp.name, rv.vote_text
        FROM session_people sp
        JOIN rollcall_votes rv 
            ON sp.people_id = rv.people_id
        WHERE sp.state = ?
            AND rv.rollcall_id = ?
        """
        cursor.execute(query, [state, rollcall_id])
        votes = pd.DataFrame(cursor.fetchall(), columns=['Name', f'Bill{i+1}'])
        df = df.merge(votes[['Name', f'Bill{i+1}']], on='Name', how='left')

    #Get cpac ratings
    query = """
    SELECT name AS cpac_name, party AS cpac_party, previous_year_score, old_lifetime_score, years_of_service
    FROM cpac_people
    WHERE state = ? AND year = ?
    """
    cursor.execute(query, [state, year])
    cpac_df = pd.DataFrame(cursor.fetchall(), columns=['cpac_name', 'cpac_party', 'previous_year_score', 'old_lifetime_score', 'years_of_service'])
    df = pd.merge(df, cpac_df, left_on='Name', right_on='cpac_name', how='outer')
    sorted_df = df.sort_values(by='last_name', ascending=True)
    # Write to Excel
    sorted_df.to_excel(f'votes_{state}.xlsx', index=False)


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
# Add toggle for house/senate
house_or_senate_toggle_flag = tk.IntVar(value=1)
radio_on = tk.Radiobutton(root, text="House", variable=house_or_senate_toggle_flag, value=1, indicatoron=False, width=10)
radio_off = tk.Radiobutton(root, text="Senate", variable=house_or_senate_toggle_flag, value=0, indicatoron=False, width=10)
radio_off.pack(pady=5)
radio_on.pack(pady=5)
# session_id entry field
session_entry = tk.Text(main_frame, width=1000, height=5)
default_session_entry_msg = "2098\n1988"
session_entry.insert("1.0", default_session_entry_msg)
session_entry.pack(pady=10)
# state entry field
state_entry = tk.Entry(main_frame, width=100)
default_state_entry_msg = "VA"
state_entry.insert(0, default_state_entry_msg)
state_entry.pack(pady=10)
# year entry field
year_entry = tk.Entry(main_frame, width=100)
default_year_entry_msg = "2023"
year_entry.insert(0, default_year_entry_msg)
year_entry.pack(pady=10)
# rollCallId entry field
rollCallId_entry = tk.Text(main_frame, width=1000, height=21)
default_roll_call_entry_msg = "1253853\n1353336"
rollCallId_entry.insert("1.0", default_roll_call_entry_msg)
rollCallId_entry.pack(pady=10)
# Update button command to print entry value
def validate_session_id():
    try:
        session_ids = [int(line) for line in session_entry.get("1.0", tk.END).splitlines()]
        return session_ids
    except ValueError:
        return False
def validate_year():
    try:
        year = int(year_entry.get())
        return year
    except ValueError:
        return False 
def validate_state():
    try:
        state = state_entry.get()
        assert len(state)==2
        return state
    except AssertionError:
        return False     
def validate_rollCallId():
    try:
        rollCallIds = [int(line) for line in rollCallId_entry.get("1.0", tk.END).splitlines()]
        return rollCallIds
    except ValueError:
        return False
def process():
    session_ids = validate_session_id()
    if not session_ids:
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
    year = validate_year()
    if not year:
        msg_button.config(text="Please enter a valid year")
        return
    state = validate_state()
    if not state: 
        msg_button.config(text="Please enter a two letter state abbreviation")
        return
    drop_tables()
    create_tables()
    msg_button.config(text="Fetching session people...")
    root.update()
    for session_id in session_ids:
        session_people = fetch_people(session_id)
        house_or_senate = "senate" if house_or_senate_toggle_flag.get()==0 else "house"
        add_session_people(state, session_people, house_or_senate)

    for rid in rollCallIds:
        msg_button.config(text=f"Fetching votes for roll call {rid}...")
        root.update()
        votes = fetch_votes(rid)
        add_rollcall_votes(rid, votes)

    msg_button.config(text="Fetching CPAC (acu) Ratings...")
    data = fetch_ratings(state, year)
    add_cpac_people(state, year, data, house_or_senate)

    msg_button.config(text="Creating spreadsheet...")
    root.update()
    create_spreadsheet(rollCallIds, state, year)
    msg_button.config(text="Spreadsheet created!")
# Add a button
button = tk.Button(main_frame, text="Create Spreadsheet!", command=process)
button.pack(pady=10)
# Start the main loop
# root.mainloop()


#%%
# default_roll_call_entry_msg = "1253853\n1353336"
drop_tables()
create_tables()
data = fetch_votes(1253853)
print(data, len(data), type(data))
add_rollcall_votes(1253853, data)


# %%
conn.commit()
cursor.close()
conn.close()