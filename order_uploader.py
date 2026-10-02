import os
import csv
import io
import base64
import requests
import random
import string
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import smtplib
from email.message import EmailMessage
import webbrowser
import time
import socket
import threading
import httplib2
import ssl
import traceback
import sys
import hashlib
# Google Drive imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
# Gmail API imports
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import re

# --- GitHub API utility functions (reuse from main app) ---
github_token = "YOUR_GITHUB_TOKEN"
github_repo = "ordercreator"
github_owner = "YOUR_GITHUB_USERNAME"

def github_api_headers(json_mode=False):
    return {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json" if json_mode else "application/vnd.github.v3.raw"
    }

def get_github_file_content(path):
    url = f"https://api.github.com/repos/{github_owner}/{github_repo}/contents/{path}"
    try:
        response = requests.get(url, headers=github_api_headers(False), timeout=600)
        response.raise_for_status()
        return response.content.decode("utf-8")
    except requests.exceptions.Timeout:
        raise Exception("Connexion à GitHub expirée (timeout). Vérifiez votre connexion internet.")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Erreur réseau lors de l'accès à GitHub: {e}")
    except ssl.SSLError as e:
        raise Exception(f"Erreur SSL lors de l'accès à GitHub: {e}")

def update_github_file_content(path, content, message="Update file via uploader"):
    url = f"https://api.github.com/repos/{github_owner}/{github_repo}/contents/{path}"
    try:
        get_resp = requests.get(url, headers=github_api_headers(True), timeout=600)
    except requests.exceptions.Timeout:
        raise Exception("Connexion à GitHub expirée (timeout). Vérifiez votre connexion internet.")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Erreur réseau lors de l'accès à GitHub: {e}")
    except ssl.SSLError as e:
        raise Exception(f"Erreur SSL lors de l'accès à GitHub: {e}")
    if get_resp.status_code == 200:
        try:
            sha = get_resp.json()["sha"]
        except Exception as e:
            print(f"Error parsing SHA for {path}: {e}, response: {get_resp.text}")
            sha = None
    elif get_resp.status_code == 404:
        sha = None
    else:
        print(f"GitHub GET error for {path}: {get_resp.status_code} {get_resp.text}")
        get_resp.raise_for_status()
    data = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
    }
    if sha:
        data["sha"] = sha
    try:
        put_resp = requests.put(url, headers=github_api_headers(True), json=data, timeout=600)
    except requests.exceptions.Timeout:
        raise Exception("Connexion à GitHub expirée (timeout). Vérifiez votre connexion internet.")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Erreur réseau lors de l'accès à GitHub: {e}")
    except ssl.SSLError as e:
        raise Exception(f"Erreur SSL lors de l'accès à GitHub: {e}")
    if put_resp.status_code not in (200, 201):
        print(f"GitHub PUT error for {path}: {put_resp.status_code} {put_resp.text}")
    put_resp.raise_for_status()
    return put_resp.json()

def upload_file_to_github(local_path, nom_client, numero):
    ext = os.path.splitext(local_path)[1]
    orig_filename = os.path.basename(local_path)
    rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    safe_nom = ''.join(c for c in nom_client if c.isalnum())
    safe_num = ''.join(c for c in numero if c.isalnum())
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')  # up to microseconds
    with open(local_path, "rb") as f:
        content = f.read()
        file_hash = hashlib.sha256(content).hexdigest()[:12]
    # Compose a very long and unique filename
    new_name = f"{safe_nom}_{safe_num}_{timestamp}_{rand_str}_{file_hash}_{orig_filename}"
    # Upload to uploads/
    path = f"uploads/{new_name}"
    url = f"https://api.github.com/repos/{github_owner}/{github_repo}/contents/{path}"
    try:
        get_resp = requests.get(url, headers=github_api_headers(True), timeout=600)
    except requests.exceptions.Timeout:
        raise Exception("Connexion à GitHub expirée (timeout). Vérifiez votre connexion internet.")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Erreur réseau lors de l'accès à GitHub: {e}")
    except ssl.SSLError as e:
        raise Exception(f"Erreur SSL lors de l'accès à GitHub: {e}")
    if get_resp.status_code == 200:
        sha = get_resp.json()["sha"]
    else:
        sha = None
    data = {
        "message": f"Upload file {new_name}",
        "content": base64.b64encode(content).decode("utf-8"),
    }
    if sha:
        data["sha"] = sha
    try:
        put_resp = requests.put(url, headers=github_api_headers(True), json=data, timeout=600)
    except requests.exceptions.Timeout:
        raise Exception("Connexion à GitHub expirée (timeout). Vérifiez votre connexion internet.")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Erreur réseau lors de l'accès à GitHub: {e}")
    except ssl.SSLError as e:
        raise Exception(f"Erreur SSL lors de l'accès à GitHub: {e}")
    put_resp.raise_for_status()
    return new_name

