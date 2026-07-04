"""
游戏 Capslock 锁定映射工具
===========================
解决游戏时误触 CapsLock 导致操作失误的痛点。
锁定后 CapsLock 映射为字母/数字键，解锁即恢复。

作者: CodeWhale
"""

import ctypes
from ctypes import wintypes, WINFUNCTYPE, POINTER, byref, cast
import tkinter as tk
from tkinter import ttk, messagebox
import sys
import json
import os
import time
import traceback

WH_KEYBOARD_LL = 13
VK_CAPITAL     = 0x14

_ALL_KEY_EVENTS = {0x0100, 0x0101, 0x0104, 0x0105}
_KEYUP_EVENTS   = {0x0101, 0x0105}

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP       = 0x0002
MAPVK_VK_TO_VSC       = 0

GWLP_WNDPROC = -4
WM_WTSSESSION_CHANGE    = 0x02B1
WTS_SESSION_LOCK        = 0x7
WTS_SESSION_UNLOCK      = 0x8
NOTIFY_FOR_THIS_SESSION = 0

EXTENDED_KEY_VKS = {
    0xA3, 0xA5, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22,
    0x25, 0x26, 0x27, 0x28, 0x5B, 0x5C, 0x5D, 0x6F, 0x90,
}
_VALID_VK_RANGES = [(0x41, 0x5A), (0x30, 0x39)]

_CFG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CapsLockBlocker")
os.makedirs(_CFG_DIR, exist_ok=True)
CONFIG_PATH = os.path.join(_CFG_DIR, "config.json")

if not hasattr(wintypes, "ULONG_PTR"):
    wintypes.ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
if not hasattr(wintypes, "LRESULT"):
    wintypes.LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
if not hasattr(wintypes, "LONG_PTR"):
    wintypes.LONG_PTR = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    ]

HOOKPROC = WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC  = WINFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT,
                        wintypes.WPARAM, wintypes.LPARAM)

u32, k32, wts = ctypes.windll.user32, ctypes.windll.kernel32, ctypes.windll.wtsapi32

u32.SetWindowsHookExW.restype  = wintypes.HHOOK
u32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
u32.CallNextHookEx.restype  = ctypes.c_long
u32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
u32.UnhookWindowsHookEx.restype  = wintypes.BOOL
u32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
u32.GetKeyState.restype  = wintypes.SHORT
u32.GetKeyState.argtypes = [ctypes.c_int]
u32.keybd_event.restype  = None
u32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wintypes.DWORD, wintypes.ULONG_PTR]
u32.MapVirtualKeyW.restype  = wintypes.UINT
u32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]

k32.GetModuleHandleW.restype  = wintypes.HMODULE
k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
k32.GetLastError.restype  = wintypes.DWORD
k32.GetLastError.argtypes = []

u32.GetWindowLongPtrW.restype  = wintypes.LONG_PTR
u32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
u32.SetWindowLongPtrW.restype  = wintypes.LONG_PTR
u32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG_PTR]
u32.CallWindowProcW.restype  = wintypes.LRESULT
u32.CallWindowProcW.argtypes = [WNDPROC, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
u32.DefWindowProcW.restype  = wintypes.LRESULT
u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

wts.WTSRegisterSessionNotification.restype  = wintypes.BOOL
wts.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]
wts.WTSUnRegisterSessionNotification.restype  = wintypes.BOOL
wts.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]


def _check_single_instance() -> bool:
    k32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    k32.CreateMutexW.restype  = wintypes.HANDLE
    k32.CreateMutexW(None, False, "Global\\CapsLockBlocker_SingleInstance_Mutex")
    return k32.GetLastError() != 183

def _caps_on() -> bool:
    return (u32.GetKeyState(VK_CAPITAL) & 0x0001) != 0

_DEFAULT_CFG = {"target_vk": 0x1B, "target_name": "Esc", "target_extended": False}

def _load_cfg():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return dict(_DEFAULT_CFG)

