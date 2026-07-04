# 游戏 Capslock 锁定映射工具

[![Release](https://img.shields.io/badge/release-v1.0-blue)](../../releases)

解决游戏时误触 CapsLock 导致操作失误的痛点。CapsLock 位置顺手却被大多数游戏闲置甚至误触翻车，这个工具将其锁定，并可映射为任意字母或数字键，方便操作。

## 功能

- **锁定即映射**：点击锁定后 CapsLock 原功能被拦截，自动映射为自定义字母/数字键
- **捕获目标按键**：点击捕获按钮，按下目标字母或数字键自动识别并设置映射
- **解锁即恢复**：解除锁定后 CapsLock 恢复正常功能
- **锁屏自动解除**：Win+L 锁屏时自动解除，登录界面不受影响，解锁后自动恢复
- **配置自动保存**：映射目标保存到 `%APPDATA%\CapsLockBlocker\config.json`
- **系统级拦截**：基于 Windows WH_KEYBOARD_LL 低级键盘钩子，无需管理员权限

## 使用场景

| 场景 | 映射目标 | 效果 |
|------|---------|------|
| FPS 游戏 | 映射为 R（换弹） | CapsLock 位置比 R 更顺手 |
| MOBA 游戏 | 映射为数字键 1-6（技能/物品） | 小指按 CapsLock 释放技能 |
| 任意游戏 | 锁定不吃掉 | 彻底杜绝误触 |

## 使用方法

1. 双击 `游戏Capslock锁定映射工具.exe`
2. 点击 `[ 捕获目标按键 ]`，按下要映射的字母或数字键
3. 点击 `[ 锁定并启用映射 ]`
4. 此时按 CapsLock 即触发你设置的按键
5. 点击 `[ 解除锁定 ]` 恢复 CapsLock 原功能

## 技术原理

Windows API `SetWindowsHookEx(WH_KEYBOARD_LL)` 全局低级键盘钩子拦截 VK_CAPITAL (0x14)，通过 `keybd_event` + `MapVirtualKeyW` 模拟目标按键的按下/释放。

锁屏检测通过 `WTSRegisterSessionNotification` 会话通知，锁屏时自动解除，解锁后恢复。

## 注意事项

- 部分杀毒软件可能将键盘钩子识别为可疑行为，请添加白名单
- 如钩子安装失败，尝试以管理员身份运行
- 仅支持字母键 (A-Z) 和数字键 (0-9) 作为映射目标

## 许可

MIT License
