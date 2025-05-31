'''GridVPN Desktop Client
   + Add/Delete URI
   + Clipboard Paste Support
   + Run on Startup & Auto-Connect
   + Fixed paths to JSON near EXE
   + Looks for gridvpn_core.exe either beside the EXE or in the "_internal" subfolder'''
# Python 3.13.3

__version__ = "1.1.0"

import os
import sys
import subprocess
import json
import winreg
import ctypes
import atexit
from urllib.parse import urlparse, parse_qs, unquote
import tkinter as tk
from tkinter import messagebox, simpledialog

# ------------------------------------------------------------
# Определяем папку, где лежит EXE (или сам скрипт, если запуск не из “frozen”):
if getattr(sys, 'frozen', False):
    # Когда упаковано PyInstaller, sys.executable указывает на GridVpn.exe
    BASEDIR = os.path.dirname(sys.executable)
else:
    # При запуске “python main.py” — __file__ даст путь к этому файлу
    BASEDIR = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------
# Путь до JSON-файлов (они будут сохраняться рядом с EXE)
PATHS_FILE    = os.path.join(BASEDIR, 'paths.json')
SETTINGS_FILE = os.path.join(BASEDIR, 'settings.json')
CONFIG_FILE   = os.path.join(BASEDIR, 'config.json')

# Ключ и имя в реестре для автозапуска
RUN_KEY  = r'Software\Microsoft\Windows\CurrentVersion\Run'
APP_NAME = 'GridVPNClient'

GLOBAL_XR = None

# ------------------------------------------------------------
# Функция для поиска gridvpn_core.exe либо рядом с EXE, либо в папке "_internal"
def find_xray_core() -> str:
    """
    Ищет gridvpn_core.exe в BASEDIR; если не находит — проверяет BASEDIR/_internal.
    """
    path1 = os.path.join(BASEDIR, 'gridvpn_core.exe')
    if os.path.isfile(path1):
        return path1

    path2 = os.path.join(BASEDIR, '_internal', 'gridvpn_core.exe')
    if os.path.isfile(path2):
        return path2

    raise FileNotFoundError(f'gridvpn_core.exe not found in:\n  {path1}\n  {path2}')

# ------------------------------------------------------------
# Чтение/запись флага автозапуска в settings.json
def load_settings():
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    # Если файл не существует или сломан, создаём новый со значением по умолчанию
    default = {'auto_start': False}
    save_settings(default)
    return default

def save_settings(settings: dict):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
    except PermissionError:
        messagebox.showerror('Error', f'Cannot write settings.json in {BASEDIR}\nCheck permissions.')

# ------------------------------------------------------------
# Регистрация/снятие автозапуска в реестре
def register_autostart():
    try:
        # Путь до exe: sys.executable (если “frozen”), иначе путь до скрипта
        exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        winreg.CloseKey(key)
    except Exception as e:
        messagebox.showerror('Error', f'Cannot register autostart:\n{e}')

def unregister_autostart():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass
    except Exception as e:
        messagebox.showerror('Error', f'Cannot unregister autostart:\n{e}')

