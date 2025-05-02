'''
GridVPN Desktop Client - Extended GUI with Auto-Disconnect and Multiple URIs
Python 3.13.3 поддерживается.
'''
# Структура проекта
# C:\PROJECTS\GIT_HUB\GRID_VPN/
# ├── venv/                   # виртуальное окружение
# ├── gridvpn_core.exe        # Xray Core (VPN-движок)
# ├── config.json             # генерируется автоматически
# ├── paths.json              # хранит список сохранённых URI
# ├── main.py                 # GUI-скрипт с сохранением ссылок, статусом и автоотключением
# ├── requirements.txt        # зависимости
# └── README.md               # документация проекта

import os
import sys
import subprocess
import json
import winreg
import ctypes
import atexit
from urllib.parse import urlparse, parse_qs, unquote
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

# Константы файлов и глобальная переменная для процесса Xray
PATHS_FILE = 'paths.json'
CONFIG_FILE = 'config.json'
XCORE = 'gridvpn_core.exe'
GLOBAL_XR = None

# Функции управления системным SOCKS5-прокси через реестр

def enable_system_socks(proxy='127.0.0.1:10801'):
    key_path = r'Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, 'ProxyServer', 0, winreg.REG_SZ, f'socks={proxy}')
    InternetSetOption = ctypes.windll.Wininet.InternetSetOptionW
    InternetSetOption(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
    InternetSetOption(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH

def disable_system_proxy():
    key_path = r'Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 0)
    InternetSetOption = ctypes.windll.Wininet.InternetSetOptionW
    InternetSetOption(0, 39, 0, 0)
    InternetSetOption(0, 37, 0, 0)

# Автоочистка при завершении скрипта: отключение прокси и процесса Xray

def cleanup():
    global GLOBAL_XR
    if GLOBAL_XR:
        GLOBAL_XR.stop()
    else:
        disable_system_proxy()

atexit.register(cleanup)

# Загрузка и сохранение списка URI

def load_paths():
    if os.path.isfile(PATHS_FILE):
        try:
            with open(PATHS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            save_paths([])   # перезапишем файл пустым списком
            return []
    return []

def save_paths(paths):
    with open(PATHS_FILE, 'w', encoding='utf-8') as f:
        json.dump(paths, f, indent=2, ensure_ascii=False)

# Парсинг VLESS/VMess/Trojan URI в JSON-конфиг Xray

def parse_vless(uri: str) -> dict:
    p = urlparse(uri)
    proto = p.scheme
    if proto not in ('vless', 'vmess', 'trojan'):
        raise ValueError(f'Unsupported protocol: {proto}')
    uid, host, port = p.username, p.hostname, p.port
    params = parse_qs(p.query)
    network = params.get('type', ['tcp'])[0]
    security = params.get('security', ['none'])[0]
    flow = params.get('flow', [''])[0]
    pbk = params.get('pbk', [''])[0]
    fp = params.get('fp', [''])[0]
    sni = params.get('sni', [''])[0]
    sid = params.get('sid', [''])[0]
    spx = unquote(params.get('spx', [''])[0])
    return {
        'log': {'loglevel': 'warning'},
        'inbounds': [{
            'listen': '127.0.0.1',
            'port': 10801,
            'protocol': 'socks',
            'settings': {'auth': 'noauth', 'udp': True},
            'tag': 'socks'
        }],
        'outbounds': [
            {
                'protocol': proto,
                'tag': 'proxy',
                'settings': {
                    'vnext': [{
                        'address': host,
                        'port': port,
                        'users': [{'id': uid, 'flow': flow or None, 'encryption': 'none'}]
                    }]
                },
                'streamSettings': {
                    'network': network,
                    'security': security,
                    **({'realitySettings': {
                        'publicKey': pbk,
                        'fingerprint': fp,
                        'serverName': sni,
                        'shortId': sid,
                        'spiderX': spx
                    }} if security == 'reality' else {})
                }
            },
            {'protocol': 'freedom', 'tag': 'direct', 'settings': {}}
        ]
    }

# Класс для управления процессом Xray Core

class XrayProcess:
    def __init__(self):
        self.proc = None

    def start(self):
        global GLOBAL_XR
        # Определяем путь к бинарю в упаковке или в dev
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = os.getcwd()
        exe_path = os.path.join(base, XCORE)
        if not os.path.isfile(exe_path):
            raise FileNotFoundError(f'{XCORE} not found at {exe_path}')
        # Абсолютный путь до конфига
        config_path = os.path.join(os.getcwd(), CONFIG_FILE)
        self.proc = subprocess.Popen([exe_path, '-config', config_path], cwd=os.getcwd())
        GLOBAL_XR = self
        enable_system_socks()

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait()
            self.proc = None
        disable_system_proxy()

# GUI-приложение на tkinter

class VPNGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('GridVPN Client')
        self.geometry('600x300')
        self.xr = XrayProcess()

        tk.Button(self, text='Add URI', command=self.add_uri).pack(pady=5)
        self.listbox = tk.Listbox(self)
        self.listbox.pack(fill='x', padx=10)

        frm = tk.Frame(self)
        tk.Button(frm, text='Connect', command=self.connect).pack(side='left', padx=5)
        tk.Button(frm, text='Disconnect', command=self.disconnect).pack(side='left', padx=5)
        frm.pack(pady=10)

        self.status = tk.Label(self, text='Status: Disconnected', fg='red')
        self.status.pack()

        # Загружаем сохраненные URI
        for uri in load_paths():
            self.listbox.insert('end', uri)

        self.protocol('WM_DELETE_WINDOW', self.on_close)

    def add_uri(self):
        uri = simpledialog.askstring('Add URI', 'Paste VLESS/VMess/Trojan URI:')
        if uri:
            self.listbox.insert('end', uri)
            save_paths(list(self.listbox.get(0, 'end')))

    def connect(self):
        sel = self.listbox.curselection()
        if not sel:
            return messagebox.showwarning('Warning', 'Select a URI first')
        uri = self.listbox.get(sel[0])
        try:
            cfg = parse_vless(uri)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)
            self.xr.start()
            self.status.config(text='Status: Connected', fg='green')
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def disconnect(self):
        self.xr.stop()
        self.status.config(text='Status: Disconnected', fg='red')

    def on_close(self):
        self.xr.stop()
        self.destroy()

if __name__ == '__main__':
    app = VPNGUI()
    app.mainloop()

# requirements.txt
# tkinter
# pywin32
