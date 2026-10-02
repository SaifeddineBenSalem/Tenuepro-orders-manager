import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Canvas, Scrollbar
from fpdf import FPDF
from PIL import Image
import datetime
import os
import requests
import csv
import io
import tempfile
import base64
import webbrowser
import threading
import time
import re
import math
from PIL import ImageDraw, ImageFont
import pickle
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import traceback
import random
import string
from bs4 import BeautifulSoup

_font_registered = False  # Track if DejaVu font is registered
# If you do not need Unicode, you can use built-in fonts for faster PDF generation:
# Example: pdf.set_font("Arial", '', 12)

# --- GitHub API utility functions ---
github_token = "YOUR_GITHUB_TOKEN"
github_repo = "ordercreator"
github_owner = "YOUR_GITHUB_USERNAME"  # TODO: Replace with your GitHub username

def github_api_headers(json_mode=False):
    return {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json" if json_mode else "application/vnd.github.v3.raw"
    }

def get_github_file_content(path):
    url = f"https://api.github.com/repos/{github_owner}/{github_repo}/contents/{path}"
    response = requests.get(url, headers=github_api_headers(False))
    response.raise_for_status()
    return response.content.decode("utf-8")

def update_github_file_content(path, content, message="Update file via app"):
    url = f"https://api.github.com/repos/{github_owner}/{github_repo}/contents/{path}"
    get_resp = requests.get(url, headers=github_api_headers(True))
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
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    else:
        content_bytes = content
    data = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
    }
    if sha:
        data["sha"] = sha
    print("\n---------------------\n[GITHUB UPDATE] Path: {}\nSHA: {}\nMessage: {}".format(path, sha, message))
    put_resp = requests.put(url, headers=github_api_headers(True), json=data)
    print("---------------------\n[GITHUB UPDATE RESPONSE] Status: {}\nResponse: {}\n---------------------".format(put_resp.status_code, put_resp.text))
    if put_resp.status_code not in (200, 201):
        print(f"[GITHUB ERROR] Failed to update {path}: {put_resp.status_code} {put_resp.text}")
    put_resp.raise_for_status()
    return put_resp.json()

def get_image_content_from_github(image_name):
    url = f"https://api.github.com/repos/{github_owner}/{github_repo}/contents/uploads/{image_name}"
    response = requests.get(url, headers=github_api_headers())
    response.raise_for_status()
    return response.content

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
            resp = requests.get(url, headers=github_api_headers(True))
            if resp.status_code == 404:
                update_github_file_content(path, default_content, f"Create missing {path}")
                print(f"Created missing {path} on GitHub")
        except Exception as e:
            print(f"Could not check/create {path} on GitHub: {e}")

class PDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_dejavu_font()

    def _register_dejavu_font(self):
        # Only register if not already present on this instance
        if "DejaVu" not in self.fonts or "B" not in self.fonts.get("DejaVu", {}):
            self.add_font("DejaVu", "", "DejaVuSans.ttf", uni=True)
            self.add_font("DejaVu", "B", "DejaVuSans.ttf", uni=True)
            self.add_font("DejaVu", "I", "DejaVuSans.ttf", uni=True)

    def header(self):
        self.set_font("DejaVu", 'B', 14)
        self.set_text_color(255, 0, 0)
        # self.cell(0, 10, f"Ordre de Fabrication n°{self.numero} :", ln=True, align="L")
        # Title removed as requested

    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", "I", 8)
        self.cell(0, 10, f'Créé le {self.date}', 0, 0, 'C')

    def create_order(self, data, image_paths):
        self.numero = data["Numéro"]
        self.date = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        self.add_page()

        self.set_font("DejaVu", "", 12)
        labels = [
            "Nom Client :", "Numéro :", "Type de Personnalisation :", "Commande :", "Nombre Impression :", "Détail LOGO :", "Remarque :", "Graphiste :", "Presseur :"
        ]
        values = [
            data["Nom Client"], data["Numéro"], "", data["Commande"],
            f"10 CM: {data['Nombre Impression 10 CM']}   15 CM: {data['Nombre Impression 15 CM']}   25 CM: {data['Nombre Impression 25 CM']}",
            f"{data['Réf Couleur']} - {data['Police']}", data["Remarque"], data["Graphiste"], data["Presseur"]
        ]
        max_label_w = max(self.get_string_width(label) for label in labels) + 8
        page_w = 210  # A4 width in mm
        margin = 10
        min_img_area = 80
        max_value_w = max(self.get_string_width(str(v)) for v in values) + 12
        max_table_w = page_w - 2 * margin - min_img_area
        value_w = min(max_value_w, max_table_w - max_label_w)
        truncated_values = []
        for v in values:
            v_str = str(v)
            while self.get_string_width(v_str) > value_w - 4 and len(v_str) > 3:
                v_str = v_str[:-4] + '...'
            truncated_values.append(v_str)
        table_total_w = max_label_w + value_w
        y = self.get_y()
        for label, value in zip(labels, truncated_values):
            self.set_xy(margin, y)
            self.cell(max_label_w, 10, label, border=1)
            self.cell(value_w, 10, value, border=1, ln=True)
            y += 10
        # Type de Personnalisation row (special)
        self.set_xy(margin, y)
        self.cell(max_label_w + value_w, 10, "Type de Personnalisation :", border=1, ln=True)
        y += 10
        self.set_xy(margin, y)
        self.cell(max_label_w, 10, "Impression", border=1)
        self.cell(value_w/2, 10, "☑" if data["Impression"] else "☐", border=1)
        self.cell(max_label_w, 10, "Broderie", border=1)
        self.cell(value_w/2, 10, "☑" if data["Broderie"] else "☐", border=1, ln=True)
        y += 10
        table_end_y = y
        n_images = len(image_paths)
        # Decide layout: side-by-side or images below
        side_by_side = (page_w - (margin + table_total_w + margin)) >= min_img_area and n_images > 0
        if side_by_side:
            image_x = margin + table_total_w + 8
            image_area_w = page_w - image_x - margin
            max_image_w = image_area_w
            max_image_h = (297 - margin - table_end_y - 10) / n_images
            image_y = table_end_y + 4
            for img_path in image_paths:
                try:
                    with Image.open(img_path) as img:
                        img_w, img_h = img.size
                        aspect = img_w / img_h
                        # Fit image in cell
                        if (max_image_w / aspect) <= max_image_h:
                            w = max_image_w
                            h = max_image_w / aspect
                        else:
                            h = max_image_h
                            w = max_image_h * aspect
                        self.image(img_path, x=image_x, y=image_y, w=w, h=h)
                        image_y += max_image_h
                except Exception:
                    w, h = max_image_w, max_image_h
                y_offset = (max_image_h - h) / 2 if h < max_image_h else 0
                self.image(img_path, x=image_x, y=image_y + y_offset, w=w, h=h)
                image_y += max_image_h
        elif n_images > 0:
            # Place images below the table, use full width
            image_y = table_end_y + 8
            available_h = 297 - margin - image_y
            max_image_h = available_h / n_images
            max_image_w = page_w - 2 * margin
            for img_path in image_paths:
                try:
                    with Image.open(img_path) as img:
                        img_w, img_h = img.size
                        aspect = img_w / img_h
                        # Fit image in cell
                        if (max_image_w / aspect) <= max_image_h:
                            w = max_image_w
                            h = max_image_w / aspect
                        else:
                            h = max_image_h
                            w = max_image_h * aspect
                        self.image(img_path, x=margin + (max_image_w - w) / 2, y=image_y, w=w, h=h)
                        image_y += max_image_h
                except Exception:
                    w, h = max_image_w, max_image_h
                x_img = margin + (max_image_w - w) / 2
                y_offset = (max_image_h - h) / 2 if h < max_image_h else 0
                self.image(img_path, x=x_img, y=image_y + y_offset, w=w, h=h)
                image_y += max_image_h

class FabricationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Fabrication Form - Pro Edition")
        self.root.geometry("600x700")
        self.root.minsize(500, 600)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', font=('Segoe UI', 11))
        style.configure('TButton', font=('Segoe UI', 11, 'bold'), padding=6)
        style.configure('Header.TLabel', font=('Segoe UI', 16, 'bold'), foreground='#2a4d69')
        style.configure('Section.TLabelframe.Label', font=('Segoe UI', 13, 'bold'), foreground='#4b86b4')
        style.configure('Accent.TButton', font=('Segoe UI', 12, 'bold'), foreground='white', background='#4b86b4')
        style.configure('Success.TLabel', foreground='green', font=('Segoe UI', 11, 'bold'))
        style.configure('Error.TLabel', foreground='red', font=('Segoe UI', 11, 'bold'))

        main_frame = ttk.Frame(root, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Nouvelle Ordre de Fabrication", style='Header.TLabel').pack(pady=(0, 15))

        # --- Client Info ---
        client_frame = ttk.Labelframe(main_frame, text="Informations Client", style='Section.TLabelframe')
        client_frame.pack(fill=tk.X, pady=8)
        self.fields = {}
        row = 0
        for label in ["Nom Client", "Numéro", "Réf Couleur", "Police", "Graphiste", "Presseur"]:
            ttk.Label(client_frame, text=label).grid(row=row, column=0, sticky='w', padx=5, pady=5)
            entry = ttk.Entry(client_frame, width=30)
            entry.grid(row=row, column=1, sticky='ew', padx=5, pady=5)
            self.fields[label] = entry
            client_frame.grid_rowconfigure(row, weight=0)
            row += 1
        client_frame.grid_columnconfigure(1, weight=1)

        # --- Commande & Remarque ---
        details_frame = ttk.Labelframe(main_frame, text="Détails de la Commande", style='Section.TLabelframe')
        details_frame.pack(fill=tk.X, pady=8)
        ttk.Label(details_frame, text="Commande").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.commande_text = tk.Text(details_frame, height=3, width=30, font=('Segoe UI', 10))
        self.commande_text.grid(row=0, column=1, sticky='ew', padx=5, pady=5)
        ttk.Label(details_frame, text="Remarque").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.remarque_text = tk.Text(details_frame, height=2, width=30, font=('Segoe UI', 10))
        self.remarque_text.grid(row=1, column=1, sticky='ew', padx=5, pady=5)
        details_frame.grid_columnconfigure(1, weight=1)

        # --- Nombre Impression ---
        ni_frame = ttk.Labelframe(main_frame, text="Nombre d'Impression", style='Section.TLabelframe')
        ni_frame.pack(fill=tk.X, pady=8)
        self.ni_10 = ttk.Entry(ni_frame, width=10)
        self.ni_15 = ttk.Entry(ni_frame, width=10)
        self.ni_25 = ttk.Entry(ni_frame, width=10)
        ttk.Label(ni_frame, text="10 CM").grid(row=0, column=0, padx=5, pady=5)
        self.ni_10.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(ni_frame, text="15 CM").grid(row=0, column=2, padx=5, pady=5)
        self.ni_15.grid(row=0, column=3, padx=5, pady=5)
        ttk.Label(ni_frame, text="25 CM").grid(row=0, column=4, padx=5, pady=5)
        self.ni_25.grid(row=0, column=5, padx=5, pady=5)
        ni_frame.grid_columnconfigure(6, weight=1)

        # --- Type de Personnalisation ---
        type_frame = ttk.Labelframe(main_frame, text="Type de Personnalisation", style='Section.TLabelframe')
        type_frame.pack(fill=tk.X, pady=8)
        self.impression_var = tk.BooleanVar()
        self.broderie_var = tk.BooleanVar()
        ttk.Checkbutton(type_frame, text="Impression", variable=self.impression_var).pack(side=tk.LEFT, padx=10, pady=5)
        ttk.Checkbutton(type_frame, text="Broderie", variable=self.broderie_var).pack(side=tk.LEFT, padx=10, pady=5)

        # --- Image Upload Section ---
        img_frame = ttk.Labelframe(main_frame, text="Images à joindre", style='Section.TLabelframe')
        img_frame.pack(fill=tk.BOTH, pady=8)
        self.image_paths = []
        self.img_listbox = tk.Listbox(img_frame, height=4, font=('Segoe UI', 10))
        self.img_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        btn_frame = ttk.Frame(img_frame, width=120)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)
        btn_frame.pack_propagate(False)
        ttk.Button(btn_frame, text="Ajouter Images", command=self.upload_images).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Supprimer", command=self.remove_selected_image).pack(fill=tk.X, pady=2)

        # --- Status Message ---
        self.status_label = ttk.Label(main_frame, text="", font=('Segoe UI', 11))
        self.status_label.pack(pady=5)

        # --- Submit Button ---
        submit_btn = ttk.Button(main_frame, text="Générer PDF", command=self.generate_pdf, style='Accent.TButton')
        submit_btn.pack(pady=20, ipadx=10, ipady=5)

    def upload_images(self):
        files = filedialog.askopenfilenames(filetypes=[("Image files", "*.png;*.jpg;*.jpeg")])
        for f in files:
            if f not in self.image_paths:
                self.image_paths.append(f)
                self.img_listbox.insert(tk.END, os.path.basename(f))
        self.status_label.config(text=f"{len(files)} images ajoutées.", style='Success.TLabel')

    def remove_selected_image(self):
        selected_indices = list(self.img_listbox.curselection())
        if not selected_indices:
            return
        for idx in reversed(selected_indices):
            filename = self.img_listbox.get(idx)
            for i, path in enumerate(self.image_paths):
                if os.path.basename(path) == filename:
                    del self.image_paths[i]
                    break
            self.img_listbox.delete(idx)
        self.status_label.config(text="Image supprimée.", style='Success.TLabel')

    def generate_pdf(self):
        data = {key: entry.get() for key, entry in self.fields.items()}
        data["Commande"] = self.commande_text.get("1.0", tk.END).strip()
        data["Remarque"] = self.remarque_text.get("1.0", tk.END).strip()
        data["Nombre Impression 10 CM"] = self.ni_10.get()
        data["Nombre Impression 15 CM"] = self.ni_15.get()
        data["Nombre Impression 25 CM"] = self.ni_25.get()
        data["Impression"] = self.impression_var.get()
        data["Broderie"] = self.broderie_var.get()
        try:
            pdf = PDF()
            pdf.create_order(data, self.image_paths)
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            numero = normalize_filename(data.get('Numéro', 'order'))
            filename = os.path.join(desktop_path, f"ordre_fabrication_{numero}_{timestamp}.pdf")
            pdf.output(filename)
            self.status_label.config(text="PDF créé avec succès !", style='Success.TLabel')
            messagebox.showinfo("PDF Saved", f"{filename} a été créé.")
        except Exception as e:
            self.status_label.config(text=f"Erreur lors de la création du PDF : {e}", style='Error.TLabel')
            messagebox.showerror("Erreur", f"Erreur lors de la création du PDF : {e}")

class OrdersApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Orders Table - Pro Edition")
        self.status_filter = tk.StringVar(value="all")
        self.graphiste_filter = tk.StringVar(value="all")
        self.search_var = tk.StringVar()
        self.data = []
        self.filtered_data = []
        self.fieldnames = []
        self.page_size = 9  # Show 9 rows per page
        self.current_page = 0
        self.load_data()
        self.create_widgets()
        self.refresh_table()

    def load_data(self):
        chaima_rows = load_csv_from_github("chaima.csv")
        yosr_rows = load_csv_from_github("yosr.csv")
        self.data = chaima_rows + yosr_rows
        if self.data:
            self.fieldnames = list(self.data[0].keys())
        else:
            self.fieldnames = [
                "NomClient", "Numero", "TypePersonnalisation", "Commande",
                "NombreD'impression10CM", "NombreD'impression15CM", "NombreD'Impression25CM",
                "RefColor", "Police", "Remarque", "Graphiste", "Presseur", "status", "BunchOfImagesNames"
            ]

    def create_widgets(self):
        # --- Main Title ---
        title_label = tk.Label(self.root, text="Orders Management", font=("Segoe UI", 20, "bold"), fg="#2a4d69")
        title_label.pack(pady=(10, 0))
        # --- Filter/Search Row ---
        filter_frame = tk.Frame(self.root, bg="#f0f4fa", bd=2, relief=tk.RIDGE)
        filter_frame.pack(fill=tk.X, padx=5, pady=8)
        # Status filter
        tk.Label(filter_frame, text="Filter by status:", bg="#f0f4fa").pack(side=tk.LEFT, padx=(8,0))
        status_options = ["all", "pending", "printed"]
        filter_menu = ttk.Combobox(filter_frame, textvariable=self.status_filter, values=status_options, state="readonly", width=10)
        filter_menu.pack(side=tk.LEFT, padx=(0, 10))
        filter_menu.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())
        # Graphiste filter
        tk.Label(filter_frame, text="Graphiste:", bg="#f0f4fa").pack(side=tk.LEFT)
        graphiste_options = ["all", "chaima", "yosr"]
        graphiste_menu = ttk.Combobox(filter_frame, textvariable=self.graphiste_filter, values=graphiste_options, state="readonly", width=10)
        graphiste_menu.pack(side=tk.LEFT, padx=(0, 10))
        graphiste_menu.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())
        # Search
        tk.Label(filter_frame, text="Search:", bg="#f0f4fa").pack(side=tk.LEFT)
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=(0, 10))
        search_entry.bind("<KeyRelease>", lambda e: self.refresh_table())
        # Print All button
        tk.Button(filter_frame, text="Print All", command=self.print_all, bg="#4b86b4", fg="white", font=("Segoe UI", 10, "bold")).pack(side=tk.RIGHT, padx=(8, 8))
        # Refresh button
        tk.Button(filter_frame, text="Refresh", command=self.refresh_data, bg="#e0e0e0", font=("Segoe UI", 10)).pack(side=tk.RIGHT, padx=(0, 5))
        # Filter Gmail button
        filter_gmail_btn = tk.Button(filter_frame, text="Filter Gmail", command=self.run_filter_gmail, bg="#a084ca", fg="white", font=("Segoe UI", 10, "bold"))
        filter_gmail_btn.pack(side=tk.RIGHT, padx=(0, 8))
        # --- Table Section ---
        table_frame = tk.Frame(self.root)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        # Horizontal scrollbar
        x_scroll = tk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        x_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        # Vertical scrollbar
        y_scroll = tk.Scrollbar(table_frame, orient=tk.VERTICAL)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        # --- Treeview Style for Font and Row Height ---
        style = ttk.Style()
        style.configure("Custom.Treeview", font=("Segoe UI", 13), rowheight=38)
        style.configure("Custom.Treeview.Heading", font=("Segoe UI", 14, "bold"))
        style.map('Treeview', background=[('selected', '#ececec')])
        # Table
        self.tree = ttk.Treeview(table_frame, columns=self.fieldnames, show="headings", xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set, style="Custom.Treeview")
        for col in self.fieldnames:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120, anchor='w', minwidth=80)
        self.tree.pack(fill=tk.BOTH, expand=True)
        x_scroll.config(command=self.tree.xview)
        y_scroll.config(command=self.tree.yview)
        self.tree.tag_configure('pending', background='#d1b3ff')  # purple
        self.tree.tag_configure('printed', background='#b3ffb3')  # green
        self.tree.bind("<Double-1>", self.on_row_double_click)
        # --- Auto-expand columns to fill table ---
        def resize_columns(event):
            total_width = event.width
            n_cols = len(self.fieldnames)
            max_col_width = 250
            min_col_width = 80
            col_width = max(min_col_width, min(max_col_width, int(total_width / n_cols)))
            for col in self.fieldnames:
                self.tree.column(col, width=col_width, minwidth=min_col_width, stretch=True)
        table_frame.bind("<Configure>", resize_columns)
        # --- Pagination Controls ---
        pag_frame = tk.Frame(self.root)
        pag_frame.pack(fill=tk.X, padx=8, pady=(0, 10))
        self.prev_btn = ttk.Button(pag_frame, text="Previous", command=self.prev_page)
        self.prev_btn.pack(side=tk.LEFT)
        self.page_label = tk.Label(pag_frame, text="Page 1/1", font=("Segoe UI", 11))
        self.page_label.pack(side=tk.LEFT, padx=12)
        self.next_btn = ttk.Button(pag_frame, text="Next", command=self.next_page)
        self.next_btn.pack(side=tk.LEFT)

        # --- Add status label for filter progress ---
        self.status_label = tk.Label(self.root, text="", font=("Segoe UI", 11))
        self.status_label.pack(pady=5)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh_table()

    def next_page(self):
        max_page = max(0, (len(self.filtered_data) - 1) // self.page_size)
        if self.current_page < max_page:
            self.current_page += 1
            self.refresh_table()

    def refresh_data(self):
        self.load_data()
        self.refresh_table()

    def refresh_table(self):
        # --- Filtering and searching ---
        search = self.search_var.get().lower().strip()
        status = self.status_filter.get()
        graphiste = self.graphiste_filter.get()
        def row_matches(entry):
            # Exclude photo columns from search
            search_columns = [k for k in self.fieldnames if not ("BunchOfImagesNames" in k or "BunchOfPhotos" in k)]
            if search:
                found = False
                for k in search_columns:
                    v = str(entry.get(k, "")).lower()
                    if search in v:
                        found = True
                        break
                if not found:
                    return False
            if status != "all" and entry.get("status", "").lower() != status:
                return False
            if graphiste != "all" and entry.get("Graphiste", "").strip().lower() != graphiste:
                return False
            return True
        self.filtered_data = [entry for entry in self.data if row_matches(entry)]
        # --- Pagination ---
        total_pages = max(1, (len(self.filtered_data) - 1) // self.page_size + 1)
        self.current_page = min(self.current_page, total_pages - 1)
        start_idx = self.current_page * self.page_size
        end_idx = start_idx + self.page_size
        page_data = self.filtered_data[start_idx:end_idx]
        # --- Update table ---
        for row in self.tree.get_children():
            self.tree.delete(row)
        for entry in page_data:
            row_status = entry.get("status", "").lower()
            tag = row_status if row_status in ("pending", "printed") else ""
            values = [entry.get(f, "") for f in self.fieldnames]
            self.tree.insert("", "end", values=values, tags=(tag,))
        # --- Update pagination label and buttons ---
        self.page_label.config(text=f"Page {self.current_page+1}/{total_pages}")
        self.prev_btn.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL if self.current_page < total_pages-1 else tk.DISABLED)

    def on_row_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        values = self.tree.item(item, "values")
        if not values:
            return
        entry = None
        # Find the entry in filtered_data by Numero (unique)
        numero_idx = self.fieldnames.index("Numero") if "Numero" in self.fieldnames else 1
        numero = values[numero_idx]
        for e in self.filtered_data:
            if str(e.get("Numero", "")) == str(numero):
                entry = e
                break
        if entry:
            self.show_order_detail(entry)

    def show_order_detail(self, entry):
        detail_win = tk.Toplevel(self.root)
        detail_win.title(f"Order Details - {entry.get('Numero', '')}")
        detail_win.geometry("900x500")
        detail_win.configure(bg="#f7f7fa")
        # --- Order info ---
        info_frame = tk.Frame(detail_win, bg="#f7f7fa")
        info_frame.pack(fill=tk.X, padx=20, pady=10)
        title = tk.Label(info_frame, text=f"Order #{entry.get('Numero', '')}", font=("Segoe UI", 18, "bold"), fg="#2a4d69", bg="#f7f7fa")
        title.pack(anchor="w")
        subtitle = tk.Label(info_frame, text=f"Client: {entry.get('NomClient', '')} | Graphiste: {entry.get('Graphiste', '')} | Status: {entry.get('status', '').capitalize()}", font=("Segoe UI", 12), fg="#4b86b4", bg="#f7f7fa")
        subtitle.pack(anchor="w", pady=(0, 8))
        # Structured details
        key_10 = "NombreD'impression10CM"
        key_15 = "NombreD'impression15CM"
        key_25 = "NombreD'Impression25CM"
        fields = [
            ("Nom Client", entry.get("NomClient", "")),
            ("Numéro", entry.get("Numero", "")),
            ("Type Perso", entry.get("TypePersonnalisation", "")),
            ("Commande", entry.get("Commande", "")),
            ("Nombre Impression", f"10CM: {entry.get(key_10, '')} | 15CM: {entry.get(key_15, '')} | 25CM: {entry.get(key_25, '')}"),
            ("Réf Couleur", entry.get("RefColor", "")),
            ("Police", entry.get("Police", "")),
            ("Remarque", entry.get("Remarque", "")),
            ("Graphiste", entry.get("Graphiste", "")),
            ("Presseur", entry.get("Presseur", "")),
        ]
        y = margin  # Ensure y is initialized before any use
        # First, collect all value lines to determine the max width needed
        all_value_lines = []
        for label, value in fields:
            value_str = str(value)
            lines = value_str.splitlines()
            if len(lines) > 10:
                max_pairs = 10
                pairs = []
                max_lines = min(len(lines), max_pairs * 2)
                i = 0
                while i < max_lines:
                    if i+1 < max_lines:
                        pairs.append(lines[i] + ' || ' + lines[i+1])
                        i += 2
                    else:
                        pairs.append(lines[i])
                        i += 1
                value_lines_to_display = pairs
            else:
                value_lines_to_display = lines
            all_value_lines.extend(value_lines_to_display)
        # Calculate the max width needed for any value line
        pdf.set_font("DejaVu", '', value_font_size)
        max_value_w = max(pdf.get_string_width(line) for line in all_value_lines) + 4
        # Calculate max label width
        pdf.set_font("DejaVu", '', label_font_size)
        max_label_w = max(pdf.get_string_width(label + ":") + 4 for label, _ in fields)
        # Limit to available page width
        max_value_w = min(max_value_w, page_w - 2 * margin - max_label_w)
        table_w = max_label_w + max_value_w
        y = margin  # Ensure y is initialized here, before the drawing loop
        for label, value in fields:
            pdf.set_font("DejaVu", '', value_font_size)
            value_str = str(value)
            lines = value_str.splitlines()
            if len(lines) > 10:
                max_pairs = 10
                pairs = []
                max_lines = min(len(lines), max_pairs * 2)
                i = 0
                while i < max_lines:
                    if i+1 < max_lines:
                        pairs.append(lines[i] + ' || ' + lines[i+1])
                        i += 2
                    else:
                        pairs.append(lines[i])
                        i += 1
                    value_lines_to_display = pairs
                else:
                    value_lines_to_display = lines
                n_lines = max(1, len(value_lines_to_display))
                cell_height = 9 * n_lines
                # Draw label cell (single cell, height = cell_height)
                pdf.set_xy(margin, y)
                pdf.set_font("DejaVu", '', label_font_size)
                pdf.cell(max_label_w, cell_height, label + ":", border=1, align='L')
                # Draw value cell (multi_cell for line breaks and border)
                pdf.set_xy(margin + max_label_w, y)
                pdf.set_font("DejaVu", '', value_font_size)
                pdf.multi_cell(max_value_w, 9, '\n'.join(value_lines_to_display), border=1, align='L')
                y += cell_height
            table_end_y = y
            # --- Images placement: maximize size, use a grid that fills the available space ---
            images_str = entry.get("BunchOfPhotos") or entry.get("BunchOfImagesNames") or ""
            images = [img.strip() for img in images_str.split(",") if img.strip()]
            images = [normalize_filename(img) for img in images]
            print(f"[DEBUG] Images before extension filter for Numero={entry.get('Numero','')}: {images}")
            allowed_exts = {'.jpg', '.jpeg', '.png', '.bmp'}
            images = [img for img in images if os.path.splitext(img)[1].lower() in allowed_exts]
            print(f"[DEBUG] Images after extension filter for Numero={entry.get('Numero','')}: {images}")
            n_images = len(images)
            if n_images > 0:
                # Define the area for the image grid (to the right of the table, using most of the page)
                grid_x = margin + table_w + 40
                grid_y = margin
                grid_w = page_w - grid_x - margin
                grid_h = page_h - 2 * margin
                # Find the optimal grid (cols, rows) to maximize image size
                best_cols = 1
                best_size = 0
                for cols in range(1, n_images + 1):
                    rows = math.ceil(n_images / cols)
                    cell_w = grid_w / cols
                    cell_h = grid_h / rows
                    size = min(cell_w, cell_h)
                    if size > best_size:
                        best_size = size
                        best_cols = cols
                n_cols = best_cols
                n_rows = math.ceil(n_images / n_cols)
                cell_w = grid_w / n_cols
                cell_h = grid_h / n_rows
                for idx, img_name in enumerate(images):
                    try:
                        img_path = None
                        if image_cache and img_name in image_cache and image_cache[img_name]:
                            img_path = image_cache[img_name]
                        else:
                            img_content = get_image_content_from_github(img_name)
                            img_temp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(img_name)[1])
                            img_temp.write(img_content)
                            img_temp.close()
                            img_path = img_temp.name
                        with Image.open(img_path) as pil_img:
                            img_w0, img_h0 = pil_img.size
                            aspect = img_w0 / img_h0
                            # Fit image in cell
                            if (cell_w / aspect) <= cell_h:
                                w = int(cell_w)
                                h = int(cell_w / aspect)
                            else:
                                h = int(cell_h)
                                w = int(cell_h * aspect)
                            col = idx % n_cols
                            row = idx // n_cols
                            x_img = int(grid_x + col * cell_w + (cell_w - w) / 2)
                            y_img = int(grid_y + row * cell_h + (cell_h - h) / 2)
                            pil_img = pil_img.resize((w, h), Image.LANCZOS)
                            img.paste(pil_img, (x_img, y_img))
                        if not (image_cache and img_name in image_cache and image_cache[img_name]):
                            os.remove(img_path)
                    except Exception as e:
                        print(f"Error adding image {img_name}: {e}")
        # Save image
        numero = normalize_filename(entry.get("Numero", "order"))
        out_path = os.path.join(output_dir, f"order_{numero}.png")
        print(f"[DEBUG] Saving image to: {out_path}")
        img.save(out_path)

    def print_all(self):
        # Select all pending rows
        pending_entries = [row for row in self.data if row.get("status", "").lower() == "pending"]
        if not pending_entries:
            messagebox.showinfo("No Pending", "No pending entries to print.")
            return
        # Show loading window with progress bar
        loading_win = tk.Toplevel(self.root)
        loading_win.title("Veuillez patienter")
        loading_win.geometry("420x180")
        loading_win.transient(self.root)
        loading_win.grab_set()
        loading_win.resizable(False, False)
        status_label = tk.Label(loading_win, text="Génération des images en cours...", font=("Segoe UI", 12))
        status_label.pack(pady=(18, 8))
        progress = ttk.Progressbar(loading_win, mode="indeterminate", length=320)
        progress.pack(pady=(0, 18))
        progress.start(10)
        def do_generate_images():
            try:
                import shutil
                print("[DEBUG] Starting do_generate_images")
                output_dir = get_output_dir()
                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                os.makedirs(output_dir, exist_ok=True)
                # --- Image cache: {img_name: resized_temp_path} ---
                image_cache = {}
                all_image_names = set()
                for entry in pending_entries:
                    images_str = entry.get("BunchOfPhotos") or entry.get("BunchOfImagesNames") or ""
                    images = [img.strip() for img in images_str.split(",") if img.strip()]
                    images = [normalize_filename(img) for img in images]
                    allowed_exts = {'.jpg', '.jpeg', '.png', '.bmp'}
                    images = [img for img in images if os.path.splitext(img)[1].lower() in allowed_exts]
                    all_image_names.update(images)
                print(f"[DEBUG] Downloading and resizing {len(all_image_names)} unique images for all orders...")
                for img_name in all_image_names:
                    try:
                        img_content = get_image_content_from_github(img_name)
                        img_temp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(img_name)[1])
                        img_temp.write(img_content)
                        img_temp.close()
                        # Resize and cache as PNG (for Tkinter and PIL)
                        with Image.open(img_temp.name) as img:
                            img.thumbnail((600, 600))  # adjust size as needed
                            resized_temp = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                            img.save(resized_temp.name, format='PNG')
                            resized_temp.close()
                            image_cache[img_name] = resized_temp.name
                        os.remove(img_temp.name)  # remove original temp
                        print(f"[DEBUG] Cached resized image: {img_name}")
                    except Exception as e:
                        print(f"[ERROR] Failed to cache image {img_name}: {e}")
                        image_cache[img_name] = None
                for idx, entry in enumerate(pending_entries):
                    print(f"[DEBUG] Processing order {idx+1}/{len(pending_entries)}: Numero={entry.get('Numero','')}")
                    try:
                        self.add_entry_to_image(entry, image_cache=image_cache, output_dir=output_dir)
                        print(f"[DEBUG] Finished adding entry to image: Numero={entry.get('Numero','')}")
                    except Exception as e:
                        print(f"[ERROR] Exception in add_entry_to_image for Numero={entry.get('Numero','')}: {e}")
                # Clean up temp image files
                print("[DEBUG] Cleaning up temp image files...")
                for img_name, img_path in image_cache.items():
                    if img_path and os.path.exists(img_path):
                        try:
                            os.remove(img_path)
                            print(f"[DEBUG] Deleted temp file: {img_path}")
                        except Exception as e:
                            print(f"[ERROR] Could not delete temp file {img_path}: {e}")
                print("[DEBUG] Updating statuses and moving rows")
                try:
                    self.update_status_and_move(pending_entries)
                    print("[DEBUG] Status update complete")
                except Exception as e:
                    print(f"[ERROR] Exception during status update: {e}")
                    raise
                print("[DEBUG] Reloading data and refreshing table")
                try:
                    self.load_data()
                    self.refresh_table()
                    print("[DEBUG] Data reload and table refresh complete")
                except Exception as e:
                    print(f"[ERROR] Exception during data reload/refresh: {e}")
                # Combine all images into a single PDF
                def images_to_pdf(image_folder, output_pdf_path):
                    from PIL import Image
                    import os
                    image_files = sorted([
                        os.path.join(image_folder, f)
                        for f in os.listdir(image_folder)
                        if f.lower().endswith('.png')
                    ])
                    if not image_files:
                        print("No images found to combine.")
                        return False
                    images = [Image.open(f).convert('RGB') for f in image_files]
                    images[0].save(output_pdf_path, save_all=True, append_images=images[1:])
                    print(f"PDF saved to {output_pdf_path}")
                    return True
                # Announce PDF generation in the progress bar
                status_label.config(text="Génération du PDF en cours...")
                progress.start(10)
                pdf_path = os.path.join(output_dir, "all_orders.pdf")
                pdf_success = images_to_pdf(output_dir, pdf_path)
                if pdf_success:
                    print(f"[DEBUG] PDF generated at {pdf_path}")
                else:
                    print("[ERROR] PDF generation failed (no images found)")
                def after_generate():
                    progress.stop()
                    loading_win.destroy()
                    messagebox.showinfo("Images & PDF Saved", f"Images created in: {output_dir}\nPDF created: {pdf_path}")
                self.root.after(0, after_generate)
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                print(f"[FATAL ERROR] Exception in do_generate_images: {e}\n{tb}")
                def after_error(e=e):
                    progress.stop()
                    loading_win.destroy()
                    messagebox.showerror("Error", f"An error occurred while generating images: {e}\nSee console for details.")
                self.root.after(0, after_error)
        threading.Thread(target=do_generate_images, daemon=True).start()

    def add_entry_to_image(self, entry, image_cache=None, output_dir=None):
        print(f"[DEBUG] add_entry_to_image called for Numero={entry.get('Numero', 'order')}, output_dir={output_dir}")
        if output_dir is None:
            output_dir = get_output_dir()
        # Output image size (A4 landscape at 150dpi: 3508x2480 px)
        page_w, page_h = 3508, 2480
        margin = 60
        label_font_size = 33
        value_font_size = 33
        min_value_w = 200
        max_table_w = int(page_w * 0.55)
        # Use a default font
        try:
            font_label = ImageFont.truetype("arial.ttf", label_font_size)
            font_value = ImageFont.truetype("arial.ttf", value_font_size)
        except Exception:
            font_label = font_value = None
        img = Image.new('RGB', (page_w, page_h), 'white')
        draw = ImageDraw.Draw(img)
        def get_multiline_text_width(text, font):
            lines = str(text).splitlines() or [""]
            return max(draw.textlength(line, font=font) for line in lines)
        key_10 = "NombreD'impression10CM"
        key_15 = "NombreD'impression15CM"
        key_25 = "NombreD'Impression25CM"
        fields = [
            ("Nom Client", entry.get("NomClient", "")),
            ("Numéro", entry.get("Numero", "")),
            ("Type Perso", entry.get("TypePersonnalisation", "")),
            ("Commande", entry.get("Commande", "")),
            ("Nombre Impression", f"10CM: {entry.get(key_10, '')} | 15CM: {entry.get(key_15, '')} | 25CM: {entry.get(key_25, '')}"),
            ("Réf Couleur", entry.get("RefColor", "")),
            ("Police", entry.get("Police", "")),
            ("Remarque", entry.get("Remarque", "")),
            ("Graphiste", entry.get("Graphiste", "")),
            ("Presseur", entry.get("Presseur", "")),
        ]
        # Calculate max label and value width
        max_label_w = 0
        max_value_w = min_value_w
        for label, value in fields:
            label_w = get_multiline_text_width(label + ":", font_label)
            max_label_w = max(max_label_w, label_w)
            value_w = get_multiline_text_width(value, font_value)
            max_value_w = max(max_value_w, value_w)
        max_label_w += 20
        max_value_w = min(max_value_w + 40, page_w - 2 * margin - max_label_w)
        table_w = max_label_w + max_value_w
        y = margin
        for label, value in fields:
            value_lines = str(value).splitlines() or [""]
            if font_value:
                if hasattr(font_value, "getbbox"):
                    bbox = font_value.getbbox("A")
                    line_height = bbox[3] - bbox[1]
                else:
                    bbox = draw.textbbox((0,0), "A", font=font_value)
                    line_height = bbox[3] - bbox[1]
            else:
                line_height = 32
            line_gap = 8  # Add vertical gap between lines
            cell_padding_top = 10
            cell_padding_bottom = 10
            num_lines = len(value_lines)
            cell_height = max(60, cell_padding_top + cell_padding_bottom + (line_height + line_gap) * num_lines - line_gap)
            label_box = (margin, y, margin + max_label_w, y + cell_height)
            value_box = (margin + max_label_w, y, margin + max_label_w + max_value_w, y + cell_height)
            draw.rectangle(label_box, outline="black", width=2)
            draw.rectangle(value_box, outline="black", width=2)
            draw.text((margin + 10, y + cell_padding_top), label + ":", fill="black", font=font_label)
            for i, line in enumerate(value_lines):
                draw.text((margin + max_label_w + 10, y + cell_padding_top + i * (line_height + line_gap)), line, fill="black", font=font_value)
            y += cell_height
        table_end_y = y
        # --- Images placement: maximize size, use a grid that fills the available space ---
        images_str = entry.get("BunchOfPhotos") or entry.get("BunchOfImagesNames") or ""
        images = [img.strip() for img in images_str.split(",") if img.strip()]
        images = [normalize_filename(img) for img in images]
        print(f"[DEBUG] Images before extension filter for Numero={entry.get('Numero','')}: {images}")
        allowed_exts = {'.jpg', '.jpeg', '.png', '.bmp'}
        images = [img for img in images if os.path.splitext(img)[1].lower() in allowed_exts]
        print(f"[DEBUG] Images after extension filter for Numero={entry.get('Numero','')}: {images}")
        n_images = len(images)
        if n_images > 0:
            # Define the area for the image grid (to the right of the table, using most of the page)
            grid_x = margin + table_w + 40
            grid_y = margin
            grid_w = page_w - grid_x - margin
            grid_h = page_h - 2 * margin
            # Find the optimal grid (cols, rows) to maximize image size
            best_cols = 1
            best_size = 0
            for cols in range(1, n_images + 1):
                rows = math.ceil(n_images / cols)
                cell_w = grid_w / cols
                cell_h = grid_h / rows
                size = min(cell_w, cell_h)
                if size > best_size:
                    best_size = size
                    best_cols = cols
            n_cols = best_cols
            n_rows = math.ceil(n_images / n_cols)
            cell_w = grid_w / n_cols
            cell_h = grid_h / n_rows
            for idx, img_name in enumerate(images):
                try:
                    img_path = None
                    if image_cache and img_name in image_cache and image_cache[img_name]:
                        img_path = image_cache[img_name]
                    else:
                        img_content = get_image_content_from_github(img_name)
                        img_temp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(img_name)[1])
                        img_temp.write(img_content)
                        img_temp.close()
                        img_path = img_temp.name
                    with Image.open(img_path) as pil_img:
                        img_w0, img_h0 = pil_img.size
                        aspect = img_w0 / img_h0
                        # Fit image in cell
                        if (cell_w / aspect) <= cell_h:
                            w = int(cell_w)
                            h = int(cell_w / aspect)
                        else:
                            h = int(cell_h)
                            w = int(cell_h * aspect)
                        col = idx % n_cols
                        row = idx // n_cols
                        x_img = int(grid_x + col * cell_w + (cell_w - w) / 2)
                        y_img = int(grid_y + row * cell_h + (cell_h - h) / 2)
                        pil_img = pil_img.resize((w, h), Image.LANCZOS)
                        img.paste(pil_img, (x_img, y_img))
                    if not (image_cache and img_name in image_cache and image_cache[img_name]):
                        os.remove(img_path)
                except Exception as e:
                    print(f"Error adding image {img_name}: {e}")
        # Save image
        numero = normalize_filename(entry.get("Numero", "order"))
        out_path = os.path.join(output_dir, f"order_{numero}.png")
        print(f"[DEBUG] Saving image to: {out_path}")
        img.save(out_path)

    def update_status_and_move(self, pending_entries):
        # Load all CSVs
        chaima_rows = load_csv_from_github("chaima.csv")
        yosr_rows = load_csv_from_github("yosr.csv")
        try:
            chaimadone_rows = load_csv_from_github("chaimadone.csv")
        except Exception:
            chaimadone_rows = []
        try:
            yosrdone_rows = load_csv_from_github("yosrdone.csv")
        except Exception:
            yosrdone_rows = []

        print(f"Before: chaima_rows={len(chaima_rows)}, yosr_rows={len(yosr_rows)}, chaimadone_rows={len(chaimadone_rows)}, yosrdone_rows={len(yosrdone_rows)}")
        print(f"Fieldnames: {self.fieldnames}")

        # Normalize Numero for all rows
        def norm_num(row):
            return str(row.get("Numero", "")).strip()

        printed_numeros = set()
        for entry in pending_entries:
            entry["status"] = "printed"
            graphiste = (entry.get("Graphiste", "") or "").strip().lower()
            numero = str(entry.get("Numero", "")).strip()
            printed_numeros.add(numero)
            print(f"Marking Numero={numero} as printed, Graphiste={graphiste}")
            if graphiste == "chaima":
                chaimadone_rows.append(entry)
            elif graphiste == "yosr":
                yosrdone_rows.append(entry)
            else:
                print(f"Unknown graphiste: {graphiste}")

        chaima_rows_new = [r for r in chaima_rows if norm_num(r) not in printed_numeros]
        yosr_rows_new = [r for r in yosr_rows if norm_num(r) not in printed_numeros]

        print(f"After: chaima_rows_new={len(chaima_rows_new)}, yosr_rows_new={len(yosr_rows_new)}, chaimadone_rows={len(chaimadone_rows)}, yosrdone_rows={len(yosrdone_rows)}")

        # --- FIX: Use fixed fieldnames order for all CSVs ---
        fixed_fieldnames = [
            'NomClient','Numero','TypePersonnalisation','Commande',
            "NombreD'impression10CM","NombreD'impression15CM","NombreD'Impression25CM",
            'RefColor','Police','Remarque','Graphiste','Presseur','status','BunchOfPhotos'
        ]

        # Ensure all rows have all fields in the fixed order and remove any extra keys
        def fill_and_clean_fields(row):
            # Remove any extra keys
            keys_to_remove = [k for k in row if k not in fixed_fieldnames]
            for k in keys_to_remove:
                del row[k]
            # Fill missing fields
            for f in fixed_fieldnames:
                if f not in row:
                    row[f] = ''
            return row
        chaima_rows_new = [fill_and_clean_fields(r) for r in chaima_rows_new]
        yosr_rows_new = [fill_and_clean_fields(r) for r in yosr_rows_new]
        chaimadone_rows = [fill_and_clean_fields(r) for r in chaimadone_rows]
        yosrdone_rows = [fill_and_clean_fields(r) for r in yosrdone_rows]

        # Save all
        save_csv_to_github("chaima.csv", chaima_rows_new, fixed_fieldnames, "Remove printed entries")
        save_csv_to_github("yosr.csv", yosr_rows_new, fixed_fieldnames, "Remove printed entries")
        save_csv_to_github("chaimadone.csv", chaimadone_rows, fixed_fieldnames, "Add printed entries")
        save_csv_to_github("yosrdone.csv", yosrdone_rows, fixed_fieldnames, "Add printed entries")

    def run_filter_gmail(self):
        def task():
            process_and_update_rows_from_csvs()
        threading.Thread(target=task, daemon=True).start()

