"""Native Windows notification-area messages; no browser permission or cloud service."""
import ctypes
import os
import queue
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path


class DesktopNotifier:
    def __init__(self, url='http://127.0.0.1:8765'):
        self.url = url
        self.available = False
        self.last_visible_at = None
        self.ready = threading.Event()
        self.requests = queue.Queue()
        self.hwnd = None
        self.thread = None
        if os.name == 'nt':
            self.thread = threading.Thread(target=self._run,daemon=True,name='StudyPet notification icon')
            self.thread.start()
            self.ready.wait(5)

    def send(self, title, body):
        if not self.available or not self.hwnd:
            return False
        done, result = threading.Event(), {}
        self.requests.put((title,body,done,result))
        self._post(self.hwnd,0x8002,0,0)
        return done.wait(5) and bool(result.get('ok'))

    def close(self):
        if self.hwnd:
            self._post(self.hwnd,0x0010,0,0)
        if self.thread:
            self.thread.join(timeout=3)

    def _run(self):
        from ctypes import wintypes as w
        user = ctypes.WinDLL('user32',use_last_error=True)
        shell = ctypes.WinDLL('shell32',use_last_error=True)
        kernel = ctypes.WinDLL('kernel32',use_last_error=True)
        proc_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t,w.HWND,w.UINT,w.WPARAM,w.LPARAM)
        class WNDCLASS(ctypes.Structure):
            _fields_=[('style',w.UINT),('proc',proc_type),('class_extra',ctypes.c_int),('window_extra',ctypes.c_int),
                      ('instance',w.HINSTANCE),('icon',w.HICON),('cursor',w.HANDLE),('background',w.HBRUSH),
                      ('menu',w.LPCWSTR),('name',w.LPCWSTR)]
        class NOTIFY(ctypes.Structure):
            _fields_=[('size',w.DWORD),('window',w.HWND),('id',w.UINT),('flags',w.UINT),('callback',w.UINT),
                      ('icon',w.HICON),('tip',w.WCHAR*128),('state',w.DWORD),('state_mask',w.DWORD),
                      ('info',w.WCHAR*256),('version',w.UINT),('title',w.WCHAR*64),('info_flags',w.DWORD),
                      ('guid',ctypes.c_byte*16),('balloon_icon',w.HICON)]
        kernel.GetModuleHandleW.argtypes=[w.LPCWSTR]; kernel.GetModuleHandleW.restype=w.HMODULE
        user.DefWindowProcW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]; user.DefWindowProcW.restype=ctypes.c_ssize_t
        user.RegisterClassW.argtypes=[ctypes.POINTER(WNDCLASS)]; user.RegisterClassW.restype=w.WORD
        user.CreateWindowExW.argtypes=[w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.HWND,w.HMENU,w.HINSTANCE,ctypes.c_void_p]
        user.CreateWindowExW.restype=w.HWND
        user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]; user.PostMessageW.restype=w.BOOL
        user.DestroyWindow.argtypes=[w.HWND]
        user.LoadIconW.argtypes=[w.HINSTANCE,ctypes.c_void_p]; user.LoadIconW.restype=w.HICON
        user.LoadImageW.argtypes=[w.HINSTANCE,w.LPCWSTR,w.UINT,ctypes.c_int,ctypes.c_int,w.UINT]; user.LoadImageW.restype=w.HANDLE
        user.GetMessageW.argtypes=[ctypes.POINTER(w.MSG),w.HWND,w.UINT,w.UINT]; user.GetMessageW.restype=w.BOOL
        user.TranslateMessage.argtypes=[ctypes.POINTER(w.MSG)]
        user.DispatchMessageW.argtypes=[ctypes.POINTER(w.MSG)]; user.DispatchMessageW.restype=ctypes.c_ssize_t
        shell.Shell_NotifyIconW.argtypes=[w.DWORD,ctypes.POINTER(NOTIFY)]; shell.Shell_NotifyIconW.restype=w.BOOL
        self._post = user.PostMessageW
        icon_data = NOTIFY()
        icon_data.size = ctypes.sizeof(NOTIFY)
        icon_data.id = 1
        icon_data.callback = 0x8001
        icon_data.tip = 'StudyPet 学习提醒 · 点击打开计划'
        custom_icon = Path(__file__).with_name('web_static') / 'pet.ico'
        icon = user.LoadImageW(None,str(custom_icon),1,32,32,0x10) if custom_icon.exists() else None
        icon_data.icon = icon or user.LoadIconW(None,ctypes.c_void_p(32516))
        def fit(value, limit):
            return str(value).encode('utf-16-le')[:limit*2].decode('utf-16-le',errors='ignore')
        @proc_type
        def procedure(hwnd,message,wp,lp):
            if message == 0x8002:
                try:
                    title,body,done,result = self.requests.get_nowait()
                except queue.Empty:
                    return 0
                try:
                    icon_data.flags = 0x10
                    icon_data.info = fit(body,255)
                    icon_data.title = fit(title,63)
                    icon_data.info_flags = 0x11  # Informational, silent.
                    result['ok'] = bool(shell.Shell_NotifyIconW(1,ctypes.byref(icon_data)))
                finally:
                    done.set()
                return 0
            if message == 0x8001:
                event = lp & 0xffff
                if event == 0x402:
                    self.last_visible_at = datetime.now(timezone.utc).isoformat()
                if event in (0x202,0x400,0x401,0x405):
                    threading.Thread(target=webbrowser.open,args=(self.url,),daemon=True).start()
                return 0
            if message == 0x0010:
                user.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:
                shell.Shell_NotifyIconW(2,ctypes.byref(icon_data))
                user.PostQuitMessage(0)
                return 0
            return user.DefWindowProcW(hwnd,message,wp,lp)
        name = f'StudyPetNotificationWindow{os.getpid()}'
        instance = kernel.GetModuleHandleW(None)
        window_class = WNDCLASS(proc=procedure,instance=instance,name=name)
        try:
            if not user.RegisterClassW(ctypes.byref(window_class)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.hwnd = user.CreateWindowExW(0,name,'StudyPet',0,0,0,0,0,None,None,instance,None)
            if not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            icon_data.window = self.hwnd
            icon_data.flags = 1|2|4
            self.available = bool(shell.Shell_NotifyIconW(0,ctypes.byref(icon_data)))
            icon_data.version = 4
            shell.Shell_NotifyIconW(4,ctypes.byref(icon_data))
            self.ready.set()
            message = w.MSG()
            while user.GetMessageW(ctypes.byref(message),None,0,0) > 0:
                user.TranslateMessage(ctypes.byref(message))
                user.DispatchMessageW(ctypes.byref(message))
        finally:
            self.available = False
            self.ready.set()
            self.hwnd = None
