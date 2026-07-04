"""
CapsLock 锁定工具
==================
通过 Windows WH_KEYBOARD_LL 低级键盘钩子拦截 CapsLock 按键。
钩子在主线程（tkinter 消息泵）中运行，无需独立线程。

特性:
- 不需要管理员权限
- 系统级全局拦截
- 简洁的图形界面
- 锁屏自动解除锁定，登录后自动恢复 —— 防止锁屏界面大小写异常

作者: CodeWhale
日期: 2026-06-26
"""

import ctypes
from ctypes import wintypes, WINFUNCTYPE, POINTER, byref, cast
import tkinter as tk
from tkinter import ttk, messagebox
import sys

# ============================================================
# 常量
# ============================================================
WH_KEYBOARD_LL = 13
VK_CAPITAL     = 0x14

# 窗口过程常量
GWLP_WNDPROC = -4

# WTS 会话通知常量
WM_WTSSESSION_CHANGE    = 0x02B1
WTS_SESSION_LOCK        = 0x7
WTS_SESSION_UNLOCK      = 0x8
NOTIFY_FOR_THIS_SESSION = 0

# ============================================================
# 兼容性补丁
# ============================================================
if not hasattr(wintypes, "ULONG_PTR"):
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        wintypes.ULONG_PTR = ctypes.c_ulonglong
    else:
        wintypes.ULONG_PTR = ctypes.c_ulong
if not hasattr(wintypes, "LRESULT"):
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        wintypes.LRESULT = ctypes.c_longlong
    else:
        wintypes.LRESULT = ctypes.c_long
if not hasattr(wintypes, "LONG_PTR"):
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        wintypes.LONG_PTR = ctypes.c_longlong
    else:
        wintypes.LONG_PTR = ctypes.c_long

# ============================================================
# 结构体
# ============================================================
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode",      wintypes.DWORD),
        ("scanCode",    wintypes.DWORD),
        ("flags",       wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", wintypes.ULONG_PTR),
    ]

# ============================================================
# 函数类型
# ============================================================
HOOKPROC = WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
WNDPROC  = WINFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

# ============================================================
# 加载 DLL + 声明签名
# ============================================================
user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
wtsapi32 = ctypes.windll.wtsapi32

# ---- SetWindowsHookExW ----
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]

user32.CallNextHookEx.restype = ctypes.c_long
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]

user32.UnhookWindowsHookEx.restype = wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]

user32.GetKeyState.restype = wintypes.SHORT
user32.GetKeyState.argtypes = [ctypes.c_int]

# ---- GetModuleHandleW ----
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

kernel32.GetLastError.restype = wintypes.DWORD
kernel32.GetLastError.argtypes = []

# ---- 窗口过程相关 ----
user32.GetWindowLongPtrW.restype = wintypes.LONG_PTR
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]

user32.SetWindowLongPtrW.restype = wintypes.LONG_PTR
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG_PTR]

