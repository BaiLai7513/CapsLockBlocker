# GameCapslockMapper v1.2.6 正式版

发布日期：2026-11-19

Windows 下的 CapsLock 锁定映射工具：先锁定 CapsLock，再按需启用映射。默认“切换锁定”：按一次 CapsLock 让目标键保持按下，再按一次释放；也可以选择“按住触发”。

## 核心行为

- 未锁定时：CapsLock 保持系统原生功能。
- 点击顶部“锁定 CapsLock”：CapsLock 被完全拦截，默认不映射。
- 锁定后才能捕获目标键、勾选“锁定期间启用映射”。
- 映射方式：
  - 切换锁定（默认）：按一次 CapsLock 保持目标键按下，再按一次释放；参考 QKeyMapper 的 Lock 状态机思路。
  - 按住触发：按住 CapsLock 时目标键按下，松开释放。
- 取消映射：释放目标键，但保持 CapsLock 锁定。
- 解除锁定、锁屏或关闭程序：释放目标键并恢复 CapsLock 原生功能。
- 锁屏解锁后保持原生，不自动重新锁定。

## 主要修复

- 重写输入状态机：CapsLock 按下/抬起完全拦截，锁定状态独立于物理按键状态。
- 过滤 LLKHF_INJECTED，避免 SendInput 模拟事件再次进入状态机。
- 忽略 CapsLock 自动重复，避免长按反复切换。
- 锁定、解锁、锁屏、取消映射、切换方式、退出时都会成对发送目标键 KEYUP。
- 使用 SendInput + 扫描码发送目标键。
- 锁屏检测使用独立 WTS 消息窗口线程 + OpenInputDesktop 轮询兜底，不再替换 Tk 窗口过程。
- 运行权限检测；run_source.bat 自动请求管理员权限。
- 打包改为 onedir 文件夹，避免单文件自解压临时目录失败。
- 窗口加宽到 540、最大高度 760，隐藏右侧滚动条；锁定按钮固定在顶部，映射方式文字完整显示，常规屏幕一屏展示全部内容。
- 修复原 _clean.bat 误删用户 Pictures 目录的危险逻辑；现在只清理构建产物。

## 运行要求

- Windows 10/11（代码兼容 Windows 7+ 的 API）。
- 运行版已自带 Python 和 Tcl/Tk，无需安装 Python。
- EXE 会请求管理员权限；如果游戏以管理员运行，本工具也必须以管理员启动。
- 必须保留整个 GameCapslockMapper 文件夹（含 _internal），不能只复制 exe。

## 包内容

运行版：

- GameCapslockMapper/GameCapslockMapper.exe
- GameCapslockMapper/_internal/...

源码版：

- caps_lock_blocker.py
- README.md
- LICENSE
- VERSION
- RELEASE_NOTES.md
- build_exe.bat
- run_source.bat
- 游戏Capslock锁定映射工具.spec
- app.manifest
- test_capslock_mapper.py
- _clean.bat
- .gitignore

## 验证

- 6 个单元测试通过。
- 源码 --self-test、--smoke-test 通过。
- 打包后的 EXE --self-test、--smoke-test 通过。
- 布局测量：窗口 540×760，锁定按钮顶部可见，映射方式两个选项完整显示，内容 529px 小于可视区。
- 校验值见 dist/SHA256SUMS.txt。

## 已知限制

- 当前只支持单键映射，不支持组合键。
- 部分使用内核级反作弊或特殊 Raw Input 通道的游戏可能忽略模拟输入。
- 程序被任务管理器强杀时无法发送 KEYUP；正常关闭、解锁、锁屏会清理。
- 安全软件可能对全局键盘钩子误报，请将整个文件夹加入信任区。
