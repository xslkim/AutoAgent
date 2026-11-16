# GunForge3D 本机开发环境

探测日期：2026-11-16（Asia/Shanghai）。供后续执行工程师使用；机器配置、磁盘余量和连接设备会变化，开工时重新检查。本文记录实际探测结果，不代表游戏、美术工具链或目标设备已经验收。

## 1. 项目当前状态

- 仓库：`E:\tvgun`；本工程：`E:\tvgun\gunforge3d`；探测时分支为 `main`。
- 本次检查时 `gunforge3d/` 只有 docs 文档，尚无 `game/project.godot`、`run.ps1`、测试框架、关卡 JSON 或 artkit。不能直接运行文档中的游戏测试命令，应先执行 TASKS T00。
- 白模工作以 [PLAN.md](PLAN.md)、[TASKS.md](TASKS.md) 为准。后续美术以 [ART3D_FRAMEWORK.md](ART3D_FRAMEWORK.md)、[ART3D_PLAN_WAREHOUSE_RAID.md](ART3D_PLAN_WAREHOUSE_RAID.md) 为准；AF/EI/WR 目前只有任务大纲，尚无详细执行任务。
- 脚本应基于 `$PSScriptRoot` 定位，不把本机盘符写进业务代码。修改范围、提交规则按 TASKS 执行；不要混入其他工程的改动。

## 2. 已探测硬件与系统

| 项目 | 实测值 |
|---|---|
| 系统 | Windows 11 专业版，64位，10.0.26200 |
| CPU | Intel Core Ultra 7 265K |
| 内存 | 可报告物理内存约63.4 GiB |
| GPU | NVIDIA GeForce RTX 5090 |
| 显存 | nvidia-smi报告32607 MiB |
| NVIDIA驱动 | 610.88 |
| 默认执行Shell | PowerShell 7.6.9 Core |
| C盘空闲 | 约680.4 GiB |
| D盘空闲 | 约144.3 GiB |
| E盘空闲 | 约411.7 GiB |

显卡可用和显存充足不能证明某个生成模型或GPU烘焙后端兼容。大型权重下载前检查D盘空间；将原始生成物和中间缓存放仓库外，例如 `D:\gunforge_cache\art3d`，不要把模型权重提交到Git。

## 3. 工具路径与验证程度

| 工具 | 版本与路径 | 本次验证 |
|---|---|---|
| Godot | `4.6.3.stable.official.7d41c59c4`；`D:\gunforge_cache\tools\godot-4.6.3\Godot_v4.6.3-stable_win64_console.exe` | 版本命令成功；临时SceneTree脚本在headless模式执行Vector3计算，退出0 |
| Blender | `4.2.16 LTS`，构建hash `39502cae951c`；`C:\Program Files\Blender Foundation\Blender 4.2\blender.exe` | background/factory-startup成功；Cycles枚举出RTX 5090 CUDA与OPTIX、CPU及Intel ONEAPI设备 |
| Python | `3.12.10`；`C:\Users\xsl\AppData\Local\Programs\Python\Python312\python.exe` | 版本及标准库脚本运行成功 |
| uv | `0.12.4`；`C:\Users\xsl\.local\bin\uv.exe` | 版本命令成功，尚未创建artkit环境 |
| Git | `2.50.0.windows.2`；`C:\Program Files\Git\cmd\git.exe` | 版本、分支和工作树检查成功 |
| nvidia-smi | `C:\Windows\System32\nvidia-smi.exe` | GPU/显存/驱动查询成功 |
| ADB | `1.0.41`，platform-tools `36.0.0-13206524`；`C:\Users\xsl\AppData\Local\Android\Sdk\platform-tools\adb.exe` | 版本成功；devices列表为空；查询启动了本地5037端口ADB守护进程 |

Godot、Blender不在本次Shell的PATH中，但上述绝对路径可用；`GODOT_BIN`当前未设置。不要因此重新安装。Blender启动有一条TBBmalloc提示，但正常退出；本次只验证了设备枚举，未进行实际Cycles GPU渲染、顶点色烘焙或GLB导出，不能把设备列出记为GPU渲染通过。

## 4. WSL与生成模型

已登记三个WSL2发行版：`Ubuntu-22.04`（默认）、`wsl_hair`、`ubuntu22`，探测时均停止。本次未启动或修改发行版，没有验证Linux Python、CUDA透传、模型依赖或权重。

