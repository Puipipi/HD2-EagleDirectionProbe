# 飞鹰来袭方向探针 / Eagle Direction Probe

**状态：只读测量工具。已在实机跑过多次；`0.2.0` 与 `0.3.0` 两次导致游戏终止，`0.6.0` 已实机验证可正常
加载、游戏进入并持续读到数据（未跑任务、未做实机测量）。不要使用 0.2.0/0.3.0——两者的载荷都已从
工作区和模组管理器里替换掉。**

## 事故记录：两次终止，两个不同的根因（2026-10-07）

两次都是我的错，而且两次的原因**不一样**——这一点值得写清楚，因为第一轮修复只治了其中一个。

### 第一次：`0.2.0` → `0xC0000409 STATUS_STACK_BUFFER_OVERRUN`（`__fastfail`）

| | |
| --- | --- |
| 现场 | 转储 `helldivers2.exe.32240.dmp`；加载器日志确认本 addon 已加载 |
| 触发场景 | **在装配界面选择飞鹰战备时**（不在任务里、不在呼叫中） |
| 真实机制 | 飞船上有一个**完全静止**的同资源物件（268 个样本里只移动了 **1.5 mm**），探针仅凭「存在信标资源」就把它当成一次呼叫，于是**在菜单里连续 29 秒每帧采样** |
| 致命缺陷 | 全程**没有 `sr.Script.temp_byte_count` 存取**。工作区已跑通的覆盖模组把「存/取 temp 字节数」当**每帧纪律**（顶层 `protected()` 包住整个 tick，逐单位读包围盒时也成对调用）。脚本临时内存区不自动重置，只分配不还原就会累积，最终溢出 → fail-fast |
| **不是**的原因 | **不是查询太慢。** 0.6.0 逐键实测：`units_by_resource` 每次 **0.00 ms**，整帧开销低于 `os.clock()` 的 15.6 ms 分辨率。我一开始怀疑「每帧 11 次查询太贵」，实测推翻了它 |

### 第二次：`0.3.0` → 同样的 `0xC0000409`，但死在**启动时**

| | |
| --- | --- |
| 现场 | 加载器日志**最后一行**是 `mods/codex/eagle_direction_probe: loading`，**没有对应的 `: loaded`**，该次会话也没有 `Startup finished` |
| 根因 | 我**凭空猜了一个 API 签名**：写了 `pcall(gs.in_session)`。工作区里**每一个**已跑通模组写的都是 `in_session(session)`，且先用 `sr.Network.game_session()` 拿到 session 并判空。缺参数进原生绑定 → 原生层空引用 → fail-fast |
| 教训 | `pcall` **挡不住原生崩溃**，它只挡 Lua 错误。猜签名在这里是致命操作 |

## `0.6.0` 的修复（每条都有测试兜着）

| 缺陷 | 修复 |
| --- | --- |
| 菜单误采（把静止物件当呼叫） | **移动判据**：信标单位必须移动超过 `BEACON_MOVE_M`（0.75 m）才算一次投掷；表以**单位句柄**为键（身份串是资源哈希，被所有信标共用，以它为键会让一次真实投掷永久污染后续）。静止物件会被点名忽略 |
| 没有 temp 纪律 | 每帧都在 `temp_guard_begin`/`temp_guard_end` 守卫内，并**计时**，`temp_bytes` 写进状态行 |
| 每帧查询风暴 | 每帧只查 **2 个**身份（飞机 + 信标）；弹种识别改为**每次呼叫一次**、带 20 ms 预算、**逐键记录耗时** |
| 猜 API 签名 | `in_session(session)`，session 取自 `Network.game_session()`，写法照抄已跑通模组 |
| 启动期触碰引擎 | `STARTUP_GRACE_S`（20 s）内一次引擎调用都不发 |
| 无法区分「空闲」与「读不到」 | **每 30 s 一条状态行**，任何界面都写：`worlds / session / beacon_units / aircraft_units / temp_bytes / last_tick / samples / calls / backoff` |
| 探针可能拖累游戏 | 25 ms 帧预算 + 退避 + 连续 5 次超标**永久自停** |
| 崩溃丢数据 | jsonl 定期 flush（0.1.0 的数据就是随崩溃丢的） |

### 实机验证结果（`0.6.0`）