user32.CallWindowProcW.restype = wintypes.LRESULT
user32.CallWindowProcW.argtypes = [WNDPROC, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

user32.DefWindowProcW.restype = wintypes.LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

# ---- WTS 会话通知 ----
wtsapi32.WTSRegisterSessionNotification.restype = wintypes.BOOL
wtsapi32.WTSRegisterSessionNotification.argtypes = [wintypes.HWND, wintypes.DWORD]

wtsapi32.WTSUnRegisterSessionNotification.restype = wintypes.BOOL
wtsapi32.WTSUnRegisterSessionNotification.argtypes = [wintypes.HWND]

# ============================================================
# 辅助
# ============================================================
def _check_single_instance() -> bool:
    """通过 Windows Mutex 检测是否已有实例在运行。
    返回 True 表示当前是唯一实例，False 表示已有实例。
    互斥锁句柄泄漏由操作系统在进程退出时自动回收，无需手动释放。
    """
    mutex_name = "Global\\CapsLockBlocker_SingleInstance_Mutex"
    kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateMutexW(None, False, mutex_name)
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS

def is_caps_on() -> bool:
    """检查当前 CapsLock 状态: True=大写, False=小写。"""
    return (user32.GetKeyState(VK_CAPITAL) & 0x0001) != 0

# ============================================================
# 主类
# ============================================================
class CapsLockBlocker:
    def __init__(self):
        # ---- 状态 ----
        self.is_locked       = False   # 用户是否主动锁定
        self._prev_lock_state = False  # 锁屏前的 is_locked 状态
        self._is_ws_locked   = False   # 工作站是否处于锁屏状态

        # ---- 钩子 ----
        self._hook_id  = None
        self._hook_ref = None

        # ---- 窗口过程子类化 ----
        self._orig_wndproc = None  # 原始窗口过程地址
        self._wndproc_ref  = None  # 新窗口过程引用（防 GC）

        # ---- GUI ----
        self.root = tk.Tk()
        self.root.title("CapsLock 锁定工具")
        self.root.geometry("380x330")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 居中
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

        self._build_ui()
        self._install_hook()
        # 延迟注册会话通知（等窗口 HWND 就绪）
        self.root.after(200, self._register_session_notification)
        self._refresh_status()

    # ================================================================
    # UI
    # ================================================================
    def _build_ui(self):
        f = ttk.Frame(self.root, padding=20)
        f.pack(fill=tk.BOTH, expand=True)

        # 标题
        ttk.Label(f, text="CapsLock 锁定工具",
                  font=("Microsoft YaHei", 14, "bold")).pack(pady=(0, 15))

        # 锁定状态
        self._lock_var = tk.StringVar(value="已解锁")
        self._lock_lbl = ttk.Label(f, textvariable=self._lock_var,
                                   font=("Microsoft YaHei", 12), foreground="green")
        self._lock_lbl.pack(pady=5)

        # CapsLock 状态
        self._caps_var = tk.StringVar(value="检测中...")
        row1 = ttk.Frame(f)
        row1.pack(pady=5)
        ttk.Label(row1, text="CapsLock 状态: ",
                  font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        ttk.Label(row1, textvariable=self._caps_var,
                  font=("Microsoft YaHei", 10, "bold")).pack(side=tk.LEFT)

        # 锁屏状态（新增）
        self._screen_var = tk.StringVar(value="桌面: 活跃")
        row2 = ttk.Frame(f)
        row2.pack(pady=5)
        ttk.Label(row2, text="系统桌面: ",
                  font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self._screen_lbl = ttk.Label(row2, textvariable=self._screen_var,
                                     font=("Microsoft YaHei", 10, "bold"),
                                     foreground="gray")
        self._screen_lbl.pack(side=tk.LEFT)

        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # 锁定按钮
        self._btn = ttk.Button(f, text="锁定 CapsLock", command=self._toggle)
        self._btn.pack(pady=8)

        # 说明文字
        desc = ("锁定后 CapsLock 键完全失效\n"
                "锁屏时自动解除，登录后自动恢复")
        ttk.Label(f, text=desc,
                  font=("Microsoft YaHei", 9), foreground="gray",
                  justify=tk.CENTER).pack(pady=(5, 0))

    # ================================================================
    # 钩子
    # ================================================================
    def _install_hook(self):
        """在主线程安装 WH_KEYBOARD_LL 钩子。

        对 WH_KEYBOARD_LL: 回调在本线程的消息泵中触发，hmod=NULL(0) 即可，
        不需要注入到其他进程。
        """
        self._hook_ref = HOOKPROC(self._hook_callback)

        self._hook_id = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._hook_ref,
            0,  # hmod = NULL — WH_KEYBOARD_LL 不需要注入 DLL
            0,  # dwThreadId = 0 → 全局钩子
        )

        if not self._hook_id:
            err = kernel32.GetLastError()
            self._caps_var.set(f"钩子失败 (err={err})")
            self._lock_var.set("安装失败")
            self._lock_lbl.config(foreground="orange")
            self._btn.config(state="disabled", text="不可用")
            if err == 5:  # ERROR_ACCESS_DENIED
                msg = "权限不足。右键以管理员身份运行即可。"
            elif err == 8:  # ERROR_NOT_ENOUGH_MEMORY
                msg = "系统资源不足，关闭一些程序后重试。"
            else:
                msg = f"错误码 {err}。杀毒软件可能阻止了键盘钩子。"
            messagebox.showwarning("CapsLock 锁定工具", msg)

    def _hook_callback(self, nCode, wParam, lParam):
        """低级键盘钩子回调（主线程调用）。

        当用户主动锁定 且 工作站未锁屏 时拦截 CapsLock。
        工作锁屏时放行，让登录界面正常使用 CapsLock。
        """
        if nCode >= 0 and self.is_locked and not self._is_ws_locked:
            kb = cast(lParam, POINTER(KBDLLHOOKSTRUCT)).contents
            if kb.vkCode == VK_CAPITAL:
                return 1  # 吃掉这个按键
        return user32.CallNextHookEx(
            self._hook_id if self._hook_id else 0, nCode, wParam, lParam)

    # ================================================================
    # 锁定切换
    # ================================================================
    def _toggle(self):
        """用户手动切换锁定状态。"""
        self.is_locked = not self.is_locked
        self._update_lock_ui()
        self.root.title(
            "CapsLock 锁定工具 - [已锁定]" if self.is_locked
            else "CapsLock 锁定工具"
        )

    def _update_lock_ui(self):
        """根据 is_locked 刷新 UI 元素（不改变标题）。"""
        if self.is_locked:
            self._lock_var.set("已锁定")
            self._lock_lbl.config(foreground="red")
            self._btn.config(text="解除锁定")
        else:
            self._lock_var.set("已解锁")
            self._lock_lbl.config(foreground="green")
            self._btn.config(text="锁定 CapsLock")

    # ================================================================
    # 状态刷新
    # ================================================================
    def _refresh_status(self):
        """定时刷新 CapsLock 指示灯状态。"""
        self._caps_var.set("大写 ↑" if is_caps_on() else "小写 ↓")
        self.root.after(200, self._refresh_status)

    # ================================================================
    # 锁屏检测 — WTSRegisterSessionNotification
    # ================================================================
    def _get_hwnd(self):
        """获取 tkinter 窗口的原生 HWND（整数）。"""
        hwnd_str = self.root.frame()
        return int(hwnd_str, 16) if hwnd_str else None

    def _register_session_notification(self):
        """注册 WTS 会话通知，锁屏/解锁时收到 WM_WTSSESSION_CHANGE。"""
        hwnd = self._get_hwnd()
        if not hwnd:
            # HWND 尚未就绪，延迟重试
            self.root.after(100, self._register_session_notification)
            return

        # 第一步：注册会话通知
        ok = wtsapi32.WTSRegisterSessionNotification(
            wintypes.HWND(hwnd), NOTIFY_FOR_THIS_SESSION)
        if not ok:
            err = kernel32.GetLastError()
            self._screen_var.set(f"锁屏检测不可用 (err={err})")
            self._screen_lbl.config(foreground="orange")
            return

        # 第二步：子类化窗口过程以拦截 WM_WTSSESSION_CHANGE
        self._orig_wndproc = user32.GetWindowLongPtrW(
            wintypes.HWND(hwnd), GWLP_WNDPROC)

        self._wndproc_ref = WNDPROC(self._session_wndproc)

        # 显式转换为地址值，避免 ctypes 自动转换的兼容性问题
        proc_addr = ctypes.cast(self._wndproc_ref, ctypes.c_void_p).value
        user32.SetWindowLongPtrW(
            wintypes.HWND(hwnd), GWLP_WNDPROC,
            wintypes.LONG_PTR(proc_addr)
        )

    def _unregister_session_notification(self):
        """还原窗口过程并注销会话通知。"""
        hwnd = self._get_hwnd()
        if not hwnd or not self._wndproc_ref:
            return

        # 先还原窗口过程
        if self._orig_wndproc is not None:
            user32.SetWindowLongPtrW(
                wintypes.HWND(hwnd), GWLP_WNDPROC, self._orig_wndproc)

        # 再注销会话通知
        wtsapi32.WTSUnRegisterSessionNotification(wintypes.HWND(hwnd))
        self._wndproc_ref = None

    def _session_wndproc(self, hwnd, msg, wparam, lparam):
        """自定义窗口过程：拦截 WM_WTSSESSION_CHANGE 消息。

        当收到锁屏/解锁事件时，通过 tkinter 的 after_idle
        安全地调度 UI 更新（避免 Tcl/Tk 重入问题）。
        """
        if msg == WM_WTSSESSION_CHANGE:
            if wparam == WTS_SESSION_LOCK:
                # 锁屏 → 立即解除锁定
                self.root.after(0, self._on_workstation_lock)
            elif wparam == WTS_SESSION_UNLOCK:
                # 解锁 → 立即恢复锁定
                self.root.after(0, self._on_workstation_unlock)

        # 调用原始窗口过程处理其他消息
        if self._orig_wndproc is not None:
            orig = ctypes.cast(self._orig_wndproc, WNDPROC)
            return orig(hwnd, msg, wparam, lparam)
        else:
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_workstation_lock(self):
        """工作站锁屏时调用：保存并解除 CapsLock 锁定。"""
        if self._is_ws_locked:
            return  # 防止重复触发
        self._is_ws_locked = True

        # 保存锁屏前的锁定状态
        self._prev_lock_state = self.is_locked

        # 如果当前是锁定状态，则解除（让锁屏界面正常使用 CapsLock）
        if self.is_locked:
            self.is_locked = False
            self._update_lock_ui()

        # 更新 UI 锁屏指示
        self._screen_var.set("桌面: 锁屏中")
        self._screen_lbl.config(foreground="orange")
        self.root.title("CapsLock 锁定工具 - [锁屏中]")

    def _on_workstation_unlock(self):
        """工作站解锁时调用：恢复之前的锁定状态。"""
        if not self._is_ws_locked:
            return  # 防止重复触发
        self._is_ws_locked = False

        # 恢复锁屏前的锁定状态
        if self._prev_lock_state:
            self.is_locked = True
        self._prev_lock_state = False

        self._update_lock_ui()

        # 更新 UI 锁屏指示
        self._screen_var.set("桌面: 活跃")
        self._screen_lbl.config(foreground="gray")
        self.root.title(
            "CapsLock 锁定工具 - [已锁定]" if self.is_locked
            else "CapsLock 锁定工具"
        )

    # ================================================================
    # 退出
    # ================================================================
    def _on_close(self):
        """安全退出：先卸钩、还原窗口过程，再销毁窗口。"""
        # 1. 卸掉键盘钩子
        if self._hook_id:
            user32.UnhookWindowsHookEx(self._hook_id)
            self._hook_id = None

        # 2. 还原窗口过程 + 注销会话通知
        self._unregister_session_notification()

        # 3. 销毁窗口
        self.root.destroy()

# ============================================================
# 入口
# ============================================================
def main():
    # 单实例检测：如果已有实例在运行，弹出提示后退出
    if not _check_single_instance():
        messagebox.showinfo("CapsLock 锁定工具", "程序已在运行中。\n请查看系统托盘或任务栏。")
        return

    try:
        CapsLockBlocker().root.mainloop()
    except Exception as e:
        messagebox.showerror("错误", f"启动失败:\n{e}")

if __name__ == "__main__":
    main()
