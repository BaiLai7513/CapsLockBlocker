"""
游戏 Capslock 锁定映射工具
===========================
解决游戏时误触 CapsLock 导致操作失误的痛点。
锁定后 CapsLock 被拦截，可映射为任意单键；解锁或锁屏时恢复 CapsLock 原生功能。

v1.2.6 更新:
- 窗口加宽到 540；最大高度 760；隐藏右侧滚动条，常规屏幕一屏显示全部设置。
- 映射方式两个选项完整显示，不再被遮挡。
- 锁定按钮仍固定在顶部，极端小屏保留滚轮兜底。

v1.2.5 更新:
- 锁定/解锁按钮固定在窗口顶部，详情区可滚动；窗口高度自适应屏幕，修复小屏/高缩放下按钮被遮挡。

v1.2.4 更新:
- 映射状态机重写：默认“切换锁定”（按一下保持目标键，再按一下释放），可选“按住触发”。
- 钩子过滤 LLKHF_INJECTED、忽略 CapsLock 自动重复，并在锁定/解锁/锁屏/退出时成对释放目标键。
- 保留先锁定再启用映射的两段式流程。

v1.2.3 更新:
- 锁定与映射解耦：先锁定 CapsLock，锁定后才能勾选映射。
- 锁屏/关闭程序视为恢复默认的出口：锁屏会解除映射并解除锁定，解锁后保持 CapsLock 原生。
- 增加运行权限显示，源码启动器自动请求管理员权限。

v1.2.1 更新:
- 发布方式改为文件夹（onedir），不再解压到临时目录，避免安全软件拦截导致无法启动。

v1.2 更新:
- 映射目标扩展到任意单键（F1-F24、方向键、小键盘、Ctrl/Shift/Alt 等）
- 注入方式改为 SendInput + 扫描码，提高游戏兼容性
- 锁屏检测改为独立消息窗口线程，避免 Tk 窗口过程被替换导致的崩溃
- 锁屏自动释放（v1.2.3 起锁屏后保持原生 CapsLock）
- 修复钩子回调异常、退出时目标键卡住、单实例检测等问题

作者: CodeWhale
"""

import ctypes
from ctypes import wintypes, WINFUNCTYPE, POINTER, byref, cast
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import traceback


APP_NAME = "游戏 Capslock 锁定映射工具"
APP_VERSION = "1.2.6"

WH_KEYBOARD_LL = 13
VK_CAPITAL = 0x14
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_PACKET = 0xE7
VK_PROCESSKEY = 0xE5

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_WTSSESSION_CHANGE = 0x02B1

WTS_SESSION_LOGON = 0x5
WTS_SESSION_LOGOFF = 0x6
WTS_SESSION_LOCK = 0x7
WTS_SESSION_UNLOCK = 0x8
NOTIFY_FOR_THIS_SESSION = 0

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_KEYBOARD = 1
MAPVK_VK_TO_VSC = 0
MAPVK_VK_TO_VSC_EX = 4

DESKTOP_SWITCHDESKTOP = 0x0100
ERROR_ALREADY_EXISTS = 183
ERROR_CLASS_ALREADY_EXISTS = 1410

# 用于标记“程序自己注入的 CapsLock 复位事件”，避免被钩子再次拦截。
MAGIC_EXTRA = 0x434C4231

_KEYDOWN_EVENTS = {WM_KEYDOWN, WM_SYSKEYDOWN}
_KEYUP_EVENTS = {WM_KEYUP, WM_SYSKEYUP}
_ALL_KEY_EVENTS = _KEYDOWN_EVENTS | _KEYUP_EVENTS
LLKHF_INJECTED = 0x00000010

MAPPING_MODE_TOGGLE = "toggle"
MAPPING_MODE_HOLD = "hold"
_MAPPING_MODES = (MAPPING_MODE_TOGGLE, MAPPING_MODE_HOLD)

_EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,  # PgUp/PgDn/End/Home/方向键
    0x2C, 0x2D, 0x2E,                                  # PrintScreen/Insert/Delete
    0x5B, 0x5C, 0x5D,                                  # Win/Menu
    0x6F, 0x90,                                        # 小键盘 /、NumLock
    0xA3, 0xA5,                                        # 右 Ctrl / 右 Alt
    0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3,          # 媒体键
}

_BLOCKED_TARGET_VKS = {
    VK_CAPITAL, VK_LWIN, VK_RWIN, VK_PACKET, VK_PROCESSKEY,
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06,                  # 鼠标键
}

_FALLBACK_VK_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter",
    0x13: "Pause", 0x1B: "Esc", 0x20: "Space",
    0x21: "PgUp", 0x22: "PgDn", 0x23: "End", 0x24: "Home",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x2C: "PrintScreen", 0x2D: "Insert", 0x2E: "Delete",
    0x5B: "LWin", 0x5C: "RWin", 0x5D: "Menu",
    0x6A: "Num *", 0x6B: "Num +", 0x6D: "Num -", 0x6E: "Num .", 0x6F: "Num /",
    0x90: "NumLock", 0x91: "ScrollLock",
    0xA0: "LShift", 0xA1: "RShift", 0xA2: "LCtrl", 0xA3: "RCtrl",
    0xA4: "LAlt", 0xA5: "RAlt",
    0xAD: "Mute", 0xAE: "Vol-", 0xAF: "Vol+",
    0xB0: "NextTrack", 0xB1: "PrevTrack", 0xB2: "Stop", 0xB3: "Play",
}
for _i in range(1, 25):
    _FALLBACK_VK_NAMES[0x6F + _i] = f"F{_i}"
for _i in range(10):
    _FALLBACK_VK_NAMES[0x60 + _i] = f"Num {_i}"
del _i

_CFG_DIR = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    "CapsLockBlocker",
)
CONFIG_PATH = os.path.join(_CFG_DIR, "config.json")

_DEFAULT_CFG = {
    "target_vk": 0x1B,
    "target_name": "Esc",
    "target_extended": False,
    "mapping_mode": MAPPING_MODE_TOGGLE,
}


