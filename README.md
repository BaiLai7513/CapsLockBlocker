# CapsLock 锁定工具

一个轻量级的 Windows 工具，用于锁定 CapsLock 键，使其无法切换大小写。

## 功能

- **锁定 CapsLock**：按下 CapsLock 键完全无效，无法切换大小写状态
- **解锁 CapsLock**：通过界面按钮一键解除，恢复正常功能
- **锁屏自动解除**：锁屏（Win+L）时自动解除锁定，确保登录界面 CapsLock 正常工作
- **解锁后自动恢复**：解锁回到桌面后，自动恢复到之前的锁定状态
- **实时状态显示**：界面实时显示 CapsLock 开关状态、锁定状态、锁屏状态
- **不需要管理员权限**：基于 Windows 低级键盘钩子（WH_KEYBOARD_LL）实现
- **极低资源占用**：后台 CPU 占用近乎为零

## 使用方法

### 直接运行（需要 Python）

```bash
python caps_lock_blocker.py
```

### 打包为 EXE（推荐）

双击运行 `build_exe.bat`，打包后的 EXE 位于 `dist/CapsLock锁定工具.exe`。

打包要求：
- Python 3.6+
- 网络连接（首次会自动安装 PyInstaller）

### 开机自启

将 `CapsLock锁定工具.exe` 的快捷方式放入：
`C:\Users\你的用户名\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`

## 技术原理

### CapsLock 锁定

使用 Windows API `SetWindowsHookEx(WH_KEYBOARD_LL)` 设置全局低级键盘钩子，
在锁定状态下拦截 VK_CAPITAL (0x14) 按键事件并阻止其传递到系统。

- 钩子运行在主线程中，通过 tkinter 消息泵驱动
- 基于 `ctypes` 纯 Python 实现，无需第三方依赖
- GUI 使用 tkinter（Python 标准库）

### 锁屏检测

通过 `WTSRegisterSessionNotification` API 注册会话通知，
在收到 `WTS_SESSION_LOCK`（锁屏）和 `WTS_SESSION_UNLOCK`（解锁）
事件时自动切换锁定状态：

1. **锁屏时**：保存当前锁定状态 → 解除锁定（让登录界面正常使用 CapsLock）
2. **解锁时**：恢复之前的锁定状态

> 注：Windows 锁屏界面运行在安全桌面（Secure Desktop）上，
> 与普通应用程序的默认桌面隔离。理论上 WH_KEYBOARD_LL 钩子不会影响锁屏界面，
> 但自动解除锁定是一个防御性设计，确保在任何情况下都不会干扰登录操作。

## 注意事项

- 部分杀毒软件可能将键盘钩子识别为可疑行为，请添加白名单
- 如果钩子启动失败，尝试以管理员身份运行
- 锁定期间 CapsLock 键的 LED 指示灯可能仍会变化（取决于键盘硬件），但系统不会切换大小写
- 锁屏检测依赖 WTS（Windows Terminal Services）API，在极少数精简版 Windows 上可能不可用

## 许可

MIT License
