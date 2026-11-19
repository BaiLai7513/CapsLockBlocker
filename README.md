# 游戏 Capslock 锁定映射工具

版本：v1.2.6

## 正式发布文件

- 运行版：dist\GameCapslockMapper-v1.2.6.zip
- 源码版：dist\GameCapslockMapper-v1.2.6-source.zip
- 校验文件：dist\SHA256SUMS.txt
- 发布说明：RELEASE_NOTES.md

解决游戏时误触 CapsLock 导致操作失误的痛点：锁定后 CapsLock 不再切换大小写，可以映射为任意单键；解锁或锁屏后恢复 CapsLock 原生功能。

## 核心行为（先锁定，再选映射）

1. 未锁定时：CapsLock 保持系统原生功能。
2. 点击“锁定 CapsLock”：CapsLock 被完全拦截，此时默认不映射。
3. 锁定后：才能捕获目标键、勾选“锁定期间启用映射”，并选择映射方式：
   - **切换锁定（默认）**：按一次 CapsLock 让目标键保持按下，再按一次释放（类似 QKeyMapper 的 Lock）。
   - **按住触发**：按住 CapsLock 时目标键按下，松开 CapsLock 释放。
4. 取消“启用映射”：立即释放目标键并解除映射，但仍保持 CapsLock 锁定。
5. 点击“解除锁定”：解除映射并恢复 CapsLock 原生功能。
6. 锁屏或关闭程序：立即解除映射和锁定，恢复 CapsLock 原生。锁屏解锁后保持原生，不自动重新锁定；需要的话再点一次“锁定 CapsLock”。

## 功能

- 任意单键映射：字母、数字、F1-F24、方向键、Insert/Delete/Home/End/PgUp/PgDn、小键盘、Ctrl/Shift/Alt、媒体键等。
- 捕获目标按键：点击捕获按钮后按下目标键即可识别并保存。
- 使用 SendInput + 扫描码发送目标按键，比旧版 keybd_event 更接近真实键盘，兼容性更好。
- 使用独立消息窗口线程接收 WTS 会话通知，替代直接替换 Tk 窗口过程，修复锁屏时可能崩溃的问题。
- WTS 注册失败时自动降级为 OpenInputDesktop 桌面轮询；主线程还有一层兜底轮询。
- 锁定与映射解耦：先锁定 CapsLock，锁定后才能按需启用映射。
- 两种映射状态机：切换锁定（按一下保持、再按释放）和按住触发。
- 过滤 LLKHF_INJECTED 注入事件，避免 SendInput 再次触发自己的状态机。
- 忽略 CapsLock 自动重复；解除映射、解除锁定、锁屏、退出时成对发送目标键 KEYUP，避免按键卡住。
- 锁屏/关闭程序后恢复 CapsLock 原生，锁屏解锁后不会自动重新锁定。
- 配置自动保存到 %APPDATA%\CapsLockBlocker\config.json。
- 单实例检测，防止重复启动多个窗口。

## 使用方法

1. 双击 dist\GameCapslockMapper\GameCapslockMapper.exe；或双击 run_source.bat 从源码运行。
2. 点击窗口顶部固定的“锁定 CapsLock”按钮。此时 CapsLock 被拦截，但默认不映射。窗口已加宽到 540、最大高度 760，右侧滚动条隐藏；常规屏幕一屏即可看到全部设置，锁定按钮始终可见。
3. 锁定后点击“捕获目标按键”，按下要映射的键（例如 R、1、F、Ctrl）。
4. 勾选“锁定期间启用映射”，选择“切换锁定”或“按住触发”。
   - 切换锁定：按一次 CapsLock，目标键保持按下；再按一次 CapsLock，目标键释放。
   - 按住触发：按住 CapsLock 时目标键按下，松开即释放。
5. 取消勾选=立即释放目标键并解除映射但仍锁定；点击“解除锁定”=解除映射并恢复 CapsLock 原生。锁屏或关闭程序也会自动恢复原生。

## 映射目标说明

支持：