if not hasattr(wintypes, "ULONG_PTR"):
    wintypes.ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
if not hasattr(wintypes, "LONG_PTR"):
    wintypes.LONG_PTR = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUTUNION),
    ]


HOOKPROC = WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC = WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
wts = ctypes.WinDLL("wtsapi32", use_last_error=True)

u32.SetWindowsHookExW.restype = wintypes.HHOOK
u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
u32.CallNextHookEx.restype = ctypes.c_ssize_t
u32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
u32.UnhookWindowsHookEx.restype = wintypes.BOOL
u32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
u32.GetKeyState.restype = wintypes.SHORT
u32.GetKeyState.argtypes = [ctypes.c_int]
u32.MapVirtualKeyW.restype = wintypes.UINT
u32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
u32.GetKeyNameTextW.restype = ctypes.c_int
u32.GetKeyNameTextW.argtypes = [ctypes.c_long, wintypes.LPWSTR, ctypes.c_int]
u32.SendInput.restype = wintypes.UINT
u32.SendInput.argtypes = [wintypes.UINT, POINTER(INPUT), ctypes.c_int]

u32.RegisterClassW.restype = wintypes.ATOM
u32.RegisterClassW.argtypes = [POINTER(WNDCLASSW)]
u32.CreateWindowExW.restype = wintypes.HWND
u32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HANDLE, wintypes.HINSTANCE, ctypes.c_void_p,
]
u32.DefWindowProcW.restype = ctypes.c_ssize_t
u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u32.DestroyWindow.restype = wintypes.BOOL
u32.DestroyWindow.argtypes = [wintypes.HWND]
u32.PostQuitMessage.restype = None
u32.PostQuitMessage.argtypes = [ctypes.c_int]
u32.GetMessageW.restype = ctypes.c_int
u32.GetMessageW.argtypes = [POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
u32.TranslateMessage.restype = wintypes.BOOL
u32.TranslateMessage.argtypes = [POINTER(wintypes.MSG)]
u32.DispatchMessageW.restype = ctypes.c_ssize_t
u32.DispatchMessageW.argtypes = [POINTER(wintypes.MSG)]
u32.PostMessageW.restype = wintypes.BOOL
u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u32.SetTimer.restype = ctypes.c_size_t
u32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, ctypes.c_void_p]
u32.KillTimer.restype = wintypes.BOOL
u32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
u32.OpenInputDesktop.restype = wintypes.HDESK
u32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
u32.CloseDesktop.restype = wintypes.BOOL
u32.CloseDesktop.argtypes = [wintypes.HDESK]

k32.GetModuleHandleW.restype = wintypes.HMODULE
k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
k32.CreateMutexW.restype = wintypes.HANDLE
k32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
k32.SetLastError.restype = None
k32.SetLastError.argtypes = [wintypes.DWORD]

wts.WTSRegisterSessionNotification.restype = wintypes.BOOL
wts.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
wts.WTSUnRegisterSessionNotification.restype = wintypes.BOOL
wts.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]


def _caps_on() -> bool:
    return (u32.GetKeyState(VK_CAPITAL) & 0x0001) != 0


def is_user_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def is_extended_vk(vk: int) -> bool:
    vk = int(vk)
    try:
        scan = u32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC_EX)
    except Exception:
        scan = 0
    if scan and ((scan >> 8) & 0xFF) in (0xE0, 0xE1):
        return True
    return vk in _EXTENDED_VKS


def vk_display_name(vk: int) -> str:
    vk = int(vk)
    if 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0x30 <= vk <= 0x39:
        return chr(vk)

    scan = 0
    try:
        scan = u32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC_EX)
    except Exception:
        scan = 0

    lparam = 0
    if scan:
        lparam = (scan & 0xFF) << 16
        if ((scan >> 8) & 0xFF) in (0xE0, 0xE1) or is_extended_vk(vk):
            lparam |= 1 << 24
    else:
        try:
            scan = u32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        except Exception:
            scan = 0
        lparam = (scan & 0xFF) << 16

    if lparam:
        buf = ctypes.create_unicode_buffer(64)
        try:
            if u32.GetKeyNameTextW(lparam, buf, 64):
                name = buf.value.strip()
                if name:
                    return name
        except Exception:
            pass
    return _FALLBACK_VK_NAMES.get(vk, f"VK 0x{vk:02X}")


def is_mappable_vk(vk: int) -> bool:
    try:
        vk = int(vk)
    except (TypeError, ValueError):
        return False
    return 1 <= vk <= 0xFE and vk not in _BLOCKED_TARGET_VKS


def _normalize_cfg(raw) -> dict:
    cfg = dict(_DEFAULT_CFG)
    if isinstance(raw, dict):
        for key in ("target_vk", "target_name", "target_extended", "mapping_mode"):
            if key in raw:
                cfg[key] = raw[key]
    try:
        vk = int(cfg.get("target_vk", _DEFAULT_CFG["target_vk"]))
    except (TypeError, ValueError):
        vk = _DEFAULT_CFG["target_vk"]
    if not is_mappable_vk(vk):
        vk = _DEFAULT_CFG["target_vk"]
    cfg["target_vk"] = vk
    cfg["target_name"] = vk_display_name(vk)
    cfg["target_extended"] = is_extended_vk(vk)
    mode = str(cfg.get("mapping_mode", MAPPING_MODE_TOGGLE)).lower()
    if mode not in _MAPPING_MODES:
        mode = MAPPING_MODE_TOGGLE
    cfg["mapping_mode"] = mode
    return cfg


def _load_cfg() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return _normalize_cfg(json.load(f))
    except Exception:
        return _normalize_cfg(None)


