# GunForge 首站运行框架

在仓库根目录双击 play_paper_lantern.cmd，或执行 ./gunforge/start_game.ps1。-Gun 直接进入光枪输入模式，-Test 运行核心回归。

启动器先校验已审核素材哈希，用 Pillow 构建 runtime/，再导入 Godot 资源并启动游戏。Godot 使用已验证的 4.6.3 console 程序，可通过 GODOT_BIN 或 -Godot 指定。本机工具保存在仓库相邻的 gunforge_cache/tools/godot-4.6.3/。生成的运行包与 .godot/ 不入库。

Enter 开始，鼠标左键射击，右键或 R 换弹，屏幕外扣扳机也换弹。5 投币续关，Esc 暂停，F11 全屏，G 切换鼠标与光枪，F2 打开显示设置，F3 切换显示器/电视，C 开始校准。校准有 5 个拟合点和 4 个独立检查点，误差需小于 10 规范像素。设置按显示配置保存。

core/ 提供坐标、协议、像素命中、骨架播放、校准和声音。runtime/game_rules.gd 与 game_scene.gd 从当前游戏的 games/g01/scripts/ 构建，关卡来自 games/g01/levels/。游戏角色保持 NPC/人质身份。

## 自动操作

开发构建监听本机 TCP 19010，每行一个 JSON 请求，每行一个 JSON 回应。支持 state、freeze、step、input、mode、profile、capture 和 quit。先冻结再按固定步长推进，输入通过与正常玩法相同的事件入口。gunforge/pipeline/qa_0b.py 使用该接口跑三轮、截图并验证死亡续关。以 -- --fixed 启动可直接进入冻结模式。

光枪 UDP 9000，发现 UDP 8001，兼容旧格式 x,y / SHOT 和带序号新格式。新手机发送独立 HELLO 会话标识，游戏向同一 UDP 端点回发 FRAME。开发 API 只监听 loopback。

结果在 games/g01/reports/0B/，真实显示器/电视测试按根目录 WORKFLOW.md 核对手机版本与录制数据。
