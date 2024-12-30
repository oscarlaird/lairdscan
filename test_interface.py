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
# Start the main loop
root.mainloop()