def _save_cfg(cfg: dict) -> None:
    try:
        os.makedirs(_CFG_DIR, exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_normalize_cfg(cfg), f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except Exception:
        pass


_mutex_handle = None


def check_single_instance() -> bool:
    global _mutex_handle
    name = "Global\\CapsLockBlocker_SingleInstance_Mutex"
    try:
        k32.SetLastError(0)
        handle = k32.CreateMutexW(None, False, name)
        if not handle:
            k32.SetLastError(0)
            handle = k32.CreateMutexW(None, False, "Local\\CapsLockBlocker_SingleInstance_Mutex")
        if not handle:
            return True
        _mutex_handle = handle
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


def _send_key(vk: int, up: bool = False, extended=None, extra: int = 0) -> bool:
    """通过 SendInput 发送一个按键事件。优先使用扫描码，兼容游戏 Raw Input。"""
    vk = int(vk)
    if extended is None:
        extended = is_extended_vk(vk)

    scan_ex = 0
    try:
        scan_ex = u32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC_EX)
    except Exception:
        scan_ex = 0

    scan = scan_ex & 0xFF
    if scan_ex and ((scan_ex >> 8) & 0xFF) in (0xE0, 0xE1):
        extended = True

    flags = KEYEVENTF_KEYUP if up else 0
    if scan:
        flags |= KEYEVENTF_SCANCODE
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        ki = KEYBDINPUT(0, scan, flags, 0, extra)
    else:
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        ki = KEYBDINPUT(vk, 0, flags, 0, extra)

    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki = ki
    try:
        return u32.SendInput(1, byref(inp), ctypes.sizeof(INPUT)) == 1
    except Exception:
        return False


class SessionWatcher:
    """在独立线程中创建隐藏窗口接收 WM_WTSSESSION_CHANGE。

    不再替换 Tk 主窗口的窗口过程，避免锁屏时窗口过程重入/回调失效导致崩溃。
    WTS 注册失败时，自动降级为 OpenInputDesktop 桌面轮询。
    """

    def __init__(self):
        self.events = queue.Queue()
        self._thread = None
        self._ready = threading.Event()
        self._hwnd = None
        self._wts_ok = False
        self._wndproc_ref = None
        self._desk_reported = None
        self._desk_candidate = None
        self._desk_count = 0

    @property
    def hwnd(self):
        return self._hwnd

    @property
    def wts_ok(self) -> bool:
        return self._wts_ok

    def start(self, timeout: float = 2.0) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="CapsLockSessionWatcher", daemon=True)
        self._thread.start()
        self._ready.wait(timeout)

    def stop(self) -> None:
        hwnd = self._hwnd
        if hwnd:
            try:
                u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(1.5)

    def _run(self) -> None:
        try:
            self._create_and_loop()
        except Exception as exc:
            self.events.put(("error", str(exc)))
            self._ready.set()

    def _create_and_loop(self) -> None:
        hinst = k32.GetModuleHandleW(None)
        class_name = "CapsLockBlockerSessionWatcherWnd"
        wc = WNDCLASSW()
        wc.style = 0
        wc.lpfnWndProc = WNDPROC(self._wndproc)
        wc.cbClsExtra = 0
        wc.cbWndExtra = 0
        wc.hInstance = hinst
        wc.hIcon = None
        wc.hCursor = None
        wc.hbrBackground = None
        wc.lpszMenuName = None
        wc.lpszClassName = class_name
        self._wndproc_ref = wc.lpfnWndProc

        atom = u32.RegisterClassW(byref(wc))
        if not atom:
            err = ctypes.get_last_error()
            if err != ERROR_CLASS_ALREADY_EXISTS:
                raise OSError(err, "RegisterClassW failed")

        hwnd = u32.CreateWindowExW(
            0, class_name, "CapsLockBlockerSessionWatcher", 0,
            0, 0, 0, 0, None, None, hinst, None,
        )
        if not hwnd:
            err = ctypes.get_last_error()
            raise OSError(err, "CreateWindowExW failed")

        self._hwnd = hwnd
        try:
            self._wts_ok = bool(wts.WTSRegisterSessionNotification(hwnd, NOTIFY_FOR_THIS_SESSION))
        except Exception:
            self._wts_ok = False

        if not self._wts_ok:
            u32.SetTimer(hwnd, 1, 500, None)

        self.events.put(("ready", {"wts": self._wts_ok}))
        self._ready.set()

        msg = wintypes.MSG()
        while True:
            ret = u32.GetMessageW(byref(msg), None, 0, 0)
            if ret <= 0:
                break
            u32.TranslateMessage(byref(msg))
            u32.DispatchMessageW(byref(msg))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_WTSSESSION_CHANGE:
                if wparam in (WTS_SESSION_LOCK, WTS_SESSION_LOGOFF):
                    self.events.put(("lock", "wts"))
                elif wparam in (WTS_SESSION_UNLOCK, WTS_SESSION_LOGON):
                    self.events.put(("unlock", "wts"))
            elif msg == WM_TIMER:
                self._poll_desktop()
            elif msg == WM_CLOSE:
                u32.DestroyWindow(hwnd)
                return 0
            elif msg == WM_DESTROY:
                try:
                    u32.KillTimer(hwnd, 1)
                except Exception:
                    pass
                try:
                    wts.WTSUnRegisterSessionNotification(hwnd)
                except Exception:
                    pass
                u32.PostQuitMessage(0)
                return 0
        except Exception:
            pass
        return u32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _poll_desktop(self) -> None:
        try:
            hdesk = u32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
            locked = not hdesk
            if hdesk:
                u32.CloseDesktop(hdesk)
        except Exception:
            return

        if locked != self._desk_candidate:
            self._desk_candidate = locked
            self._desk_count = 1
        else:
            self._desk_count += 1

        if self._desk_count >= 2 and locked != self._desk_reported:
            self._desk_reported = locked
            self.events.put(("lock" if locked else "unlock", "desktop"))


class KeyCaptureDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("捕获目标按键")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result_vk = None
        self.result_name = ""
        self.result_extended = False

        self.geometry("420x250")
        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        self.configure(padx=20, pady=20)

        ttk.Label(
            self,
            text="请按下要映射的按键",
            font=("Microsoft YaHei", 12, "bold"),
            wraplength=370,
            justify="center",
        ).pack(pady=(0, 8))

        self._key_display = tk.StringVar(value="等待按键...")
        ttk.Label(
            self,
            textvariable=self._key_display,
            font=("Microsoft YaHei", 14, "bold"),
            foreground="#0066CC",
            anchor="center",
        ).pack(pady=8)

        ttk.Label(
            self,
            text="支持字母/数字、F1-F24、方向键、小键盘、Ctrl/Shift/Alt 等任意单键\n按 Esc 取消",
            font=("Microsoft YaHei", 9),
            foreground="gray",
            justify="center",
        ).pack(pady=(4, 10))

        ttk.Button(self, text="取消", command=self._cancel).pack()

        self.bind("<KeyPress>", self._on_key)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.focus_set()
        self.after(60000, self._cancel)

    def _on_key(self, event):
        if event.keysym == "Escape":
            self._cancel()
            return "break"
        try:
            vk = int(event.keycode)
        except (TypeError, ValueError):
            return "break"
        if not is_mappable_vk(vk):
            self._key_display.set(f"不支持该按键: {vk_display_name(vk)}")
            return "break"

        self.result_vk = vk
        self.result_name = vk_display_name(vk)
        self.result_extended = is_extended_vk(vk)
        self._key_display.set(self.result_name)
        self.after(120, self.destroy)
        return "break"

    def _cancel(self):
        self.result_vk = None
        try:
            self.destroy()
        except Exception:
            pass


