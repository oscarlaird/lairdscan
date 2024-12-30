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
                print("Skipping Rep in session people")
                continue
        if house_or_senate=='house':
            if p['role']=='Sen':
                print("Skipping Sen in session people")
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
        previous_year_score=c['acuRatings'][0]['rating'] if len(c['acuRatings'])>0 else None
        old_lifetime_score=c['acuLifetimeRatings'][0]['rating'] if len(c['acuLifetimeRatings'])>0 else None
        years_of_service=c['yearsRated']['aggregate']['count']
        if house_or_senate=='senate':
            if c['history'][0]['chamber']=='house':
                print("Skipping Rep in cpac data")
                continue
        if house_or_senate=='house':
            if c['history'][0]['chamber']=='senate':
                print("Skipping Sen in cpac data")
                continue
        cursor.execute('''
        INSERT OR IGNORE INTO cpac_people (name, party, previous_year_score, old_lifetime_score, years_of_service, state, year)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, party, previous_year_score, old_lifetime_score, years_of_service, state, year))                                             
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

    # Add each bill's votes as a new column
    for i, rollcall_id in enumerate(good_rollcall_ids + bad_rollcall_ids):
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
        # Add score column based on vote text
        vote_text_map = {'Yea': '+', 'Nay': '-', 'NV': 'x'} if rollcall_id in good_rollcall_ids else {'Yea': '-', 'Nay': '+', 'NV': 'x'}
        df[f'Bill{i+1}_score'] = df[f'Bill{i+1}'].map(vote_text_map)

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
root.title("Roll Call Scraper")
root.geometry("600x600")
# allow resizing
root.grid_columnconfigure(0, weight=1)
root.grid_rowconfigure(0, weight=1)
# Create a main frame
main_frame = tk.Frame(root)
main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
# Add a label for showing messages
msg_label = tk.Label(main_frame, text="Enter links to roll calls from the legiscan website.")
msg_label.pack(pady=10)
# state entry field
# Create state entry frame and widgets
state_frame = tk.Frame(main_frame)
state_frame.pack(pady=5)
state_label = tk.Label(state_frame, text="STATE")
state_label.pack(side=tk.LEFT, padx=5)
state_entry = tk.Entry(state_frame, width=100)
default_state_entry_msg = "AZ"
state_entry.insert(0, default_state_entry_msg)
state_entry.pack(side=tk.LEFT, padx=5)
# year entry field
year_frame = tk.Frame(main_frame)
year_frame.pack(pady=5)
year_label = tk.Label(year_frame, text="YEAR")
year_label.pack(side=tk.LEFT, padx=5)
year_entry = tk.Entry(year_frame, width=100)
default_year_entry_msg = "2023"
year_entry.insert(0, default_year_entry_msg)
year_entry.pack(side=tk.LEFT, padx=5)
# Add toggle for house/senate
house_or_senate_toggle_flag = tk.IntVar(value=0)
toggle_frame = tk.Frame(main_frame)
toggle_frame.pack(pady=5)
radio_off = tk.Radiobutton(toggle_frame, text="Senate", variable=house_or_senate_toggle_flag, value=0, indicatoron=False, width=10)
radio_on = tk.Radiobutton(toggle_frame, text="House", variable=house_or_senate_toggle_flag, value=1, indicatoron=False, width=10)
radio_off.pack(side=tk.LEFT, padx=5)
radio_on.pack(side=tk.LEFT, padx=5)
# rollCallId entry fields
good_rollcalls_label = tk.Label(main_frame, text="Good Roll Call URLs (one per line)")
good_rollcalls_label.pack(pady=(10,0))
good_rollcalls_entry = tk.Text(main_frame, width=1000, height=5)
default_good_roll_call_entry_msg = """
https://legiscan.com/AZ/rollcall/SB1003/id/1373207
https://legiscan.com/AZ/rollcall/SB1004/id/1398904
"""
good_rollcalls_entry.insert("1.0", default_good_roll_call_entry_msg)
good_rollcalls_entry.pack(pady=5, fill="both", expand=True)

bad_rollcalls_label = tk.Label(main_frame, text="Bad Roll Call URLs (one per line)")
bad_rollcalls_label.pack(pady=(10,0))
bad_rollcalls_entry = tk.Text(main_frame, width=1000, height=5)
bad_rollcalls_entry.insert("1.0", "")
bad_rollcalls_entry.pack(pady=5, fill="both", expand=True)

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
def validate_rollcalls(entry_widget):
    try:
        urls = [line.strip() for line in entry_widget.get("1.0", tk.END).splitlines()]
        rollCallIds = [int(url.split("id/")[-1]) for url in urls if url]
        return rollCallIds
    except ValueError as e:
        print(f"Error validating roll calls: {e}")
        return False
def process():
    # session_ids = validate_session_id()
    # if not session_ids:
    #     msg_button.config(text="Please enter a valid session ID")
    #     session_entry.delete(0, tk.END)
    #     session_entry.insert(0, default_session_entry_msg)
    #     return
    good_rollcall_ids = validate_rollcalls(good_rollcalls_entry)
    bad_rollcall_ids = validate_rollcalls(bad_rollcalls_entry)
    if good_rollcall_ids is False or bad_rollcall_ids is False:
        msg_label.config(text="Please enter urls which end in the roll call id.")
        return
    year = validate_year()
    if not year:
        msg_label.config(text="Please enter a valid year")
        return
    state = validate_state()
    if not state: 
        msg_label.config(text="Please enter a two letter state abbreviation")
        return
    msg_label.config(text=f"Fetching sessions list for {state} in {year}...")
    root.update()
    session_ids = fetch_sessions_list(state, year)
    drop_tables()
    create_tables()
    msg_label.config(text="Fetching session people...")
    root.update()
    for session_id in session_ids:
        session_people = fetch_people(session_id)
        house_or_senate = "senate" if house_or_senate_toggle_flag.get()==0 else "house"
        add_session_people(state, session_people, house_or_senate)

    for rid in good_rollcall_ids+bad_rollcall_ids:
        msg_label.config(text=f"Fetching votes for roll call {rid}...")
        root.update()
        votes = fetch_votes(rid)
        add_rollcall_votes(rid, votes)

    msg_label.config(text="Fetching CPAC (acu) Ratings...")
    root.update()
    data = fetch_ratings(state, year)
    add_cpac_people(state, year, data, house_or_senate)

    msg_label.config(text="Creating spreadsheet...")
    root.update()
    create_spreadsheet(good_rollcall_ids, bad_rollcall_ids, state, year)
    msg_label.config(text="Spreadsheet created!")
# Add a button
button = tk.Button(main_frame, text="Create Spreadsheet!", command=process)
button.pack(pady=10)
# Start the main loop
root.mainloop()


#%%
# default_roll_call_entry_msg = "1253853\n1353336"
# drop_tables()
# create_tables()
# data = fetch_votes(1253853)
# print(data, len(data), type(data))
# add_rollcall_votes(1253853, data)


# %%
conn.commit()
cursor.close()
conn.close()