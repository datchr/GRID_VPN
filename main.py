'''
GridVPN Desktop Client - Simple GUI for Single VLESS Link
Теперь с автоматическим включением/выключением системного SOCKS-прокси
Python 3.13.3 полностью поддерживается.
'''
# Структура проекта
# C:\PROJECTS\GIT_HUB\GRID_VPN/
# ├── venv/                   # виртуальное окружение
# ├── gridvpn_core.exe        # Xray Core (VPN-движок)
# ├── config.json             # генерируется автоматически
# ├── main.py                 # GUI-скрипт с автопрокси
# ├── requirements.txt        # зависимости
# └── README.md               # документация

# main.py
import os
import sys
import subprocess
import json
import winreg
import ctypes
from urllib.parse import urlparse, parse_qs, unquote
import tkinter as tk
from tkinter import messagebox

# Функции для включения/выключения системного SOCKS5-прокси
def enable_system_socks(proxy='127.0.0.1:10801'):
    reg_path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, 'ProxyServer', 0, winreg.REG_SZ, f'socks={proxy}')
    InternetSetOption = ctypes.windll.Wininet.InternetSetOptionW
    InternetSetOption(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
    InternetSetOption(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH

def disable_system_proxy():
    reg_path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 0)
    InternetSetOption = ctypes.windll.Wininet.InternetSetOptionW
    InternetSetOption(0, 39, 0, 0)
    InternetSetOption(0, 37, 0, 0)

# Парсер VLESS/VMess/Trojan URI в JSON-конфиг Xray
def parse_vless(uri: str) -> dict:
    parsed = urlparse(uri)
    proto = parsed.scheme
    if proto not in ('vless', 'vmess', 'trojan'):
        raise ValueError(f'Неподдерживаемый протокол: {proto}')
    user_id = parsed.username
    host = parsed.hostname
    port = parsed.port
    params = parse_qs(parsed.query)
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
        'outbounds': [{
            'protocol': proto,
            'tag': 'proxy',
            'settings': {
                'vnext': [{
                    'address': host,
                    'port': port,
                    'users': [{'id': user_id, 'flow': flow or None, 'encryption': 'none'}]
                }]
            },
            'streamSettings': {
                'network': network,
                'security': security,
                **({'realitySettings': {'publicKey': pbk, 'fingerprint': fp, 'serverName': sni,
                                          'shortId': sid, 'spiderX': spx}} if security == 'reality' else {})
            }
        }, {'protocol': 'freedom', 'tag': 'direct', 'settings': {}}]
    }

# Сохранение конфига
def save_config(cfg: dict):
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

# Запуск Xray Core и активация системного прокси
def run_xray():
    exe = os.path.join(os.getcwd(), 'gridvpn_core.exe')
    if not os.path.isfile(exe):
        messagebox.showerror('Ошибка', 'gridvpn_core.exe не найден!')
        return
    try:
        subprocess.Popen([exe, '-config', 'config.json'], cwd=os.getcwd())
        enable_system_socks('127.0.0.1:10801')
        messagebox.showinfo('Success', 'VPN запущен. Системный SOCKS5 прокси активирован.')
    except Exception as e:
        messagebox.showerror('Ошибка', str(e))

# GUI
def on_closing(root):
    disable_system_proxy()
    root.destroy()

class VPNGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('GridVPN Client')
        self.geometry('500x150')
        self.protocol('WM_DELETE_WINDOW', lambda: on_closing(self))
        tk.Label(self, text='Вставьте VLESS/VMess/Trojan URI:').pack(pady=10)
        self.uri_var = tk.StringVar()
        tk.Entry(self, textvariable=self.uri_var, width=60).pack(padx=10)
        tk.Button(self, text='Connect', command=self.connect).pack(pady=20)

    def connect(self):
        uri = self.uri_var.get().strip()
        try:
            cfg = parse_vless(uri)
            save_config(cfg)
            run_xray()
        except Exception as e:
            messagebox.showerror('Ошибка', str(e))

if __name__ == '__main__':
    app = VPNGUI()
    app.mainloop()

# requirements.txt
# ----------------
# tkinter       # встроен в Python, но при необходимости: pip install tk
# pywin32       # для удобной работы с WinAPI (необязательно, но можно)
# 
# README.md
# ---------
# После запуска main.py и ввода URI, Xray Core стартует и устанавливает системный SOCKS5 прокси.
# При закрытии окна прокси отключается автоматически.