class CapsLockBlocker:
    def __init__(self, silent: bool = False):
        self._silent = silent
        self._is_admin = is_user_admin()
        cfg = _load_cfg()
        self._target_vk = cfg["target_vk"]
        self._target_name = cfg["target_name"]
        self._target_extended = cfg["target_extended"]
        self._mapping_mode = cfg["mapping_mode"]

        self.is_locked = False
        self._mapping_enabled = False
        self._system_locked = False
        self._capturing = False
        self._target_down = False
        self._caps_physical_down = False
        self._last_trigger = 0.0
        self._trigger_count = 0
        self._hook_id = None
        self._hook_ref = None
        self._hook_ok = False
        self._closed = False

        self._watcher = None
        self._watcher_ready = False
        self._watcher_wts_ok = False
        self._watcher_error = None
        self._fallback_last = 0.0
        self._fallback_candidate = None
        self._fallback_count = 0

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        screen_h = self.root.winfo_screenheight()
        win_w = 540
        win_h = min(760, max(560, screen_h - 40))
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.report_callback_exception = self._on_error
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2)
        self.root.geometry(f"+{x}+{y}")

        self._build_ui()
        self._install_hook()
        self._start_watcher()
        self._refresh_lock_ui()
        self._refresh_screen_ui()
        self._refresh_map_ui()

        self.root.after(120, self._poll_session_events)
        self._refresh_status()
        self._refresh_trigger()

    # ---------- UI ----------
    def _build_ui(self):
        header = ttk.Frame(self.root, padding=(18, 12, 18, 4))
        header.pack(fill="x")

        ttk.Label(
            header,
            text="游戏 Capslock 锁定映射工具",
            font=("Microsoft YaHei", 14, "bold"),
        ).pack(pady=(0, 2))
        ttk.Label(
            header,
            text=f"v{APP_VERSION}  ·  先锁定 CapsLock，再选择是否映射",
            font=("Microsoft YaHei", 8),
            foreground="gray",
        ).pack(pady=(0, 6))

        self._btn_lock = ttk.Button(
            header,
            text="[ 锁定 CapsLock ]",
            command=self._toggle_lock,
            width=24,
        )
        self._btn_lock.pack(pady=(2, 2))

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True)

        bg = ttk.Style().lookup("TFrame", "background") or self.root.cget("background")
        self._canvas = tk.Canvas(body, highlightthickness=0, borderwidth=0, background=bg)
        self._canvas.pack(side="left", fill="both", expand=True)

        f = ttk.Frame(self._canvas, padding=(12, 8, 12, 14))
        self._canvas_window = self._canvas.create_window((0, 0), window=f, anchor="nw")
        f.bind("<Configure>", lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfigure(self._canvas_window, width=e.width))
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

        sf = ttk.LabelFrame(f, text="状态", padding=8)
        sf.pack(fill="x", pady=(0, 8))

        rows = [
            ("lock", "锁定状态:", "已解锁", "green"),
            ("caps", "CapsLock:", "检测中...", None),
            ("mode", "映射模式:", "未锁定", "gray"),
            ("screen", "系统桌面:", "活跃", "gray"),
            ("admin", "运行权限:", "管理员" if self._is_admin else "普通", "green" if self._is_admin else "orange"),
            ("watcher", "锁屏检测:", "启动中...", "gray"),
        ]
        self._status_vars = {}
        self._status_labels = {}
        for key, label, initial, fg in rows:
            row = ttk.Frame(sf)
            row.pack(fill="x", pady=1)
            ttk.Label(
                row,
                text=label,
                width=12,
                anchor="e",
                font=("Microsoft YaHei", 9),
            ).pack(side="left")
            var = tk.StringVar(value=initial)
            lbl = ttk.Label(row, textvariable=var, font=("Microsoft YaHei", 9, "bold"))
            if fg:
                lbl.config(foreground=fg)
            lbl.pack(side="left", padx=(6, 0))
            self._status_vars[key] = var
            self._status_labels[key] = lbl

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=6)

        mf = ttk.LabelFrame(f, text="按键映射", padding=8)
        mf.pack(fill="x", pady=(4, 8))

        self._capture_btn = ttk.Button(
            mf,
            text="[ 捕获目标按键 ]",
            command=self._capture,
            width=24,
        )
        self._capture_btn.pack(pady=(0, 8))

        cur = ttk.Frame(mf)
        cur.pack(fill="x", pady=2)
        ttk.Label(
            cur,
            text="当前映射:",
            width=10,
            anchor="e",
            font=("Microsoft YaHei", 9),
        ).pack(side="left")
        self._map_display_var = tk.StringVar()
        self._map_display_lbl = ttk.Label(
            cur,
            textvariable=self._map_display_var,
            font=("Microsoft YaHei", 9, "bold"),
            foreground="#0066CC",
        )
        self._map_display_lbl.pack(side="left", padx=(6, 0))

        self._mapping_var = tk.BooleanVar(value=False)
        self._mapping_chk = ttk.Checkbutton(
            mf,
            text="锁定期间启用映射（先锁定，再勾选）",
            variable=self._mapping_var,
            command=self._on_mapping_toggle,
        )
        self._mapping_chk.pack(anchor="center", pady=(6, 0))

        mode_row = ttk.Frame(mf)
        mode_row.pack(fill="x", pady=(4, 0))
        ttk.Label(
            mode_row,
            text="映射方式:",
            width=10,
            anchor="e",
            font=("Microsoft YaHei", 9),
        ).pack(side="left")
        self._map_mode_var = tk.StringVar(value=self._mapping_mode)
        self._mode_toggle_rb = ttk.Radiobutton(
            mode_row,
            text="按一下保持/再按释放",
            variable=self._map_mode_var,
            value=MAPPING_MODE_TOGGLE,
            command=self._on_mapping_mode_changed,
        )
        self._mode_toggle_rb.pack(side="left", padx=(4, 0))
        self._mode_hold_rb = ttk.Radiobutton(
            mode_row,
            text="按住触发",
            variable=self._map_mode_var,
            value=MAPPING_MODE_HOLD,
            command=self._on_mapping_mode_changed,
        )
        self._mode_hold_rb.pack(side="left", padx=(4, 0))

        ttk.Label(
            mf,
            text="切换锁定 = 按一次 CapsLock 保持目标键按下，再按一次释放；按住 = 按住 CapsLock 才触发。",
            font=("Microsoft YaHei", 8),
            foreground="gray",
            wraplength=390,
            justify="center",
        ).pack(pady=(2, 0))

        self._trigger_var = tk.StringVar(value="尚未触发")
        tr = ttk.Frame(mf)
        tr.pack(fill="x", pady=2)
        ttk.Label(
            tr,
            text="触发指示:",
            width=10,
            anchor="e",
            font=("Microsoft YaHei", 9),
        ).pack(side="left")
        ttk.Label(
            tr,
            textvariable=self._trigger_var,
            font=("Microsoft YaHei", 9),
            foreground="gray",
        ).pack(side="left", padx=(6, 0))

        ttk.Label(
            mf,
            text="支持任意单键：字母/数字、F1-F24、方向键、小键盘、Ctrl/Shift/Alt 等",
            font=("Microsoft YaHei", 8),
            foreground="gray",
            wraplength=390,
            justify="center",
        ).pack(pady=(6, 0))

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=6)

        ttk.Label(
            f,
            text="先锁定 CapsLock；锁定后才能勾选映射。\n解除锁定、锁屏或关闭程序后恢复 CapsLock 原生功能。",
            font=("Microsoft YaHei", 8),
            foreground="gray",
            wraplength=400,
            justify="center",
        ).pack(pady=(6, 0))

        if not self._is_admin:
            ttk.Label(
                f,
                text="当前以普通权限运行：如果前台游戏/窗口是管理员权限，Windows 会拦截键盘钩子和按键注入，映射会失效。\n请关闭程序，右键 run_source.bat 或 GameCapslockMapper.exe，选择“以管理员身份运行”。",
                font=("Microsoft YaHei", 8),
                foreground="#CC6600",
                wraplength=400,
                justify="center",
            ).pack(pady=(4, 0))

    def _on_mousewheel(self, event):
        try:
            steps = int(-event.delta / 120)
            if steps:
                self._canvas.yview_scroll(steps * 3, "units")
        except Exception:
            pass

    def _set_status(self, key: str, text: str, color=None):
        var = self._status_vars.get(key)
        lbl = self._status_labels.get(key)
        if var is not None:
            var.set(text)
        if lbl is not None and color:
            lbl.config(foreground=color)

    def _refresh_lock_ui(self):
        if not self._hook_ok:
            self._set_status("lock", "键盘钩子失败", "red")
            self._set_status("mode", "无法锁定", "red")
        elif self._system_locked:
            self._set_status("lock", "锁屏已释放", "orange")
            self._set_status("mode", "CapsLock 正常", "orange")
        elif self.is_locked:
            mode_label = "切换锁定" if self._mapping_mode == MAPPING_MODE_TOGGLE else "按住触发"
            self._set_status("lock", "已锁定", "red")
            self._set_status(
                "mode",
                f"已锁定并映射（{mode_label}）" if self._mapping_enabled else "已锁定（未映射）",
                "#0066CC" if self._mapping_enabled else "gray",
            )
        else:
            self._set_status("lock", "已解锁", "green")
            self._set_status("mode", "CapsLock 正常", "gray")

        if self._system_locked:
            self._btn_lock.config(text="[ 锁屏中，CapsLock 已恢复 ]")
        elif self.is_locked:
            self._btn_lock.config(text="[ 解除锁定 ]")
        else:
            self._btn_lock.config(text="[ 锁定 CapsLock ]")

        if self._system_locked or not self._hook_ok:
            self._btn_lock.config(state="disabled")
        else:
            self._btn_lock.config(state="normal")

        editing_state = "normal" if (self.is_locked and not self._system_locked and self._hook_ok) else "disabled"
        self._capture_btn.config(state=editing_state)
        self._mapping_chk.config(state=editing_state)
        self._mode_toggle_rb.config(state=editing_state)
        self._mode_hold_rb.config(state=editing_state)
        self._mapping_var.set(bool(self._mapping_enabled))
        self._map_mode_var.set(self._mapping_mode)
        self._refresh_map_ui()
        self._update_title()

    def _refresh_screen_ui(self):
        if self._system_locked:
            self._set_status("screen", "锁屏中", "orange")
        else:
            self._set_status("screen", "活跃", "gray")

    def _refresh_map_ui(self):
        suffix = "（保持按下）" if self._target_down else ""
        self._map_display_var.set(f"CapsLock -> {self._target_name}{suffix}")
        if self._mapping_enabled:
            self._map_display_lbl.config(foreground="#0066CC")
        else:
            self._map_display_lbl.config(foreground="gray")
        if hasattr(self, "_mapping_var"):
            self._mapping_var.set(bool(self._mapping_enabled))
        if hasattr(self, "_map_mode_var"):
            self._map_mode_var.set(self._mapping_mode)

    def _update_title(self):
        title = f"{APP_NAME} v{APP_VERSION}"
        if self._system_locked:
            title += " - [锁屏中]"
        elif self.is_locked:
            title += " - [已锁定]"
        self.root.title(title)

    # ---------- hook / input ----------
    def _install_hook(self):
        self._hook_ref = HOOKPROC(self._hook_callback)
        self._hook_id = u32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_ref, 0, 0)
        if not self._hook_id:
            err = ctypes.get_last_error()
            self._hook_ok = False
            msg = {
                5: "权限不足，请尝试以管理员身份运行。",
                8: "系统资源不足，请重启后再试。",
            }.get(err, f"错误码 {err}。")
            if not self._silent:
                try:
                    messagebox.showwarning(
                        APP_NAME,
                        f"键盘钩子安装失败：\n{msg}\n\n当前无法锁定 CapsLock。",
                    )
                except Exception:
                    pass
            return
        self._hook_ok = True

    def _call_next(self, nCode, wParam, lParam):
        return u32.CallNextHookEx(self._hook_id or 0, nCode, wParam, lParam)

    def _hook_callback(self, nCode, wParam, lParam):
        try:
            if nCode < 0:
                return self._call_next(nCode, wParam, lParam)
            if not self.is_locked or self._system_locked or self._capturing:
                return self._call_next(nCode, wParam, lParam)
            if wParam not in _ALL_KEY_EVENTS:
                return self._call_next(nCode, wParam, lParam)

            kb = cast(lParam, POINTER(KBDLLHOOKSTRUCT)).contents
            # 放行程序自己注入的事件，避免 SendInput 再次触发状态机。
            if int(kb.flags) & LLKHF_INJECTED:
                if kb.vkCode == VK_CAPITAL:
                    return 1
                return self._call_next(nCode, wParam, lParam)
            if kb.vkCode != VK_CAPITAL:
                return self._call_next(nCode, wParam, lParam)
            if int(kb.dwExtraInfo) == MAGIC_EXTRA:
                return self._call_next(nCode, wParam, lParam)

            is_down = wParam in _KEYDOWN_EVENTS
            is_up = wParam in _KEYUP_EVENTS
            if is_down:
                # 忽略按住 CapsLock 产生的自动重复。
                if self._caps_physical_down:
                    return 1
                self._caps_physical_down = True
                self._last_trigger = time.time()
                self._trigger_count += 1
                if self._mapping_enabled:
                    if self._mapping_mode == MAPPING_MODE_TOGGLE:
                        if self._target_down:
                            self._release_target()
                        else:
                            self._emit_target(True)
                    else:
                        self._emit_target(True)
            elif is_up:
                self._caps_physical_down = False
                if self._mapping_enabled and self._mapping_mode == MAPPING_MODE_HOLD:
                    self._emit_target(False)

            # 锁定期间完全吃掉 CapsLock，系统大小写状态不会改变。
            return 1
        except Exception:
            try:
                return self._call_next(nCode, wParam, lParam)
            except Exception:
                return 0

    def _emit_target(self, down: bool):
        _send_key(
            self._target_vk,
            up=not down,
            extended=self._target_extended,
        )
        self._target_down = bool(down)

    def _release_target(self):
        if self._target_down:
            _send_key(self._target_vk, up=True, extended=self._target_extended)
            self._target_down = False

    # ---------- lock state ----------
    def _toggle_lock(self):
        if self.is_locked:
            self._unlock()
        else:
            self._lock()

    def _lock(self):
        if self._system_locked or not self._hook_ok:
            return
        self._release_target()
        self._caps_physical_down = False
        self.is_locked = True
        self._mapping_enabled = False
        self._refresh_lock_ui()
        self._refresh_map_ui()

    def _lock_with_map(self):
        self._lock()
        if self.is_locked:
            self._set_mapping_enabled(True)

    def _lock_only(self):
        self._lock()

    def _unlock(self):
        if self._system_locked:
            return
        self._release_target()
        self._caps_physical_down = False
        self.is_locked = False
        self._mapping_enabled = False
        self._refresh_lock_ui()
        self._refresh_map_ui()

    def _set_mapping_enabled(self, enabled: bool):
        if not self.is_locked or self._system_locked:
            self._mapping_enabled = False
            self._mapping_var.set(False)
            return
        self._mapping_enabled = bool(enabled)
        self._mapping_var.set(self._mapping_enabled)
        if not self._mapping_enabled:
            self._release_target()
        self._refresh_lock_ui()
        self._refresh_map_ui()

    def _on_mapping_toggle(self):
        self._set_mapping_enabled(bool(self._mapping_var.get()))

    def _on_mapping_mode_changed(self):
        mode = self._map_mode_var.get()
        if mode not in _MAPPING_MODES:
            self._map_mode_var.set(self._mapping_mode)
            return
        if not self.is_locked or self._system_locked:
            self._map_mode_var.set(self._mapping_mode)
            return
        self._release_target()
        self._mapping_mode = mode
        self._save()
        self._refresh_lock_ui()
        self._refresh_map_ui()

    def _set_system_locked(self, locked: bool):
        locked = bool(locked)
        if locked == self._system_locked:
            return
        self._system_locked = locked
        # 锁屏视为“恢复默认”的出口：解除映射并解除锁定，解锁后保持原生 CapsLock。
        self._release_target()
        self._caps_physical_down = False
        self.is_locked = False
        self._mapping_enabled = False
        self._refresh_lock_ui()
        self._refresh_screen_ui()
        self._refresh_map_ui()

    # ---------- capture / config ----------
    def _capture(self):
        if not self.is_locked or self._system_locked:
            return
        self._release_target()
        self._capturing = True
        try:
            dialog = KeyCaptureDialog(self.root)
            self.root.wait_window(dialog)
        finally:
            self._capturing = False

        if dialog.result_vk is not None:
            self._target_vk = dialog.result_vk
            self._target_name = dialog.result_name
            self._target_extended = dialog.result_extended
            self._refresh_map_ui()
            _save_cfg({
                "target_vk": self._target_vk,
                "target_name": self._target_name,
                "target_extended": self._target_extended,
                "mapping_mode": self._mapping_mode,
            })

    def _save(self):
        _save_cfg({
            "target_vk": self._target_vk,
            "target_name": self._target_name,
            "target_extended": self._target_extended,
            "mapping_mode": self._mapping_mode,
        })

    # ---------- watcher / status ----------
    def _start_watcher(self):
        self._watcher = SessionWatcher()
        self._watcher.start(timeout=2.0)

    def _poll_session_events(self):
        if self._closed:
            return
        if self._watcher is not None:
            while True:
                try:
                    kind, data = self._watcher.events.get_nowait()
                except queue.Empty:
                    break
                except Exception:
                    break
                if kind == "ready":
                    self._watcher_ready = True
                    self._watcher_wts_ok = bool(data.get("wts")) if isinstance(data, dict) else False
                    if self._watcher_wts_ok:
                        self._set_status("watcher", "WTS 会话通知", "green")
                    else:
                        self._set_status("watcher", "桌面轮询（备用）", "orange")
                elif kind == "error":
                    self._watcher_error = str(data)
                    self._set_status("watcher", "桌面轮询（兜底）", "orange")
                elif kind == "lock":
                    self._set_system_locked(True)
                elif kind == "unlock":
                    self._set_system_locked(False)

        if (not self._watcher_ready) or self._watcher_error:
            self._poll_desktop_fallback()

        self.root.after(150, self._poll_session_events)

    def _poll_desktop_fallback(self):
        now = time.monotonic()
        if now - self._fallback_last < 0.5:
            return
        self._fallback_last = now
        try:
            hdesk = u32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
            locked = not hdesk
            if hdesk:
                u32.CloseDesktop(hdesk)
        except Exception:
            return

        if locked != self._fallback_candidate:
            self._fallback_candidate = locked
            self._fallback_count = 1
        else:
            self._fallback_count += 1
        if self._fallback_count >= 2 and locked != self._system_locked:
            self._set_system_locked(locked)

    def _refresh_status(self):
        if self._closed:
            return
        caps_on = _caps_on()
        self._set_status("caps", "大写" if caps_on else "小写", "orange" if caps_on else "gray")
        self.root.after(300, self._refresh_status)

    def _refresh_trigger(self):
        if self._closed:
            return
        if self._trigger_count == 0:
            self._trigger_var.set("尚未触发")
        else:
            elapsed = time.time() - self._last_trigger
            if elapsed < 2:
                s = "刚刚触发"
            elif elapsed < 10:
                s = f"约 {int(elapsed)} 秒前触发"
            else:
                s = f"约 {int(elapsed / 60)} 分钟前触发"
            self._trigger_var.set(f"{s}（共 {self._trigger_count} 次）")
        self._refresh_map_ui()
        self.root.after(500, self._refresh_trigger)

    # ---------- lifecycle ----------
    def _on_error(self, exc, val, tb):
        err = "".join(traceback.format_exception(exc, val, tb))
        if self._silent:
            print(err, file=sys.stderr)
            return
        try:
            messagebox.showerror(
                f"{APP_NAME} - 异常",
                f"程序遇到错误：\n\n{err[-800:]}",
            )
        except Exception:
            pass

    def _on_close(self):
        if self._closed:
            return
        self._closed = True
        self._release_target()
        self._caps_physical_down = False
        if self._hook_id:
            try:
                u32.UnhookWindowsHookEx(self._hook_id)
            except Exception:
                pass
            self._hook_id = None
        if self._watcher is not None:
            try:
                self._watcher.stop()
            except Exception:
                pass
        try:
            self.root.destroy()
        except Exception:
            pass