def load_csv_from_github(filename):
    try:
        content = get_github_file_content(filename)
        if not content.strip():
            return []
        reader = csv.DictReader(io.StringIO(content))
        return list(reader)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []

def save_csv_to_github(filename, rows, fieldnames, message):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    update_github_file_content(filename, output.getvalue(), message)

def ensure_github_files_exist():
    # Create the required CSV/TXT files and the uploads/ folder on GitHub if they are missing
    csv_header = "NomClient,Numero,TypePersonnalisation,Commande,NombreD'impression10CM,NombreD'impression15CM,NombreD'Impression25CM,RefColor,Police,Remarque,Graphiste,Presseur,status,BunchOfPhotos\n"
    required_files = {
        "chaima.csv": csv_header,
        "yosr.csv": csv_header,
        "chaimadone.csv": csv_header,
        "yosrdone.csv": csv_header,
        "versionordercreator.txt": "1.0.7",
        "versionorderextractor.txt": "1.0.4",
        "uploads/.gitkeep": "",
    }
    for path, default_content in required_files.items():
        url = f"https://api.github.com/repos/{github_owner}/{github_repo}/contents/{path}"
        try:
            resp = requests.get(url, headers=github_api_headers(True), timeout=600)
            if resp.status_code == 404:
                update_github_file_content(path, default_content, f"Create missing {path}")
                print(f"Created missing {path} on GitHub")
        except Exception as e:
            print(f"Could not check/create {path} on GitHub: {e}")

def insert_order(order_data, file_paths):
    # Decide which CSV to use
    graphiste = (order_data.get("Graphiste", "") or "").strip().lower()
    if graphiste == "chaima":
        csv_file = "chaima.csv"
    elif graphiste == "yosr":
        csv_file = "yosr.csv"
    else:
        raise ValueError("Graphiste must be 'Chaima' or 'Yosr'")
    # --- Do NOT upload any files to GitHub ---
    # Prepare row (do not include file names)
    order_data["BunchOfPhotos"] = ""
    order_data["status"] = "inserted"
    # Load, append, save
    rows = load_csv_from_github(csv_file)
    # Use the same fieldnames as your main app
    fieldnames = [
        "NomClient", "Numero", "TypePersonnalisation", "Commande",
        "NombreD'impression10CM", "NombreD'impression15CM", "NombreD'Impression25CM",
        "RefColor", "Police", "Remarque", "Graphiste", "Presseur", "status", "BunchOfPhotos"
    ]
    rows.append(order_data)
    save_csv_to_github(csv_file, rows, fieldnames, f"Add order for {order_data['NomClient']}")
    print(f"Order for {order_data['NomClient']} inserted in {csv_file} (no files uploaded to GitHub)")
    return [], []

# --- Email sending function ---
GMAIL_ADDRESS = "YOUR_GMAIL_ADDRESS@gmail.com"  # <-- Replace with your Gmail
GMAIL_APP_PASSWORD = "YOUR_GMAIL_APP_PASSWORD"  # <-- Replace with your Gmail app password

# Google Drive API setup
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'client_secret.json'

def authenticate_drive():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def upload_and_share_drive(file_path):
    if not file_path:
        raise ValueError("No file path provided to upload_and_share_drive.")
    service = authenticate_drive()
    file_metadata = {'name': os.path.basename(file_path)}
    media = MediaFileUpload(file_path, resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    file_id = file.get('id')
    if not file_id:
        raise Exception(f"Failed to upload {file_path} to Google Drive. No file ID returned. Response: {file}")
    # Set permission to anyone with the link
    service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'},
    ).execute()
    # Get shareable link
    link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    return link

def get_exe_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def sanitize_header(value):
    # Remove linefeed and carriage return characters
    return str(value).replace('\n', '').replace('\r', '').strip()

def normalize_html(html):
    # Remove whitespace, newlines, lowercase
    html = re.sub(r'\s+', '', html)
    return html.lower()

def extract_html_from_gmail_msg(msg):
    def get_html(payload):
        if 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                    import base64
                    return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                # Recursively check sub-parts
                result = get_html(part)
                if result:
                    return result
        else:
            if payload.get('mimeType') == 'text/html' and 'data' in payload.get('body', {}):
                import base64
                return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
        return ''
    return get_html(msg.get('payload', {}))