def _save_cfg(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class KeyCaptureDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("捕获目标按键")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result_vk, self.result_name, self.result_extended = None, "", False

        self.geometry("400x240")
        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        self.configure(padx=20, pady=20)

        ttk.Label(self, text="请按下要映射的字母键或数字键",
                  font=("Microsoft YaHei", 12, "bold"),
                  wraplength=340, justify="center").pack(pady=(0, 12))

        self._key_display = tk.StringVar(value="等待按键 (仅字母/数字)...")
        ttk.Label(self, textvariable=self._key_display,
                  font=("Microsoft YaHei", 14, "bold"),
                  foreground="#0066CC", anchor="center").pack(pady=10)

        ttk.Label(self, text="按下字母或数字键自动确认并关闭",
                  font=("Microsoft YaHei", 9), foreground="gray",
                  anchor="center").pack(pady=(15, 0))

        self.bind("<KeyPress>", self._on_key)
        self.focus_set()
        self.after(60000, self.destroy)

    def _on_key(self, event):
        vk = event.keycode
        ok = any(lo <= vk <= hi for lo, hi in _VALID_VK_RANGES)
        if not ok:
            self._key_display.set("无效按键 (仅限字母/数字)")
            return
        self.result_vk = vk
        self.result_extended = False
        self.result_name = event.keysym.upper() if event.keysym else chr(vk)
        self.destroy()


class CapsLockBlocker:
    def __init__(self):
        cfg = _load_cfg()
        for k, v in _DEFAULT_CFG.items():
            if k not in cfg:
                cfg[k] = v
        self._target_vk       = int(cfg["target_vk"])
        self._target_name     = str(cfg["target_name"])
        self._target_extended = bool(cfg.get("target_extended", False))
        if self._target_vk < 1 or self._target_vk > 255:
            self._target_vk = 0x1B

        self.is_locked        = False
        self._mapping_enabled = False
        self._prev_lock_state = False
        self._is_ws_locked    = False
        self._last_trigger    = 0.0
        self._trigger_count   = 0
        self._hook_id, self._hook_ref = None, None
        self._orig_wndproc, self._wndproc_ref = None, None

        self.root = tk.Tk()
        self.root.title("游戏 Capslock 锁定映射工具")
        self.root.geometry("430x700")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.report_callback_exception = self._on_error

        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

        self._build_ui()
        self._refresh_lock_ui()
        self._install_hook()
        self.root.after(200, self._register_session_notification)
        self._refresh_status()
        self._refresh_trigger()

    def _on_error(self, exc, val, tb):
        err = ''.join(traceback.format_exception(exc, val, tb))
        try:
            messagebox.showerror("游戏 Capslock 锁定映射工具 - 异常", f"程序遇到错误:\n\n{err[-300:]}")
        except Exception:
            pass

    def _build_ui(self):
        f = ttk.Frame(self.root, padding=20)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="游戏 Capslock 锁定映射工具",
                  font=("Microsoft YaHei", 14, "bold")).pack(pady=(0, 12))

        sf = ttk.LabelFrame(f, text="状态", padding=10)
        sf.pack(fill="x", pady=(0, 10))

        for label, var, fg in [
            ("锁定状态:", "已解锁", "green"),
            ("CapsLock:",  "检测中...", None),
            ("系统桌面:",  "活跃", "gray"),
        ]:
            row = ttk.Frame(sf)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=12, anchor="e",
                      font=("Microsoft YaHei", 10)).pack(side="left")
            sv = tk.StringVar(value=var)
            lbl = ttk.Label(row, textvariable=sv, font=("Microsoft YaHei", 10, "bold"))
            if fg:
                lbl.config(foreground=fg)
            lbl.pack(side="left", padx=(6, 0))
            if "锁定" in label:
                self._lock_var, self._lock_lbl = sv, lbl
            elif "Caps" in label:
                self._caps_var = sv
            else:
                self._screen_var, self._screen_lbl = sv, lbl

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=5)

        mf = ttk.LabelFrame(f, text="按键映射", padding=10)
        mf.pack(fill="x", pady=(8, 5))

        self._capture_btn = ttk.Button(mf, text="[ 捕获目标按键 ]",
                                        command=self._capture, width=24)
        self._capture_btn.pack(pady=(0, 10))

        cur = ttk.Frame(mf)
        cur.pack(fill="x", pady=(0, 10))
        ttk.Label(cur, text="当前映射:", width=10, anchor="e",
                  font=("Microsoft YaHei", 10)).pack(side="left")
        self._map_display_var = tk.StringVar()
        self._map_display_lbl = ttk.Label(cur, textvariable=self._map_display_var,
                                           font=("Microsoft YaHei", 10, "bold"),
                                           foreground="#0066CC")
        self._map_display_lbl.pack(side="left", padx=(6, 0))

        self._trigger_var = tk.StringVar(value="尚未触发")
        tr = ttk.Frame(mf)
        tr.pack(fill="x", pady=(0, 5))
        ttk.Label(tr, text="触发指示:", width=10, anchor="e",
                  font=("Microsoft YaHei", 9)).pack(side="left")
        ttk.Label(tr, textvariable=self._trigger_var,
                  font=("Microsoft YaHei", 9), foreground="gray").pack(side="left", padx=(6, 0))

        self._refresh_map_ui()

        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=10)

        self._btn_map = ttk.Button(f, text="[ 锁定并映射 ]", command=self._lock_with_map, width=24)
        self._btn_only = ttk.Button(f, text="[ 仅锁定 CapsLock ]", command=self._lock_only, width=24)
        self._btn_unlock = ttk.Button(f, text="[ 解除锁定 ]", command=self._unlock, width=24)

        ttk.Label(f, text="锁定后按 CapsLock 即触发上方自定义按键\n解锁后 CapsLock 恢复原功能",
                  font=("Microsoft YaHei", 9), foreground="gray",
                  wraplength=360, justify="center").pack()

    def _install_hook(self):
        self._hook_ref = HOOKPROC(self._hook_callback)
        self._hook_id = u32.SetWindowsHookExW(WH_KEYBOARD_LL, self._hook_ref, 0, 0)
        if not self._hook_id:
            err = k32.GetLastError()
            self._caps_var.set("钩子失败")
            self._btn_map.config(state="disabled", text="不可用"); self._btn_only.config(state="disabled", text="不可用")
            msg = {5: "权限不足，右键以管理员运行。", 8: "系统资源不足。"}.get(err, f"错误码 {err}。")
            messagebox.showwarning("游戏 Capslock 锁定映射工具", msg)

    def _hook_callback(self, nCode, wParam, lParam):
        if not (nCode >= 0 and self.is_locked and not self._is_ws_locked):
            return u32.CallNextHookEx(
                self._hook_id if self._hook_id else 0, nCode, wParam, lParam)

        kb = cast(lParam, POINTER(KBDLLHOOKSTRUCT)).contents
        if kb.vkCode != VK_CAPITAL or wParam not in _ALL_KEY_EVENTS:
            return u32.CallNextHookEx(
                self._hook_id if self._hook_id else 0, nCode, wParam, lParam)

        self._last_trigger = time.time()
        self._trigger_count += 1

        if self._mapping_enabled:
            try:
                flags = KEYEVENTF_EXTENDEDKEY if self._target_extended else 0
                if wParam in _KEYUP_EVENTS:
                    flags |= KEYEVENTF_KEYUP
                scan = u32.MapVirtualKeyW(self._target_vk, MAPVK_VK_TO_VSC)
                u32.keybd_event(self._target_vk, scan, flags, 0)
            except Exception:
                pass
        return 1

    def _lock_with_map(self):
        self.is_locked = True
        self._mapping_enabled = True
        self._refresh_lock_ui()

    def _lock_only(self):
        self.is_locked = True
        self._mapping_enabled = False
        self._refresh_lock_ui()

    def _unlock(self):
        self.is_locked = False
        self._mapping_enabled = False
        self._refresh_lock_ui()

    def _refresh_lock_ui(self):
        if self.is_locked:
            self._lock_var.set("已锁定")
            self._lock_lbl.config(foreground="red")
            self._btn_map.pack_forget()
            self._btn_only.pack_forget()
            self._btn_unlock.pack(pady=(0, 5))
            self.root.title("游戏 Capslock 锁定映射工具 - [已锁定]")
        else:
            self._lock_var.set("已解锁")
            self._lock_lbl.config(foreground="green")
            self._btn_unlock.pack_forget()
            self._btn_map.pack(pady=(5, 5))
            self._btn_only.pack(pady=(0, 5))
            self.root.title("游戏 Capslock 锁定映射工具")
        self._refresh_map_ui()

    def _capture(self):
        prev = self._mapping_enabled
        self._mapping_enabled = False
        dlg = KeyCaptureDialog(self.root)
        self.root.wait_window(dlg)
        self._mapping_enabled = prev

        if dlg.result_vk is not None:
            self._target_vk = dlg.result_vk
            self._target_name = dlg.result_name
            self._target_extended = dlg.result_extended
            self._refresh_map_ui()
            self._save()

    def _refresh_map_ui(self):
        ext = " [扩展]" if self._target_extended else ""
        self._map_display_var.set(f"CapsLock -> {self._target_name}{ext}")
        if self._mapping_enabled:
            self._map_display_lbl.config(foreground="#0066CC")
        else:
            self._map_display_lbl.config(foreground="gray")

    def _refresh_trigger(self):
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
            self._trigger_var.set(f"{s} (共 {self._trigger_count} 次)")
        self.root.after(500, self._refresh_trigger)

    def _save(self):
        _save_cfg({
            "target_vk": self._target_vk,
            "target_name": self._target_name,
            "target_extended": self._target_extended,
        })

    def _refresh_status(self):
        self._caps_var.set("大写" if _caps_on() else "小写")
        self.root.after(200, self._refresh_status)

    def _get_hwnd(self):
        s = self.root.frame()
        return int(s, 16) if s else None

    def _register_session_notification(self):
        hwnd = self._get_hwnd()
        if not hwnd:
            self.root.after(100, self._register_session_notification)
            return
        ok = wts.WTSRegisterSessionNotification(wintypes.HWND(hwnd), NOTIFY_FOR_THIS_SESSION)
        if not ok:
            err = k32.GetLastError()
            self._screen_var.set("锁屏检测不可用")
            self._screen_lbl.config(foreground="orange")
            return
        self._orig_wndproc = u32.GetWindowLongPtrW(wintypes.HWND(hwnd), GWLP_WNDPROC)
        self._wndproc_ref = WNDPROC(self._session_wndproc)
        addr = ctypes.cast(self._wndproc_ref, ctypes.c_void_p).value
        u32.SetWindowLongPtrW(wintypes.HWND(hwnd), GWLP_WNDPROC, wintypes.LONG_PTR(addr))

    def _unregister_session_notification(self):
        hwnd = self._get_hwnd()
        if not hwnd or not self._wndproc_ref:
            return
        if self._orig_wndproc is not None:
            u32.SetWindowLongPtrW(wintypes.HWND(hwnd), GWLP_WNDPROC, self._orig_wndproc)
        wts.WTSUnRegisterSessionNotification(wintypes.HWND(hwnd))
        self._wndproc_ref = None

    def _session_wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_WTSSESSION_CHANGE:
                if wparam == WTS_SESSION_LOCK:
                    self.root.after(0, self._on_lock)
                elif wparam == WTS_SESSION_UNLOCK:
                    self.root.after(0, self._on_unlock)
        except Exception:
            pass
        if self._orig_wndproc is not None:
            return ctypes.cast(self._orig_wndproc, WNDPROC)(hwnd, msg, wparam, lparam)
        return u32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_lock(self):
        try:
            if self._is_ws_locked:
                return
            self._is_ws_locked = True
            self._prev_lock_state = self.is_locked
            if self.is_locked:
                self.is_locked = False
                self._mapping_enabled = False
            self._screen_var.set("锁屏中")
            self._screen_lbl.config(foreground="orange")
            self.root.title("游戏 Capslock 锁定映射工具 - [锁屏中]")
        except Exception:
            pass

    def _on_unlock(self):
        try:
            if not self._is_ws_locked:
                return
            self._is_ws_locked = False
            if self._prev_lock_state:
                self.is_locked = True
                self._mapping_enabled = True
            self._prev_lock_state = False
            self._screen_var.set("活跃")
            self._screen_lbl.config(foreground="gray")
            self.root.title(
                "游戏 Capslock 锁定映射工具 - [已锁定]" if self.is_locked else "游戏 Capslock 锁定映射工具")
            self.root.after(100, self._refresh_lock_ui)
        except Exception:
            pass

    def _on_close(self):
        if self._hook_id:
            u32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None
        self._unregister_session_notification()
        self.root.destroy()


def main():
    if not _check_single_instance():
        messagebox.showinfo("游戏 Capslock 锁定映射工具", "程序已在运行中。")
        return
    try:
        CapsLockBlocker().root.mainloop()
    except Exception as e:
        messagebox.showerror("错误", f"启动失败:\n{e}")

if __name__ == "__main__":
    main()