- A-Z、0-9
- F1-F24
- 方向键、Insert、Delete、Home、End、PgUp、PgDn
- 小键盘数字和运算符
- Ctrl、Shift、Alt 等修饰键（适合按住 CapsLock 当语音按键）
- 音量/媒体键等常见按键

不支持：

- CapsLock 自身（防止递归）
- Win 键（避免误触开始菜单）
- 鼠标按键
- 组合键（例如 Ctrl+C）暂未支持；当前只支持单个按键

## 锁屏处理

锁屏检测使用两种方式：

1. 主方式：独立线程创建隐藏窗口，通过 WTSRegisterSessionNotification 接收 WM_WTSSESSION_CHANGE。
2. 备用方式：如果 WTS 注册失败，使用 OpenInputDesktop 轮询输入桌面；Tk 主线程还有兜底轮询。

锁屏时立即解除映射并解除锁定，恢复 CapsLock 原生；解锁后保持原生，不自动恢复锁定（需要重新点击锁定）。该实现不再替换 Tk 主窗口的 WNDPROC，避免锁屏消息回调导致程序崩溃。

## 从源码运行

要求 Windows 10/11（代码兼容 Windows 7+ 的 API），Python 3.8+，自带 tkinter。

    run_source.bat

run_source.bat 会检查权限并自动请求管理员授权。如果直接运行 py -3 caps_lock_blocker.py，则需要在管理员终端中启动，否则前台是管理员游戏时映射会失效。

自检（不显示窗口，不发真实按键）：

    py -3 caps_lock_blocker.py --self-test

## 打包 EXE

双击 build_exe.bat。脚本会：

1. 优先查找 venv/.venv，再依次探测 py -3.11 到 3.14、py -3 和 python，并优先选择已经安装 PyInstaller 的解释器。
2. 检查 tkinter。
3. 缺少 PyInstaller 时自动安装（失败时会给出手动安装命令）。
4. 使用 游戏Capslock锁定映射工具.spec 打包，输出 dist\GameCapslockMapper\GameCapslockMapper.exe（整个文件夹一起使用）。

清理构建产物：

    _clean.bat

只删除 build、dist、__pycache__，不会删除任何用户文件。

重要：v1.2.1 起改为文件夹发布（onedir）。必须保留整个 GameCapslockMapper 文件夹（含 _internal），不能只拷贝 exe。单文件模式启动时要先把自身解压到 %TEMP%，部分安全软件会拦截并提示 Could not create temporary directory。

## 运行权限

- EXE 的 app.manifest 请求管理员权限，启动时会弹 UAC；这是为了保证对以管理员运行的游戏也能拦截和注入。
- run_source.bat 会自动请求管理员权限；直接运行 py -3 caps_lock_blocker.py 则不会。
- 普通权限下只对普通权限的游戏/窗口有效；如果你的游戏以管理员身份运行，必须用管理员身份启动本工具，否则 Windows UIPI 会拦截键盘钩子和按键注入，表现为“切到游戏窗口后映射无效”。
- 界面“运行权限”会显示当前是管理员还是普通权限。
- 少数游戏使用内核级反作弊或特殊输入通道，可能忽略 SendInput 模拟按键；这不是本工具能绕过的限制。

## 切换窗口后映射无效

如果本应用窗口在最上层时正常，切到游戏/其他窗口后映射无效，优先检查：

1. 确认已经点击“锁定 CapsLock”，并勾选“锁定期间启用映射”；界面“映射模式”应显示“已锁定并映射”。
2. 本应用是否以管理员权限运行（看界面“运行权限”）。
3. 游戏/目标窗口是否以管理员权限运行；两者权限不一致时，Windows 会阻止向高权限窗口发送模拟按键。
4. 将下面的诊断信息发回：界面“触发指示”次数是否增加、目标程序名、是否管理员、是否全屏独占。

## 安全软件提示

本工具会安装全局键盘钩子，容易被安全软件误报。若 360、Windows Defender 等拦截：