def email_matches_order(msg, order, sent_html):
    # Compare subject and HTML body
    headers = msg.get('payload', {}).get('headers', [])
    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
    numero = str(order.get('Numero', ''))
    nom_client = str(order.get('NomClient', ''))
    print(f"[DEBUG] Gmail subject: {subject}")
    if numero not in subject or nom_client not in subject:
        print(f"[DEBUG] Subject does not match: {numero}, {nom_client}")
        return False
    received_html = extract_html_from_gmail_msg(msg)
    print(f"[DEBUG] Received HTML snippet: {received_html[:200]}")
    norm_sent = normalize_html(sent_html)
    norm_received = normalize_html(received_html)
    if norm_sent == norm_received:
        print(f"[DEBUG] HTML matches.")
        return True
    print(f"[DEBUG] HTML does not match.")
    return False

def send_order_email(order, file_paths, github_filenames=None, big_files=None, return_html=False):
    msg = EmailMessage()
    nom_client = sanitize_header(order.get('NomClient', ''))
    numero = sanitize_header(order.get('Numero', ''))
    msg["Subject"] = f"{nom_client} ({numero})"
    msg["From"] = sanitize_header(GMAIL_ADDRESS)
    msg["To"] = sanitize_header(GMAIL_ADDRESS)

    # Build the HTML body first
    html = """
    <html>
    <head>
    <style>
    table {
        border-collapse: collapse;
        width: 100%;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 14px;
    }
    th, td {
        border: 1px solid #4b86b4;
        padding: 8px 12px;
        text-align: left;
    }
    th {
        background-color: #4b86b4;
        color: white;
    }
    tr:nth-child(even) {
        background-color: #f2f6fa;
    }
    </style>
    </head>
    <body>
    <h2 style=\"color:#2a4d69;\">Nouvelle Commande</h2>
    <table>
        <tr><th>Champ</th><th>Valeur</th></tr>
    """
    for k, v in order.items():
        # Convert line breaks to <br> for HTML display
        if isinstance(v, str):
            v_html = v.replace('\n', '<br>')
        else:
            v_html = v
        html += f"<tr><td>{k}</td><td>{v_html}</td></tr>"
    html += """
    </table>
    <p style=\"color:#4b86b4;\">Merci d'utiliser Order Uploader Pro Edition !</p>
    """

    drive_links = []
    for file_path in file_paths:
        try:
            link = upload_and_share_drive(file_path)
            drive_links.append((os.path.basename(file_path), link))
        except Exception as e:
            print(f"Could not upload {file_path} to Drive: {e}")

    if drive_links:
        html += "<h3>Fichiers disponibles sur Google Drive :</h3><ul>"
        for fname, link in drive_links:
            html += f'<li><a href="{link}">{fname}</a></li>'
        html += "</ul>"

    html += """
    </body>
    </html>
    """

    # Set plain text and HTML content (no attachments)
    msg.set_content("Nouvelle commande reçue. Veuillez ouvrir cet email dans un client compatible HTML pour voir les détails.")
    msg.add_alternative(html, subtype='html')

    # Send email
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=20) as smtp:
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            response = smtp.send_message(msg)
            print("SMTP send_message response:", response)
        print("Order email sent!")
    except (smtplib.SMTPException, socket.timeout) as e:
        print(f"Failed to send email: {e}")
        raise Exception("Connexion à Gmail expirée (timeout) ou erreur SMTP. Vérifiez votre connexion internet.")
    except Exception as e:
        print(f"Failed to send email: {e}")
        raise
    if return_html:
        return html