```
v0.6.0 installed ... Script=table Window=table
status: worlds=11 session=true (GameSession.in_session(session)) beacon_units=1
        aircraft_units=0 temp_bytes=0 last_tick=0.0ms samples=0 calls=0 backoff=x1
a beacon-identity unit is present but has not moved 0.75 m: ignoring it as the ship prop
```

加载器：`Startup finished: 61 loaded, 0 failed`；游戏进入飞船界面并稳定运行；**`calls=0`** 证明静止物件
不再被误判；**无慢帧、无自停、无错误、无新转储**。

### 为什么这些规则现在有测试兜着

`tests/test_analyzer.py` 的 `CostContractTest` 把我犯过的每一条都变成断言：per-tick 路径不得出现
`RESOLVED`、`units_by_resource` 只能查信标与飞机、必须在 tick 内过 `in_session()`、必须存在
temp 守卫、必须有自停分支、采样率不得高于 5 Hz、必须定期 flush、**`in_session` 必须带 session 参数**
（并显式禁止裸调用回归）、必须以移动为呼叫判据、必须每 30 s 写状态行。**这些是我已经犯过一次的错，
不该靠我记得。**

---

它只回答一个问题：**呼叫飞鹰系列红战备时，飞鹰飞机的真实来袭方向是什么，它与潜兵、与战备信标是什么几何关系？**

它不画任何东西、不改任何数值、不授予任何能力。装进游戏后它只写两个日志文件，然后等你把日志交给离线分析器。

## 为什么需要这个探针

做「飞鹰来袭方向预测」模组的前提，是知道那个方向**由什么决定**。

**它不是一条统一规则。** 多个来源都说飞鹰按「俯冲方向与投掷方向的关系」分成两个家族：

| 家族 | 飞鹰型号 | 方向 |
| --- | --- | --- |
| **平行（从身后）** | 机枪扫射、110mm 火箭巢、500kg | 沿「潜兵→信标落点」连线，**从玩家背后**来袭 |
| **垂直** | 空袭、集束炸弹、凝固汽油弹、烟雾弹、（推测：毒气空袭） | **垂直**于该连线，从目标一侧切到另一侧 |

所以「预测方向」要按型号分别算，而**哪一侧**（左还是右）反倒是最不确定的一项——有资料说它与玩家朝向有关（描述为「自东向西俯冲」）。分析器因此把左右两个方向都作为候选，由数据决定，而不是先假设一个。

**方向不在任何静态数据里。** 实机字段转储显示 11 条 `EAGLE.*` 定义记录没有任何方向/角度字段；`EagleComponentData`（11 条 × 152 B）里唯一被命名的字段是 `+24 (u32) = 投送弹丸 id`，决定「投哪颗弹」而不是「从哪来」。所以只能实测。

### 来源与可信度（重要）