1. 在安全软件的恢复区恢复被隔离的 GameCapslockMapper.exe。
2. 把整个 GameCapslockMapper 文件夹加入信任区/白名单。
3. 仍然无法运行时，双击 run_source.bat 直接用 Python 运行源码；它不需要 PyInstaller 临时目录。

## 配置

配置文件：

    %APPDATA%\CapsLockBlocker\config.json

保存目标按键的虚拟键码、名称和扩展键标记。删除该文件可恢复默认 Esc。

## 已知限制

- 仅支持单键，不支持组合键。
- 不安装驱动、不修改注册表、不注入游戏进程。
- 杀毒软件可能对全局键盘钩子报毒，请添加白名单。
- 极少数游戏使用 Raw Input/DirectInput 或反作弊保护，模拟输入可能无效。

## v1.2.6 更新

- 窗口宽度 460→540，最大高度 760；隐藏右侧滚动条，常规屏幕一屏完整显示所有内容。
- 映射方式两个选项完整显示，不再出现文字被遮挡。
- 锁定/解锁按钮继续固定在顶部；极端小屏保留鼠标滚轮兜底。

## v1.2.5 更新

- 锁定/解锁按钮固定在窗口顶部，详情区改为可滚动，修复小屏、高 DPI 缩放下按钮被遮挡或看不见的问题。
- 窗口高度按屏幕可用高度自适应，不再固定 720 像素。
- 状态、映射方式、目标键说明仍在滚动区，功能不受影响。

## v1.2.4 更新

- 重写映射状态机，新增默认的“切换锁定”模式：按一次 CapsLock 保持目标键按下，再按一次释放。
- 保留“按住触发”模式：按住 CapsLock 时触发，松开释放。
- 钩子过滤 LLKHF_INJECTED 注入事件，避免自己发送的目标键事件再次进入状态机。
- 忽略 CapsLock 自动重复，避免长按 CapsLock 时反复切换。
- 锁定、解锁、锁屏、关闭程序时都强制发送目标键 KEYUP，并重置物理按键状态。
- 代码逻辑参考 QKeyMapper / keyboard_remapper 的 Lock 状态机思路；仍使用 Python + ctypes，便于现有打包。

## v1.2.3 更新

- 锁定与映射解耦：先点击“锁定 CapsLock”，锁定后才能捕获目标键、勾选“锁定期间启用映射”。
- 取消映射不会解除锁定；解除锁定才恢复 CapsLock 原生功能。
- 锁屏直接解除映射并解除锁定，解锁后保持 CapsLock 原生，不再自动重新锁定。
- 关闭程序时钩子移除，CapsLock 恢复原生。

## v1.2.2 更新

- 增加运行权限检测，界面显示当前是否为管理员。
- run_source.bat 自动请求管理员权限，修复“源码运行普通权限 + 管理员游戏”导致切窗口后映射失效的问题。
- 新增权限不一致和切换窗口无效的排查说明。

## v1.2.1 更新

- 改为文件夹发布（onedir），不再解压到 %TEMP%，修复部分系统提示 Could not create temporary directory 的问题。
- 关闭 UPX 压缩，可执行文件改为 ASCII 名称 GameCapslockMapper.exe，降低误报概率。
- 新增 run_source.bat，作为安全软件拦截时的源码运行入口。
- 注意：必须保留整个 GameCapslockMapper 文件夹。

## v1.2 更新

- 映射目标从字母/数字扩展到任意单键。
- 使用 SendInput + 扫描码注入，改进游戏兼容性。
- 重写锁屏检测：独立 WTS 消息窗口线程 + 桌面轮询兜底，修复锁屏崩溃/失效。
- 修复解锁后“仅锁定”状态被错误恢复为“锁定并映射”。
- 修复锁屏/解锁时界面按钮和状态不刷新。
- 修复钩子回调异常可能吞键、退出时目标键可能卡住、单实例检测不稳定。
- 修复打包 spec 中写死的 C:\Users\Administrator 路径。
- 替换原 _clean.bat 中误删用户 Pictures 目录的危险逻辑，改为只清理构建产物。

## 许可

MIT License

原作者：CodeWhale