AF06开工时先检查所选模型官方版本要求，再在专用环境安装并锁定依赖，不复用或修改其他工程的Python/WSL环境。Windows系统Python、Blender内置Python和WSL Python是不同解释器，依赖分别管理。不要因RTX 5090存在就认定旧PyTorch/CUDA扩展能运行。

本次没有检查账号凭据、付费服务额度、生成模型安装目录或权重。它们均为“待核验”，不是“不可用”。环境报告只记录服务是否配置/调用是否验证，不保存密钥值。模型许可、服务价格和显存需求由AF06核验，不能引用方案中的候选名称作为已安装证明。

## 5. 可立即执行的工具自检

以下命令在PowerShell运行；均不依赖尚未创建的game目录：

```powershell
Set-Location 'E:\tvgun'
$GodotExe = 'D:\gunforge_cache\tools\godot-4.6.3\Godot_v4.6.3-stable_win64_console.exe'
$BlenderExe = 'C:\Program Files\Blender Foundation\Blender 4.2\blender.exe'
& $GodotExe --version
& $BlenderExe --background --factory-startup --python-expr "import bpy; print(bpy.app.version_string)"
python --version
uv --version
git status --short
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
wsl --list --verbose
adb devices
```

PowerShell调用带空格的可执行路径必须使用 `&`。Godot引擎参数放在 `--` 之前，游戏参数放在之后；不要把 `--rendering-method` 作为游戏用户参数传入。

上表记录的是PowerShell 7。`.cmd` 文件里的 `powershell` 命令启动的是系统自带的Windows PowerShell，本次没有探测它的版本和行为；对脚本的兼容要求见TASKS T00。

## 6. 工程创建后的运行方式

**以下命令现在不能运行；需T00及相应任务完成。**

```powershell
Set-Location 'E:\tvgun'
$GodotExe = 'D:\gunforge_cache\tools\godot-4.6.3\Godot_v4.6.3-stable_win64_console.exe'
& $GodotExe --headless --path 'gunforge3d/game' --import
& $GodotExe --headless --path 'gunforge3d/game' --script 'res://tests/run_all.gd'
# 窗口启动，关卡文件需T18/T19创建
& $GodotExe --path 'gunforge3d/game' -- --level=res://data/levels/warehouse_raid.json
# EI06接入后验证Compatibility；这里传入的是引擎参数
& $GodotExe --path 'gunforge3d/game' --rendering-method gl_compatibility -- --art=on
```

每次运行检查 `$LASTEXITCODE`。如果指定 `--rendering-method gl_compatibility` 后Godot报渲染驱动不匹配，再加上引擎参数 `--rendering-driver opengl3`；这一点本次没有实测。无头模式用于逻辑测试，截图、最终限亮、材质和帧率必须用真实窗口渲染；本次没有验证Forward+或Compatibility画面。Compatibility与Godot的Mobile渲染器是不同方法，切换时需重新验收材质和环境，参见[Godot渲染器说明](https://docs.godotengine.org/en/4.6/tutorials/rendering/renderers.html)。

交互游戏可失焦暂停；自动脚本/回放按TASKS禁用失焦暂停。普通窗口自动检查建议120秒超时，整关回放600秒，结束只清理自己启动的进程。性能采集与截图/图像回读分开运行。开发TCP默认19020、测试19021；本次未验证端口空闲。

## 7. 美术工具链实施前的最小验证

1. AF00为artkit建立项目独立环境和锁文件，固定外部Python、Blender和Godot版本；白模T00–T20不需要额外Python依赖。
2. 用微型场景实际运行Cycles CPU烘焙，再验证选定GPU后端。设备枚举通过不替代此项；失败时保留日志，可先用CPU处理小样，不宣称GPU已可用。
3. 导出含灰色和彩色顶点色的GLB，读回COLOR_0并在Godot渲染；检查线性/sRGB转换、尺寸、轴向、部件中心以及材质。
4. 验证Compatibility的基础材质、限亮与白框，再用该渲染器做B1可读性验收；安卓帧率仍需真实设备。
5. 本次ADB列表为空，Android SDK完整性、Godot安卓导出模板、签名和部署都未验证。当前白模不要求安卓导出，不能把缺少真机解释为白模任务阻塞。

## 8. 交接记录要求

工程师在PROGRESS或art报告中记录命令、退出码、工具版本、测试范围及未解决问题。不要将“路径存在”“设备被枚举”“结构检查通过”合并成“整套环境通过”。升级工具或更换模型后记录新版本，并重跑对应回归；文档中未实施的命令、接口和目录仍是待交付内容。