# --- Gmail API for verification ---
def authenticate_gmail():
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    creds = None
    if os.path.exists('gmail_token_uploader.pickle'):
        with open('gmail_token_uploader.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('gmail_token_uploader.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return build('gmail', 'v1', credentials=creds)

def get_most_recent_email_by_numero(gmail_service, numero):
    # Search for emails with the numero in the subject
    query = f'subject:{numero}'
    results = gmail_service.users().messages().list(userId='me', q=query, maxResults=1).execute()
    messages = results.get('messages', [])
    if not messages:
        return None
    msg_id = messages[0]['id']
    msg = gmail_service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    return msg

def verify_and_resend_if_needed(order, file_paths, sent_html):
    try:
        gmail_service = authenticate_gmail()
        numero = str(order.get('Numero', ''))
        msg = get_most_recent_email_by_numero(gmail_service, numero)
        if msg is not None and email_matches_order(msg, order, sent_html):
            print(f"[VERIFY] Email for Numero={numero} found and matches.")
            return
        print(f"[VERIFY] Email for Numero={numero} not found or does not match. Resending...")
        sent_html2 = send_order_email(order, file_paths, return_html=True)
        insert_order(order, file_paths)
        print(f"[VERIFY] Email for Numero={numero} resent.")
    except Exception as e:
        print(f"[VERIFY] Verification or resend failed for Numero={order.get('Numero','')}: {e}")

def run_ui():
    from tkinter import font
    root = tk.Tk()
    root.title("Order Uploader - Pro Edition")
    root.geometry("600x900")  # Increased height for better visibility
    root.minsize(500, 600)
    style = ttk.Style()
    style.theme_use('clam')
    style.configure('TLabel', font=('Segoe UI', 11))
    style.configure('TButton', font=('Segoe UI', 11, 'bold'), padding=6)
    style.configure('Header.TLabel', font=('Segoe UI', 16, 'bold'), foreground='#2a4d69')
    style.configure('Section.TLabelframe.Label', font=('Segoe UI', 13, 'bold'), foreground='#4b86b4')
    style.configure('Success.TLabel', foreground='green', font=('Segoe UI', 11, 'bold'))
    style.configure('Error.TLabel', foreground='red', font=('Segoe UI', 11, 'bold'))

    # --- Add scrollable main frame ---
    canvas = tk.Canvas(root, borderwidth=0, background="#f7f9fa")
    vscroll = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vscroll.set)
    vscroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    main_frame = ttk.Frame(canvas, padding=20)
    main_frame_id = canvas.create_window((0, 0), window=main_frame, anchor="nw")

    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    main_frame.bind("<Configure>", on_frame_configure)

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    # --- End scrollable main frame setup ---

    def on_canvas_configure(event):
        # Set the inner frame's width to match the canvas width
        canvas.itemconfig(main_frame_id, width=event.width)
    canvas.bind("<Configure>", on_canvas_configure)

    ttk.Label(main_frame, text="Nouvelle Commande", style='Header.TLabel').pack(pady=(0, 10))

    # --- Order Fields ---
    fields = [
        ("NomClient", "Nom du Client"),
        ("Numero", "Numéro"),
        ("TypePersonnalisation", "Type de Personnalisation"),
        ("Commande", "Commande"),
        ("NombreD'impression10CM", "Nb Impression 10CM"),
        ("NombreD'impression15CM", "Nb Impression 15CM"),
        ("NombreD'Impression25CM", "Nb Impression 25CM"),
        ("RefColor", "Réf Couleur"),
        ("Police", "Police"),
        ("Remarque", "Remarque"),
        ("Graphiste", "Graphiste"),
        ("Presseur", "Presseur"),
    ]
    entries = {}
    form = ttk.Labelframe(main_frame, text="Informations sur la commande", style='Section.TLabelframe')
    form.pack(fill=tk.X, pady=10)
    for idx, (field, label) in enumerate(fields):
        ttk.Label(form, text=label).grid(row=idx, column=0, sticky='w', padx=5, pady=5)
        if field == "Graphiste":
            var = tk.StringVar()
            cb = ttk.Combobox(form, textvariable=var, values=["Chaima", "Yosr"], state="readonly", width=18)
            cb.grid(row=idx, column=1, sticky='ew', padx=5, pady=5)
            entries[field] = var
        elif field in ("Commande", "Remarque"):
            txt = tk.Text(form, height=3, width=30, font=('Segoe UI', 10))
            txt.grid(row=idx, column=1, sticky='ew', padx=5, pady=5)
            entries[field] = txt
        else:
            ent = ttk.Entry(form, width=30)
            ent.grid(row=idx, column=1, sticky='ew', padx=5, pady=5)
            entries[field] = ent
        form.grid_rowconfigure(idx, weight=0)
    form.grid_columnconfigure(1, weight=1)

    # --- File Upload Section ---
    file_frame = ttk.Labelframe(main_frame, text="Fichiers à joindre", style='Section.TLabelframe')
    file_frame.pack(fill=tk.BOTH, pady=10)

    file_paths = []
    file_listbox = tk.Listbox(file_frame, height=4, font=('Segoe UI', 10))
    file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

    def upload_files():
        files = filedialog.askopenfilenames(filetypes=[("All files", "*.*")])
        for f in files:
            if f not in file_paths:
                file_paths.append(f)
                file_listbox.insert(tk.END, os.path.basename(f))
        print("Current file_paths after upload:", file_paths)

    def remove_selected_file():
        selected_indices = list(file_listbox.curselection())
        if not selected_indices:
            return
        for idx in reversed(selected_indices):
            filename = file_listbox.get(idx)
            for i, path in enumerate(file_paths):
                if os.path.basename(path) == filename:
                    del file_paths[i]
                    break
            file_listbox.delete(idx)
            print(f"Removed: {filename}")
        print("Current file_paths after remove:", file_paths)

    btn_frame = ttk.Frame(file_frame, width=140)
    btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
    btn_frame.pack_propagate(False)

    btn_ajouter = ttk.Button(btn_frame, text="Ajouter Fichiers", command=upload_files)
    btn_ajouter.pack(fill=tk.X, pady=2, anchor='n')

    btn_supprimer = ttk.Button(btn_frame, text="Supprimer", command=remove_selected_file)
    btn_supprimer.pack(fill=tk.X, pady=2, anchor='n')
    
    # --- Status Message ---
    status_label = ttk.Label(main_frame, text="", font=('Segoe UI', 11))
    status_label.pack(pady=5)

    # --- Clear Form Function ---
    def clear_form():
        for field, label in fields:
            widget = entries[field]
            if field == "Graphiste":
                widget.set("")
            elif field in ("Commande", "Remarque"):
                widget.delete("1.0", tk.END)
            else:
                widget.delete(0, tk.END)
        file_paths.clear()
        file_listbox.delete(0, tk.END)

    def process_order_in_background(order, file_paths, client_name):
        def worker():
            while True:
                try:
                    sent_html = send_order_email(order, file_paths, return_html=True)
                    github_filenames, big_files = insert_order(order, file_paths)
                    root.after(0, lambda: status_label.config(
                        text=f"Commande pour {client_name} envoyée et enregistrée !", style='Success.TLabel'))
                    threading.Thread(target=verify_and_resend_if_needed, args=(order, file_paths, sent_html), daemon=True).start()
                    break
                except (requests.exceptions.RequestException, ssl.SSLError, socket.timeout, Exception) as e:
                    print(f"Background order processing failed: {repr(e)}\n{traceback.format_exc()} Retrying in 10s...")
                    root.after(0, lambda: status_label.config(
                        text=f"Traitement en arrière-plan pour {client_name} : {e}. Nouvelle tentative dans 10s...", style='Error.TLabel'))
                    time.sleep(10)
        threading.Thread(target=worker, daemon=True).start()

    # --- Submit Button ---
    def submit():
        order = {}
        for field, label in fields:
            if field == "Graphiste":
                order[field] = entries[field].get()
            elif field in ("Commande", "Remarque"):
                order[field] = entries[field].get("1.0", tk.END).strip()
            else:
                order[field] = entries[field].get()
        if not order["Graphiste"]:
            status_label.config(text="Veuillez sélectionner un graphiste.", style='Error.TLabel')
            return
        if not order["NomClient"] or not order["Numero"]:
            status_label.config(text="Nom du client et numéro sont requis.", style='Error.TLabel')
            return
        # Copy file_paths to avoid mutation during background processing
        order_copy = order.copy()
        file_paths_copy = list(file_paths)
        client_name = order["NomClient"]
        status_label.config(text=f"Commande pour {client_name} en cours de traitement en arrière-plan...", style='Success.TLabel')
        clear_form()
        process_order_in_background(order_copy, file_paths_copy, client_name)
    submit_btn = ttk.Button(main_frame, text="Envoyer la commande", command=submit)
    submit_btn.pack(pady=20, ipadx=10, ipady=5)
    submit_btn.configure(style='Accent.TButton')
    style.configure('Accent.TButton', font=('Segoe UI', 13, 'bold'), foreground='white', background='#4b86b4')
    root.mainloop()

if __name__ == "__main__":
    ensure_github_files_exist()
    try:
        remote_version = get_github_file_content("versionordercreator.txt").strip()
    except Exception as e:
        remote_version = None
        print(f"Could not fetch version from GitHub: {e}")
    if not remote_version:
        remote_version = "1.0.7"  # fallback: allow run if file missing/empty
    if remote_version != "1.0.7":
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Mise à jour requise",
            f"Votre version du logiciel (1.0.6) n'est pas à jour.\nVeuillez télécharger la nouvelle version ({remote_version}) pour continuer."
        )
        webbrowser.open_new("YOUR_UPDATE_DOWNLOAD_URL")
        time.sleep(1)  # Give the browser time to launch
        root.destroy()
        exit()
    run_ui() 