| 来源 | 日期 | 说了什么 | 可信度 |
| --- | --- | --- | --- |
| 玩家（本项目用户） | 2026-10-07，当前版本 | 机枪沿连线从身后；集束垂直从左侧 | 当前版本，但未取证 |
| [九游攻略](https://www.9game.cn/news/9843701.html) | **2024-02-24（首发期）** | 完整的两家族分类（见上表） | **可能已过期**：文中说「飞鹰一个 7 个空袭」，而毒气空袭等是后来加的 |
| [机核讨论](https://www.gcores.com/talks/1249985) | 2026-06 | 空袭默认垂直「潜兵与信标连线」 | 与上表一致，但是玩家建议帖 |

三者对**两家族结构**是一致的，所以这个结构可以当作先验；但**具体某一型号的左右侧**没有任何来源能确定，且首发期资料可能已经不准。分析器把预期**预先注册**（`EXPECTED_RULES`），测量结果只能**确认或反驳**它，不能事后凑；凡是被反驳的型号会明确标成 `CONTRADICTS`。毒气空袭那份预期标注为「外推」，因为 2024 年那份资料里还没有它。

## 只读契约

以下每一条都可以直接在源码里核对，而不是只听声明：

- 全文没有任何内存写调用（也没有 `ffi`，更谈不上 `WriteProcessMemory`）；
- 不调用任何会改状态的引擎函数；
- 只读游戏自带的 `stingray` 表上的访问器；
- 每一次引擎调用都包在 `pcall` 里，**不可能**中断 update 循环；
- 只写两个文件，都在加载器自己的日志目录下；
- 到硬性采样上限就停，并在日志里写明停了。

`tests/test_analyzer.py` 里的 `ReadOnlyContractTest` 会把上面几条当断言跑，写调用一旦被加进去测试就会红。

## 它怎么找目标

| 目标 | 键 | 来源 |
| --- | --- | --- |
| 信标（战备球） | `resource_hex = 16f397ca5f51f271`，经 `sr.IdString64.from_hex` 传 `units_by_resource` | 已实机运行的第三方模组目录 |
| 飞鹰飞机 | `content/fac_helldivers/vehicles/eagle/eagle` | 从 17.2 GB 完整进程转储离线扫出（磁盘上的游戏表是加密的，路径只在运行时内存里） |

若资源查询对飞鹰返回空表（已知对某些确实存在的单位会这样），把源码里的 `FALLBACK_WORLD_SCAN` 改成 `true` 重建：那条路改成按身份分帧遍历全世界（约 22,000 个单位，每帧 2,000），且只在一次呼叫存活期间跑——因为「遍历全世界并逐个读坐标」在本工作区有实机崩溃前科。

## 用法

```powershell
python -m pip install -r requirements-dev.txt
python -B work/standalone/build_probe.py --validate-only   # 四道门禁
python -B work/standalone/build_probe.py                   # -> dist/
python -m unittest discover -s tests -v                    # 离线检查
```

然后：

1. 在模组管理器里导入 `dist/HD2-EagleDirectionProbe-0.3.0.zip`，确认 **Bingus Shared Loader** 也启用，部署；
2. 进一局，从不同角度呼叫飞鹰战备 3–4 次（空袭 / 集束 / 凝固汽油 / 机枪扫射 都行；500kg 是单发、没有轴线，别只用它）。**基准数据尽量在开阔地形取**，理由见下节；
3. 退出任务，探针在 shutdown 时刷盘。

结果：

- `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\EagleDirectionProbe.jsonl` —— 逐样本记录，分析器的输入；
- `%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\EagleDirectionProbe.log` —— 人读：`stingray` 能力表、每次呼叫的起止、关闭摘要。

分析：

```powershell
python -B tools/analyze_eagle_probe.py "%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\EagleDirectionProbe.jsonl"
```

它按呼叫打印「潜兵→信标方位 / H1 预测轴 / 实测轴 / 残差 / 飞机首次现身到信标落地的提前量」，最后给 H1 是否成立的判读。**判读是数字给的，不是脚本的立场**：残差小且跨呼叫一致才叫支持 H1。

## 看日志时先看这三个信号

| 日志里出现 | 含义 | 下一步 |
| --- | --- | --- |
| 首个 `stingray` 能力表全为 `table` | 引擎 API 与任何共享运行时模组无关，一次性定论 | 继续 |
| `beacon units=0` | 信标没被枚举到 | 先修这个，否则整轮数据无用 |
| 有 `call N began` 但样本里没有 `eagles` | 飞鹰单位没被资源查询列出 | 打开 `FALLBACK_WORLD_SCAN` 重建 |
| 分析器打印 `measured from : aircraft` | 方向取自**飞机本体**的航迹，这是可信的那种 | 正常 |
| 分析器打印 `NOT the aircraft` 或 `WARNING` | 该次没抓到飞机，方向取自**弹体**——弹体是下落的，不是来袭方向 | 该次读数不可信；若每次都这样，先修飞机查询 |

**为什么分析器要挑轨迹。** 探针同时记录飞机和弹体。弹体的轨迹是**下落**，不是来袭方向。所以分析器**优先取飞机**那条（`src=aircraft`），只有在完全没有飞机轨迹时才退回弹体，并明确打出警告——退回的读数不该被同等信任。

## 已知机制：飞鹰会规避障碍（用户提供，本仓库尚未验证）

玩家报告：**若来袭方向上有障碍物，飞鹰的方向会发生变化。**

这条对测量和设计的影响都不小，所以单列一节：

- **对判读的影响。** 残差不为零从此有三种解释，而不是两种：H1 不成立、测量噪声、或者**那一次被障碍物扰动了**。一个 55° 的残差不能直接当作「H1 不成立」的证据。因此分析器把「部分吻合、部分偏大」单独判为 **MIXED**，并明确要求人来交代哪几次是朝着掩体扔的——**探针看不见地形，这件事只能由玩家提供**。
- **对测试方案的影响。** 基准取在开阔地形，残差才反映规则本身；想观察规避效果，就**故意朝大型掩体扔一次**，作为一个标注过的对照。这样「规则」与「扰动」才有可能分开。
- **对模组设计的影响。** 如果规避是真的，那按几何算出的**名义轴在掩体附近必然偏**。这提高了「直接读实时飞机航向」那条路的价值——它拿到的是规避之后的真实方向；而名义轴要么接受在掩体附近出错，要么得额外建模地形。

## 本地检查做了什么

- 四道打包门禁：声明行与资源名一致、**真 LuaJIT 2.1 编译**（`lupa`）、`ffi.cdef` 无 `user32`、归档内无脚本类文件；
- `AnalyzerDiscriminationTest`：用两个**合成夹具**验证分析器能分辨该接受与该拒绝的情形——H1 夹具残差 0.4°、H2 夹具残差 89.6°，并要求两者分离度 > 60°。只断言「H1 通过」是不够的：一个对什么输入都说「一致」的工具不构成证据。这两个夹具是在本轮开发中真实抓出过一个 bug 之后留下的回归；
- `ReadOnlyContractTest`：把只读契约当断言跑。

**离线检查不等于游戏验收。** 门禁与包检查只证明「格式合法、LuaJIT 能编译、结构正确」，**不证明它能跑出数据**——最可能在实机翻车的正是信标枚举与飞鹰路径这两处。

## 目录

| 路径 | 用途 |
| --- | --- |
| `src/eagle_direction_probe.lua` | 只读采样 addon（唯一出货源码） |
| `tools/analyze_eagle_probe.py` | 离线分析器：拟合 H1/H2，输出残差与提前量 |
| `tools/make_fixture.py` | 合成已知答案夹具 |
| `tests/` | 上表的离线检查与夹具 |
| `work/standalone/build_probe.py` | 构建与门禁；不部署 |
| `work/standalone/vendor/bingus/` | 第三方信封编码器，按惯例**不入库**，见 `THIRD_PARTY_NOTICES.md` |
| `dist/` | 可导入模组管理器的安装包 |

## 边界

- 只改本仓库；第三方模组保持只读参考，署名见 `THIRD_PARTY_NOTICES.md`。
- 不依赖 HD2Runtime 或任何共享运行时包；探针首行日志会把这件事实测出来。
- 不部署：构建只写 `dist/`，部署是你在管理器里的一次明确动作。
- 依赖 Bingus Shared Loader v15+ / API 1。
- 本仓库有独立 `.git`；根工作区忽略整个 `mods/`。

---

## English

**Status: a read-only measurement instrument. Source, tests and package are
complete; it has never been run in the game, and no in-game effect is claimed.**

It answers one question: when an Eagle-series red stratagem is called, what is the
aircraft's actual incoming direction, and how does it relate to the player and the
stratagem beacon? It draws nothing and grants nothing.

The direction is not in any static data: the 11 live `EAGLE.*` definition records
carry no heading or angle field, and the only named field in `EagleComponentData`
(11 records x 152 B) is `+24 (u32) = payload projectile id`, which chooses *which
bomb*, not *from where*. So it has to be measured, which is what this addon is for.

Its read-only contract is auditable in the source and asserted by
`ReadOnlyContractTest`: no memory writes, no mutating engine calls, only read
accessors on the game's own `stingray` table, every call wrapped in `pcall`, two
log files under the loader's own directory, and a hard sample budget.

```powershell
python -m pip install -r requirements-dev.txt
python -B work/standalone/build_probe.py --validate-only
python -B work/standalone/build_probe.py
python -m unittest discover -s tests -v
```

Import `dist/HD2-EagleDirectionProbe-0.3.0.zip` alongside Bingus Shared Loader v15+,
deploy, call a few Eagle stratagems from different angles, then leave the mission.
Results land in `EagleDirectionProbe.jsonl` and `EagleDirectionProbe.log` under
`%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\`, and
`tools/analyze_eagle_probe.py` fits both candidate hypotheses and prints the
residuals and the aircraft's lead time.

Offline checks are not game acceptance: the gates prove the envelope is well formed
and the source compiles on LuaJIT, not that the probe produces data. The two most
likely places to fail in game are the beacon enumeration and the Eagle resource
lookup; the README's signal table is written for exactly those.