def get_output_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    output_dir = os.path.join(desktop, "output_data")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

# --- Google API imports ---
import pickle
from google.oauth2 import service_account
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# --- Google API credential files ---
SHEETS_SERVICE_ACCOUNT_FILE = 'service_account.json'
GMAIL_OAUTH_CLIENT_FILE = 'client_secret.json'
GMAIL_TOKEN_FILE = 'gmail_token.pickle'

# --- Google Sheets and Gmail scopes ---
SHEETS_SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# --- Google Sheets IDs ---
SHEET_IDS = [
    'YOUR_CHAIMA_SHEET_ID',
    'YOUR_YOSR_SHEET_ID',
]

# --- Utility: Get Sheets service ---
def get_sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        SHEETS_SERVICE_ACCOUNT_FILE, scopes=SHEETS_SCOPES)
    return build('sheets', 'v4', credentials=creds)

# --- Utility: Get Gmail service ---
def get_gmail_service():
    creds = None
    if os.path.exists(GMAIL_TOKEN_FILE):
        with open(GMAIL_TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                GMAIL_OAUTH_CLIENT_FILE, GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    return build('gmail', 'v1', credentials=creds)

# --- Utility: Find target column in a sheet (always second column) ---
def is_purple_color(cell_color, target=(0.7607843, 0.48235294, 0.627451), tol=0.03, cell=None):
    """
    Detects if a cell is considered 'purple' (or special) for the app logic.
    Now supports both:
    - Excel theme color 7 (as found in your sheet, usually green)
    - Direct RGB color FF00FFFF (cyan)
    - Also returns True if cell_color is exactly {'red': 1}
    - Also returns True if cell_color matches {'red': 0.20392157, 'green': 0.65882355, 'blue': 0.3254902} (special green)
    """
    # If cell object is provided, check for theme and RGB
    if cell is not None:
        fg = cell.fill.fgColor if cell.fill else None
        if fg is not None:
            if getattr(fg, 'type', None) == 'theme' and getattr(fg, 'theme', None) == 7:
                return True  # Theme color 7 (green in your sheet)
            if getattr(fg, 'type', None) == 'rgb' and getattr(fg, 'rgb', None) == 'FF00FFFF':
                return True  # RGB cyan
    # Fallback: original color detection by RGB float
    if not cell_color:
        return False
    # --- New: detect pure red ---
    if cell_color == {'red': 1}:
        return True
    # --- New: detect special green ---
    special_green = {'red': 0.20392157, 'green': 0.65882355, 'blue': 0.3254902}
    if all(abs(cell_color.get(k, 0) - v) < tol for k, v in special_green.items()):
        return True
    r = cell_color.get('red', 0)
    g = cell_color.get('green', 0)
    b = cell_color.get('blue', 0)
    return (
        abs(r - target[0]) < tol and
        abs(g - target[1]) < tol and
        abs(b - target[2]) < tol
    )

def find_target_column(sheet_id, service, sheet_index=0):
    # Get sheet metadata
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheet_name = meta['sheets'][sheet_index]['properties']['title']
    # Get cell data with formatting
    result = service.spreadsheets().get(
        spreadsheetId=sheet_id,
        ranges=[sheet_name],
        includeGridData=True
    ).execute()
    grid = result['sheets'][0]['data'][0]['rowData']
    header_row = grid[0]['values']
    name_col = 1    # Second column is the name
    phone_col = 6   # Column H (5 columns to the right of name_col, immediately left of description)
    header = header_row[phone_col].get('formattedValue', '') if len(header_row) > phone_col else 'Phone'
    numbers = []
    for row in grid[1:]:
        vals = row.get('values', [])
        if phone_col < len(vals) and name_col < len(vals):
            phone = vals[phone_col].get('formattedValue', '').strip()
            name_cell = vals[name_col]
            cell_color = None
            if 'effectiveFormat' in name_cell and 'backgroundColor' in name_cell['effectiveFormat']:
                cell_color = name_cell['effectiveFormat']['backgroundColor']
            if phone and is_purple_color(cell_color):
                numbers.append(phone)
    return header, numbers

# --- Utility: Search Gmail for a number and get the first email body ---
def search_gmail_for_number(service, number):
    query = f'{number}'
    results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
    messages = results.get('messages', [])
    print(f'[DEBUG] Gmail search for "{number}": {len(messages)} message(s) found.')
    if not messages:
        return ''
    msg_id = messages[0]['id']
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    # Print subject and snippet for debug
    headers = msg.get('payload', {}).get('headers', [])
    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(no subject)')
    snippet = msg.get('snippet', '')
    print(f'[DEBUG] Subject: {subject}')
    print(f'[DEBUG] Snippet: {snippet}')
    # Improved: Recursively search for the first text/plain or text/html part
    def get_body(payload):
        # Prefer HTML part if available
        if 'parts' in payload:
            html_part = None
            text_part = None
            for part in payload['parts']:
                if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                    html_part = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                elif part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                    text_part = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                # Recursively search in sub-parts
                result = get_body(part)
                if result:
                    if part.get('mimeType') == 'text/html':
                        html_part = result
                    elif part.get('mimeType') == 'text/plain':
                        text_part = result
            return html_part or text_part or ''
        else:
            if payload.get('mimeType') == 'text/html' and 'data' in payload.get('body', {}):
                return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
            if payload.get('mimeType') == 'text/plain' and 'data' in payload.get('body', {}):
                return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
        return ''
    body = get_body(msg['payload'])
    if not body:
        print('[DEBUG] No body extracted. Raw payload:', msg['payload'])
    return body

# --- Main workflow: Extract numbers, search Gmail, save to GitHub ---
def filter_and_save_to_github(status_label=None):
    try:
        if status_label:
            status_label.config(text='Connecting to Google Sheets...')
        print('[DEBUG] Connecting to Google Sheets...')
        sheets_service = get_sheets_service()
        all_results = []
        for sheet_id in SHEET_IDS:
            header, numbers = find_target_column(sheet_id, sheets_service)
            for number in numbers:
                all_results.append({'Phone': number})
        if status_label:
            status_label.config(text='Connecting to Gmail...')
        print('[DEBUG] Connecting to Gmail...')
        try:
            gmail_service = get_gmail_service()
        except Exception as gmail_exc:
            print(f'[DEBUG] Gmail connection error: {gmail_exc}')
            if status_label:
                status_label.config(text=f'Gmail connection error: {gmail_exc}', foreground='red')
            messagebox.showerror('Error', f'Gmail connection error: {gmail_exc}')
            return
        print('[DEBUG] Connected to Gmail!')
        for row in all_results:
            if status_label:
                status_label.config(text=f'Searching Gmail for {row["Phone"]}...')
            print(f'[DEBUG] Searching Gmail for {row["Phone"]}...')
            body = search_gmail_for_number(gmail_service, row['Phone'])
            row['EmailBody'] = body
        # Save to GitHub as CSV
        if status_label:
            status_label.config(text='Saving results to GitHub...')
        print('[DEBUG] Saving results to GitHub...')
        fieldnames = ['Phone', 'EmailBody']
        save_csv_to_github('filtered_emails.csv', all_results, fieldnames, 'Save filtered emails')
        if status_label:
            status_label.config(text='Done! Results saved to GitHub.', foreground='green')
        print('[DEBUG] Done! Results saved to GitHub.')
        messagebox.showinfo('Success', 'Filtered emails saved to GitHub as filtered_emails.csv')
        # --- Show alert that Gmail filter is done ---
        messagebox.showinfo('Gmail Filter', 'Le filtrage Gmail est terminé !')
    except Exception as e:
        print('[DEBUG] Error during filter:')
        traceback.print_exc()
        if status_label:
            status_label.config(text=f'Error: {e}', foreground='red')
        messagebox.showerror('Error', f'Error during filter: {e}')

# --- Utility: Extract numbers from both sheets and save to CSV (for testing) ---
def extract_numbers_from_sheets_to_csv():
    sheets_service = get_sheets_service()
    all_results = []
    for sheet_id in SHEET_IDS:
        header, numbers = find_target_column(sheet_id, sheets_service)
        for number in numbers:
            all_results.append({'Phone': number})
    # Save to local CSV
    import csv
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    out_path = os.path.join(desktop, "sheet_numbers.csv")
    with open(out_path, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Phone"])
        writer.writeheader()
        writer.writerows(all_results)
    print(f"Extracted phone numbers saved to {out_path}")

def download_gmail_attachments(msg, output_dir, gmail_service=None, msg_id=None):
    attachments = []
    def walk_parts(parts):
        for part in parts:
            if part.get('filename') and part['filename']:
                att_id = part['body'].get('attachmentId')
                if att_id and gmail_service and msg_id:
                    att = gmail_service.users().messages().attachments().get(userId='me', messageId=msg_id, id=att_id).execute()
                    file_data = base64.urlsafe_b64decode(att['data'])
                    file_path = os.path.join(output_dir, part['filename'])
                    with open(file_path, 'wb') as f:
                        f.write(file_data)
                    print(f"[DEBUG] Downloaded attachment: {file_path}")
                    attachments.append(file_path)
            if 'parts' in part:
                walk_parts(part['parts'])
    if 'parts' in msg['payload']:
        walk_parts(msg['payload']['parts'])
    return attachments

def extract_drive_links_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        if "drive.google.com" in a["href"]:
            links.append(a["href"])
    return links

def download_drive_links_from_body(body, output_dir):
    drive_links = re.findall(r'https://drive\\.google\\.com/[\w/?=.&%-]+', body)
    if "<html" in body.lower() or "<a " in body.lower():
        try:
            html_links = extract_drive_links_from_html(body)
            drive_links.extend([l for l in html_links if l not in drive_links])
        except Exception as e:
            pass  # Remove debug print
    downloaded = []
    for link in drive_links:
        try:
            file_id_match = re.search(r'/d/([\w-]+)', link)
            if not file_id_match:
                file_id_match = re.search(r'id=([\w-]+)', link)
            if file_id_match:
                file_id = file_id_match.group(1)
                url = f'https://drive.google.com/uc?export=download&id={file_id}'
                resp = requests.get(url)
                if resp.status_code == 200:
                    cd = resp.headers.get('content-disposition', '')
                    fname_match = re.search('filename="?([^";]+)"?', cd)
                    filename = fname_match.group(1) if fname_match else f'drivefile_{file_id}'
                    file_path = os.path.join(output_dir, filename)
                    with open(file_path, 'wb') as f:
                        f.write(resp.content)
                    downloaded.append(file_path)
                # Remove debug print for failed download
            # Remove debug print for file ID extraction
        except Exception as e:
            pass  # Remove debug print
    return downloaded

def extract_yosr_line_5431_phone_and_gmail_to_csv():
    sheets_service = get_sheets_service()
    sheet_id = SHEET_IDS[1]  # yosr sheet
    result = sheets_service.spreadsheets().get(
        spreadsheetId=sheet_id,
        ranges=[sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()['sheets'][0]['properties']['title']],
        includeGridData=True
    ).execute()
    grid = result['sheets'][0]['data'][0]['rowData']
    row_idx = 5430  # 0-based index (5431st row)
    phone_col = 8   # 9th column (0-based index)
    phone = ''
    if row_idx < len(grid):
        vals = grid[row_idx].get('values', [])
        phone = vals[phone_col].get('formattedValue', '') if len(vals) > phone_col else ''
    else:
        print("[DEBUG] Line 5431 - Row index out of range.")
        return
    # Now search Gmail for this phone number
    email_body = ''
    attachments = []
    drive_files = []
    if phone:
        try:
            gmail_service = get_gmail_service()
            query = f'{phone}'
            results = gmail_service.users().messages().list(userId='me', q=query, maxResults=1).execute()
            messages = results.get('messages', [])
            print(f'[DEBUG] Gmail search for "{phone}": {len(messages)} message(s) found.')
            if not messages:
                email_body = ''
            else:
                msg_id = messages[0]['id']
                msg = gmail_service.users().messages().get(userId='me', id=msg_id, format='full').execute()
                # Print subject and snippet for debug
                headers = msg.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(no subject)')
                snippet = msg.get('snippet', '')
                print(f'[DEBUG] Subject: {subject}')
                print(f'[DEBUG] Snippet: {snippet}')
                # Improved: Recursively search for the first text/plain or text/html part
                def get_body(payload):
                    # Prefer HTML part if available
                    if 'parts' in payload:
                        html_part = None
                        text_part = None
                        for part in payload['parts']:
                            if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                                html_part = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                            elif part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                                text_part = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                            # Recursively search in sub-parts
                            result = get_body(part)
                            if result:
                                if part.get('mimeType') == 'text/html':
                                    html_part = result
                                elif part.get('mimeType') == 'text/plain':
                                    text_part = result
                        return html_part or text_part or ''
                    else:
                        if payload.get('mimeType') == 'text/html' and 'data' in payload.get('body', {}):
                            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
                        if payload.get('mimeType') == 'text/plain' and 'data' in payload.get('body', {}):
                            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
                    return ''
                email_body = get_body(msg['payload'])
                if not email_body:
                    print('[DEBUG] No body extracted. Raw payload:', msg['payload'])
                # Download attachments and drive files in a temp dir
                import tempfile
                with tempfile.TemporaryDirectory() as output_dir:
                    attachments = download_gmail_attachments(msg, output_dir, gmail_service, msg_id)
                    drive_files = download_drive_links_from_body(email_body, output_dir)
                    # Upload all files to GitHub uploads/ and rename
                    uploaded_files = []
                    for local_path in attachments + drive_files:
                        ext = os.path.splitext(local_path)[1]
                        base_name = f"yosr_{phone}_{random_string()}" + ext
                        github_filename = normalize_filename(base_name)
                        with open(local_path, 'rb') as f:
                            content = f.read()
                        update_github_file_content(f'uploads/{github_filename}', content, f'Upload {github_filename}')
                        print(f"[DEBUG] Uploaded {github_filename} to GitHub uploads/")
                        uploaded_files.append(github_filename)
        except Exception as e:
            print(f"[DEBUG] Gmail search failed: {e}")
            email_body = f"[ERROR] {e}"
    # Save to CSV
    import csv
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    out_path = os.path.join(desktop, "phone_and_email_body.csv")
    with open(out_path, "w", newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Phone", "EmailBody", "Attachments", "DriveFiles"])
        writer.writerow([phone, email_body, "; ".join(attachments), "; ".join(drive_files)])
    print(f"Extracted phone, email body, and attachments info saved to {out_path}")

def random_string(length=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def normalize_filename(filename):
    import re
    # Replace all non-alphanumeric, dot, dash, or underscore with underscore
    return re.sub(r'[^A-Za-z0-9._-]', '_', filename)

def upload_file_to_github(local_path, github_filename):
    github_filename = normalize_filename(github_filename)
    with open(local_path, 'rb') as f:
        content = f.read()
    update_github_file_content(f'uploads/{github_filename}', content, f'Upload {github_filename}')
    return github_filename

def process_and_update_rows_from_csvs():
    sheets_service = get_sheets_service()
    gmail_service = get_gmail_service()
    github_csvs = [
        (SHEET_IDS[0], 'chaima.csv', 'Chaima'),
        (SHEET_IDS[1], 'yosr.csv', 'Yosr'),
    ]
    for sheet_id, csv_name, graphiste in github_csvs:
        print(f"[DEBUG] Processing CSV for {graphiste}...")
        # Load the sheet
        meta = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        sheet_name = meta['sheets'][0]['properties']['title']
        result = sheets_service.spreadsheets().get(
            spreadsheetId=sheet_id,
            ranges=[sheet_name],
            includeGridData=True
        ).execute()
        grid = result['sheets'][0]['data'][0]['rowData']
        # Load the current CSV from GitHub
        csv_rows = load_csv_from_github(csv_name)
        fieldnames = list(csv_rows[0].keys()) if csv_rows else [
            "NomClient", "Numero", "TypePersonnalisation", "Commande", "NombreD'impression10CM", "NombreD'impression15CM", "NombreD'Impression25CM", "RefColor", "Police", "Remarque", "Graphiste", "Presseur", "status", "BunchOfImagesNames"
        ]
        for row in csv_rows:
            phone = row.get('Numero', '').strip()
            status = str(row.get('status', '')).strip().lower()
            print(f"[DEBUG] Processing row: Numero={phone}, status={status}, NomClient={row.get('NomClient','')}")
            # Accept more variants for inserted status
            if status not in ('inserted', 'insert', 'toinsert') or not phone:
                print(f"[DEBUG] Skipping row (not inserted or missing phone): Numero={phone}")
                continue
            # Find the row in the sheet with this phone number
            found = False
            for sheet_row in reversed(grid[1:]):
                vals = sheet_row.get('values', [])
                # Determine phone column index
                if csv_name == 'chaima.csv':
                    phone_col = 4  # Use column 4 (0-based) for phone in chaima
                else:
                    phone_col = 8
                if phone_col >= len(vals):
                    continue
                sheet_phone = vals[phone_col].get('formattedValue', '').strip()
                if sheet_phone == phone:
                    # Print the full row for debugging (as a list of formatted values)
                    row_debug = [v.get('formattedValue', '') for v in vals]
                    print(f"[DEBUG] Found phone match in sheet row: {row_debug}")
                    name_col = 1
                    name_cell = vals[name_col] if name_col < len(vals) else None
                    cell_color = None
                    if name_cell and 'effectiveFormat' in name_cell and 'backgroundColor' in name_cell['effectiveFormat']:
                        cell_color = name_cell['effectiveFormat']['backgroundColor']
                    if is_purple_color(cell_color):
                        found = True
                        print(f"[DEBUG] Found phone {phone} in sheet and name cell is special (purple/green/blue/red).")
                    else:
                        print(f"[DEBUG] Found phone {phone} in sheet but name cell is NOT special.")
                    break  # Always stop after the first match, regardless of color
            if not found:
                print(f"[DEBUG] Phone {phone} not found in sheet with purple name cell.")
                continue
            # Search Gmail for this phone
            query = f'{phone}'
            results = gmail_service.users().messages().list(userId='me', q=query, maxResults=1).execute()
            messages = results.get('messages', [])
            if not messages:
                print(f"[DEBUG] No Gmail found for phone {phone}")
                continue
            msg_id = messages[0]['id']
            msg = gmail_service.users().messages().get(userId='me', id=msg_id, format='full').execute()
            # Extract email body
            def get_body(payload):
                # Prefer HTML part if available
                if 'parts' in payload:
                    html_part = None
                    text_part = None
                    for part in payload['parts']:
                        if part.get('mimeType') == 'text/html' and 'data' in part.get('body', {}):
                            html_part = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        elif part.get('mimeType') == 'text/plain' and 'data' in part.get('body', {}):
                            text_part = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        # Recursively search in sub-parts
                        result = get_body(part)
                        if result:
                            if part.get('mimeType') == 'text/html':
                                html_part = result
                            elif part.get('mimeType') == 'text/plain':
                                text_part = result
                    return html_part or text_part or ''
                else:
                    if payload.get('mimeType') == 'text/html' and 'data' in payload.get('body', {}):
                        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
                    if payload.get('mimeType') == 'text/plain' and 'data' in payload.get('body', {}):
                        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
                return ''
            email_body = get_body(msg['payload'])
            # Use a temporary directory for downloads
            import tempfile
            with tempfile.TemporaryDirectory() as output_dir:
                attachments = download_gmail_attachments(msg, output_dir, gmail_service, msg_id)
                drive_files = download_drive_links_from_body(email_body, output_dir)
                # Upload all files to GitHub uploads/ and rename
                uploaded_files = []
                for local_path in attachments + drive_files:
                    ext = os.path.splitext(local_path)[1]
                    base_name = f"{row.get('NomClient','').replace(' ', '').replace('(', '').replace(')', '')}_{phone}_{random_string()}" + ext
                    github_filename = normalize_filename(base_name)
                    with open(local_path, 'rb') as f:
                        content = f.read()
                    update_github_file_content(f'uploads/{github_filename}', content, f'Upload {github_filename}')
                    print(f"[DEBUG] Uploaded {github_filename} to GitHub uploads/")
                    uploaded_files.append(github_filename)
                # Update the row in place
                row['status'] = 'pending'
                print(f"[DEBUG] Updated status to pending for Numero={phone}")
                # Use the correct column for images
                if 'BunchOfImagesNames' in row:
                    row['BunchOfImagesNames'] = ','.join(uploaded_files)
                elif 'BunchOfPhotos' in row:
                    row['BunchOfPhotos'] = ','.join(uploaded_files)
                else:
                    row['BunchOfImagesNames'] = ','.join(uploaded_files)
                print(f"[DEBUG] Updated images for Numero={phone}: {uploaded_files}")
        # Save updated CSV to GitHub
        save_csv_to_github(csv_name, csv_rows, fieldnames, f'Update filtered rows for {graphiste}')
        print(f"[DEBUG] Updated {csv_name} on GitHub.")

if __name__ == "__main__":
    ensure_github_files_exist()
    try:
        remote_version = get_github_file_content("versionorderextractor.txt").strip()
    except Exception as e:
        remote_version = None
        print(f"Could not fetch version from GitHub: {e}")
    if not remote_version:
        remote_version = "1.0.4"  # fallback: allow run if file missing/empty
    if remote_version != "1.0.4":
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Mise à jour requise",
            f"Votre version du logiciel (1.0.3) n'est pas à jour.\nVeuillez télécharger la nouvelle version ({remote_version}) pour continuer."
        )
        webbrowser.open_new("YOUR_UPDATE_DOWNLOAD_URL")
        time.sleep(1)  # Give the browser time to launch
        root.destroy()
        exit()
    # --- DEBUG: Print chaima sheet row 3199 and color comparison ---
    try:
        sheets_service = get_sheets_service()
        chaima_sheet_id = SHEET_IDS[0]
        meta = sheets_service.spreadsheets().get(spreadsheetId=chaima_sheet_id).execute()
        sheet_name = meta['sheets'][0]['properties']['title']
        result = sheets_service.spreadsheets().get(
            spreadsheetId=chaima_sheet_id,
            ranges=[sheet_name],
            includeGridData=True
        ).execute()
        grid = result['sheets'][0]['data'][0]['rowData']
        row_idx = 3198  # 1-based to 0-based
        if row_idx < len(grid):
            vals = grid[row_idx].get('values', [])
            print(f"\n---------------------\n[CHAIMA SHEET] Row 3199 (index 3198):")
            for i, v in enumerate(vals):
                val = v.get('formattedValue', '')
                print(f"  Col {i+1}: {val}")
            # Try to compare color for the name cell (col 2, index 1)
            name_cell = vals[1] if len(vals) > 1 else None
            cell_color = None
            if name_cell and 'effectiveFormat' in name_cell and 'backgroundColor' in name_cell['effectiveFormat']:
                cell_color = name_cell['effectiveFormat']['backgroundColor']
            print(f"[DEBUG] Value being compared for color: {name_cell.get('formattedValue','') if name_cell else None}")
            print(f"[DEBUG] Cell color dict: {cell_color}")
            color_result = is_purple_color(cell_color)
            print(f"[DEBUG] Result of is_purple_color: {color_result}")
        else:
            print(f"[CHAIMA SHEET] Row 3199 does not exist (sheet has only {len(grid)} rows)")
    except Exception as e:
        print(f"[ERROR] Could not fetch or print chaima sheet row 3199: {e}")
    # --- END DEBUG ---
    root = tk.Tk()
    app = OrdersApp(root)
    root.mainloop()