# ------------------------------------------------------------
# Управление системным SOCKS5-прокси через реестр
def enable_system_socks(proxy='127.0.0.1:10801'):
    key_path = r'Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, 'ProxyServer', 0, winreg.REG_SZ, f'socks={proxy}')
        InternetSetOption = ctypes.windll.Wininet.InternetSetOptionW
        InternetSetOption(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
        InternetSetOption(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH
    except Exception as e:
        messagebox.showerror('Error', f'Cannot enable system proxy:\n{e}')

def disable_system_proxy():
    key_path = r'Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 0)
        InternetSetOption = ctypes.windll.Wininet.InternetSetOptionW
        InternetSetOption(0, 39, 0, 0)
        InternetSetOption(0, 37, 0, 0)
    except Exception:
        # Если proxy уже выключен, игнорируем возможную ошибку
        pass

# ------------------------------------------------------------
# Автоочистка при выходе: останавливаем Xray или proxy
def cleanup():
    global GLOBAL_XR
    if GLOBAL_XR:
        GLOBAL_XR.stop()
    else:
        disable_system_proxy()

atexit.register(cleanup)

# ------------------------------------------------------------
# Загрузка/сохранение списка URI (paths.json)
def load_paths():
    if os.path.isfile(PATHS_FILE):
        try:
            with open(PATHS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            save_paths([])  # перезапишем пустым списком
            return []
    # Если файл не существует, создаём новый
    save_paths([])
    return []

def save_paths(paths):
    try:
        with open(PATHS_FILE, 'w', encoding='utf-8') as f:
            json.dump(paths, f, indent=2, ensure_ascii=False)
    except PermissionError:
        messagebox.showerror('Error', f'Cannot write paths.json in {BASEDIR}\nCheck permissions.')

# ------------------------------------------------------------
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
    pbk  = params.get('pbk', [''])[0]
    fp   = params.get('fp', [''])[0]
    sni  = params.get('sni', [''])[0]
    sid  = params.get('sid', [''])[0]
    spx  = unquote(params.get('spx', [''])[0])

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

# ------------------------------------------------------------
# Класс для управления процессом Xray Core (gridvpn_core.exe)
class XrayProcess:
    def __init__(self):
        self.proc = None

    def start(self):
        global GLOBAL_XR
        # Найдём фактический путь до gridvpn_core.exe
        xray_exe = find_xray_core()
        # Конфигурационный файл config.json должен быть уже записан
        config_path = CONFIG_FILE
        self.proc = subprocess.Popen([xray_exe, '-config', config_path], cwd=BASEDIR)
        GLOBAL_XR = self
        enable_system_socks()

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait()
            self.proc = None
        disable_system_proxy()

# ------------------------------------------------------------
# Главное GUI-приложение на tkinter
class VPNGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('GridVPN Client')
        self.geometry('600x360')
        self.xr = XrayProcess()

        # Загружаем настройки автозапуска
        self.settings = load_settings()
        auto_start = self.settings.get('auto_start', False)

        # Фрейм: кнопки Add/Delete URI
        btns = tk.Frame(self)
        tk.Button(btns, text='Add URI', command=self.add_uri).pack(side='left', padx=5)
        tk.Button(btns, text='Delete URI', command=self.delete_uri).pack(side='left', padx=5)
        btns.pack(pady=5)

        # Список сохранённых URI
        self.listbox = tk.Listbox(self)
        self.listbox.pack(fill='x', padx=10)
        self.listbox.bind('<Delete>', lambda e: self.delete_uri())

        # Флажок «Run on Startup & Auto-Connect»
        self.var_autostart = tk.BooleanVar(value=auto_start)
        cb = tk.Checkbutton(self,
                            text='Run on Startup & Auto-Connect',
                            variable=self.var_autostart,
                            command=self.toggle_autostart)
        cb.pack(pady=5)

        # Кнопки Connect / Disconnect
        cfrm = tk.Frame(self)
        tk.Button(cfrm, text='Connect', command=self.connect).pack(side='left', padx=5)
        tk.Button(cfrm, text='Disconnect', command=self.disconnect).pack(side='left', padx=5)
        cfrm.pack(pady=10)

        # Статус
        self.status = tk.Label(self, text='Status: Disconnected', fg='red')
        self.status.pack()

        # Загружаем URI из paths.json
        for uri in load_paths():
            self.listbox.insert('end', uri)

        # Если автозапуск включён и есть URI — сразу подключаемся к последнему
        if auto_start and self.listbox.size() > 0:
            self.listbox.selection_set(self.listbox.size() - 1)  # выбираем последний элемент
            self.connect()

        # Обработчик закрытия окна
        self.protocol('WM_DELETE_WINDOW', self.on_close)

    def toggle_autostart(self):
        """Вызывается при изменении флажка автозапуска."""
        enabled = self.var_autostart.get()
        self.settings['auto_start'] = enabled
        save_settings(self.settings)
        if enabled:
            register_autostart()
        else:
            unregister_autostart()

    def add_uri(self):
        # Сразу подставляем буфер обмена (независимо от раскладки)
        try:
            default = self.clipboard_get()
        except tk.TclError:
            default = ''
        uri = simpledialog.askstring('Add URI', 'Paste VLESS/VMess/Trojan URI:', initialvalue=default)
        if uri:
            self.listbox.insert('end', uri)
            save_paths(list(self.listbox.get(0, 'end')))

    def delete_uri(self):
        sel = self.listbox.curselection()
        if not sel:
            return messagebox.showwarning('Warning', 'Select a URI to delete')
        idx = sel[0]
        uri = self.listbox.get(idx)
        if messagebox.askyesno('Confirm Delete', f'Delete URI:\n{uri}?'):
            self.listbox.delete(idx)
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

# ------------------------------------------------------------
if __name__ == '__main__':
    VPNGUI().mainloop()