def _wait_for_event(watcher: SessionWatcher, kind: str, timeout: float):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            event_kind, data = watcher.events.get(timeout=0.1)
        except queue.Empty:
            continue
        if event_kind == kind:
            return data
    return None


def _self_test() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(f"{APP_NAME} v{APP_VERSION} 自检")
    ok = True

    def check(name, condition, detail=""):
        nonlocal ok
        if not condition:
            ok = False
        print(f"  [{'OK' if condition else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))

    check("字母键名", vk_display_name(0x41) == "A", vk_display_name(0x41))
    check("数字键名", vk_display_name(0x37) == "7", vk_display_name(0x37))
    check("Esc 键名", vk_display_name(0x1B) == "Esc", vk_display_name(0x1B))
    check("方向键为扩展键", is_extended_vk(0x25), vk_display_name(0x25))
    check("方向键名称", vk_display_name(0x25) == "Left", vk_display_name(0x25))
    check("字母键非扩展键", not is_extended_vk(0x41))
    check("CapsLock 不可作为目标", not is_mappable_vk(VK_CAPITAL))
    check("F1 可作为目标", is_mappable_vk(0x70))
    check("Ctrl 可作为目标", is_mappable_vk(0xA2))

    bad_cfg = _normalize_cfg({"target_vk": 0x14, "target_name": "x"})
    check("非法目标回退 Esc", bad_cfg["target_vk"] == 0x1B, hex(bad_cfg["target_vk"]))
    good_cfg = _normalize_cfg({"target_vk": 0x70})
    check("配置规范化 F1", good_cfg["target_vk"] == 0x70, good_cfg["target_name"])

    watcher = SessionWatcher()
    watcher.start(timeout=3.0)
    ready = None
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            kind, data = watcher.events.get(timeout=0.1)
        except queue.Empty:
            continue
        if kind == "ready":
            ready = data
            break
        if kind == "error":
            print(f"  [FAIL] 会话监视器启动 - {data}")
            ok = False
            break

    check("会话监视器窗口", ready is not None and watcher.hwnd not in (None, 0), str(ready))
    check("锁屏检测方式", ready is not None, "WTS" if watcher.wts_ok else "桌面轮询")

    if watcher.hwnd:
        u32.PostMessageW(watcher.hwnd, WM_WTSSESSION_CHANGE, WTS_SESSION_LOCK, 0)
        check("模拟锁屏事件", _wait_for_event(watcher, "lock", 2.0) is not None)
        u32.PostMessageW(watcher.hwnd, WM_WTSSESSION_CHANGE, WTS_SESSION_UNLOCK, 0)
        check("模拟解锁事件", _wait_for_event(watcher, "unlock", 2.0) is not None)

    watcher.stop()
    print("SELF_TEST_OK" if ok else "SELF_TEST_FAILED")
    return 0 if ok else 1


def _run_smoke(app: CapsLockBlocker) -> int:
    results = {}
    try:
        app._target_vk = 0x87  # F24，绝大多数程序忽略
        app._target_name = vk_display_name(0x87)
        app._target_extended = is_extended_vk(0x87)
        results["hook_ok"] = app._hook_ok

        # 1. 先锁定：默认不映射，锁定后编辑控件才可用。
        app._lock()
        results["locked"] = bool(app.is_locked and not app._mapping_enabled)
        results["capture_enabled"] = str(app._capture_btn.cget("state")) == "normal"

        # 2. 锁定后启用映射；默认“切换锁定”：第一次按下保持目标键，第二次释放。
        app._mapping_var.set(True)
        app._on_mapping_toggle()
        results["map_enabled"] = bool(app.is_locked and app._mapping_enabled)
        results["default_toggle_mode"] = (app._mapping_mode == MAPPING_MODE_TOGGLE)
        kb = KBDLLHOOKSTRUCT(VK_CAPITAL, 0, 0, 0, 0)
        lp = ctypes.addressof(kb)
        count_before = app._trigger_count
        ret_down = app._hook_callback(0, WM_KEYDOWN, lp)
        results["hook_down_blocked"] = (ret_down == 1)
        results["hook_map_emitted"] = bool(app._target_down and app._trigger_count == count_before + 1)
        ret_up = app._hook_callback(0, WM_KEYUP, lp)
        results["hook_up_blocked"] = (ret_up == 1)
        results["toggle_held_after_up"] = bool(app._target_down)

        ret_down2 = app._hook_callback(0, WM_KEYDOWN, lp)
        app._hook_callback(0, WM_KEYUP, lp)
        results["toggle_released_on_second_press"] = bool(ret_down2 == 1 and not app._target_down)

        # 3. 注入事件必须被过滤，不能再次触发状态机。
        kb_inj = KBDLLHOOKSTRUCT(VK_CAPITAL, 0, LLKHF_INJECTED, 0, 0)
        lp_inj = ctypes.addressof(kb_inj)
        count_inj = app._trigger_count
        ret_inj = app._hook_callback(0, WM_KEYDOWN, lp_inj)
        results["injected_blocked"] = bool(ret_inj == 1 and app._trigger_count == count_inj and not app._target_down)

        # 4. 按住触发模式：按下目标键保持，抬起即释放。
        app._map_mode_var.set(MAPPING_MODE_HOLD)
        app._on_mapping_mode_changed()
        results["mode_hold_switched"] = (app._mapping_mode == MAPPING_MODE_HOLD)
        app._hook_callback(0, WM_KEYDOWN, lp)
        results["hold_pressed"] = bool(app._target_down)
        app._hook_callback(0, WM_KEYUP, lp)
        results["hold_released_on_up"] = bool(not app._target_down)

        # 5. 取消映射但仍保持锁定。
        app._mapping_var.set(False)
        app._on_mapping_toggle()
        results["map_disabled_still_locked"] = bool(app.is_locked and not app._mapping_enabled)
        ret_block = app._hook_callback(0, WM_KEYDOWN, lp)
        results["hook_lock_only"] = bool(ret_block == 1 and not app._target_down)
        app._hook_callback(0, WM_KEYUP, lp)

        # 6. 解除锁定恢复原生。
        app._unlock()
        results["unlocked"] = bool(not app.is_locked and not app._mapping_enabled)

        # 7. 锁屏直接解除锁定和映射；解锁后保持原生，不自动恢复。
        app._lock_with_map()
        results["locked_map"] = bool(app.is_locked and app._mapping_enabled)
        app._set_system_locked(True)
        results["screen_released"] = bool(not app.is_locked and not app._mapping_enabled)
        app._set_system_locked(False)
        results["screen_stays_unlocked"] = bool(not app.is_locked and not app._mapping_enabled)
        app._unlock()
    except Exception as exc:
        results["error"] = str(exc)
        traceback.print_exc()

    app.root.after(250, app._on_close)
    app.root.mainloop()
    print("GUI_SMOKE_RESULT " + json.dumps(results, ensure_ascii=False))
    if results.get("error"):
        print("GUI_SMOKE_FAILED")
        return 1
    required = [
        "locked", "capture_enabled", "map_enabled", "default_toggle_mode",
        "map_disabled_still_locked", "unlocked", "locked_map",
        "screen_released", "screen_stays_unlocked",
        "toggle_held_after_up", "toggle_released_on_second_press",
        "injected_blocked", "mode_hold_switched", "hold_pressed", "hold_released_on_up",
    ]
    if results.get("hook_ok"):
        required += ["hook_down_blocked", "hook_map_emitted", "hook_up_blocked", "hook_lock_only"]
    if not all(results.get(key) for key in required):
        print("GUI_SMOKE_FAILED")
        return 1
    print("GUI_SMOKE_OK")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return _self_test()

    smoke = "--smoke-test" in sys.argv
    if not smoke and not check_single_instance():
        try:
            messagebox.showinfo(APP_NAME, "程序已在运行中。")
        except Exception:
            pass
        return 0

    try:
        app = CapsLockBlocker(silent=smoke)
    except Exception as exc:
        if smoke:
            print(f"GUI_SMOKE_FAILED: {exc}", file=sys.stderr)
            traceback.print_exc()
        else:
            try:
                messagebox.showerror(APP_NAME, f"启动失败：\n{exc}")
            except Exception:
                pass
        return 1

    if smoke:
        return _run_smoke(app)

    app.root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
