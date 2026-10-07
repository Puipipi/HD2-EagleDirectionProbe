# 飞鹰来袭方向探针 / Eagle Direction Probe

**状态：只读测量工具，源码、测试与安装包齐备；一次实机都没跑过，不宣称任何游戏内效果。**

它只回答一个问题：**呼叫飞鹰系列红战备时，飞鹰飞机的真实来袭方向是什么，它与潜兵、与战备信标是什么几何关系？**

它不画任何东西、不改任何数值、不授予任何能力。装进游戏后它只写两个日志文件，然后等你把日志交给离线分析器。

## 为什么需要这个探针

做「飞鹰来袭方向预测」模组的前提，是知道那个方向**由什么决定**。两个竞争假设：

| | H1：设计规则 | H2：实时航向 |
| --- | --- | --- |
| 假设 | 来袭轴垂直于「潜兵→信标」连线，左右由潜兵朝向决定（社区说法） | 来袭轴 = 飞鹰飞机当下的航向（它平时绕圈，从当前位置切入） |
| 预测时机 | 投掷瞬间即可算出 | 必须等飞机出现 |
| 若成立 | 模组只需两个坐标加一条线 | 模组要持续跟踪飞机并处理提前量 |

**方向不在任何静态数据里。** 实机字段转储显示 11 条 `EAGLE.*` 定义记录没有任何方向/角度字段；`EagleComponentData`（11 条 × 152 B）里唯一被命名的字段是 `+24 (u32) = 投送弹丸 id`，决定「投哪颗弹」而不是「从哪来」。所以只能实测。

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

1. 在模组管理器里导入 `dist/HD2-EagleDirectionProbe-0.1.0.zip`，确认 **Bingus Shared Loader** 也启用，部署；
2. 进一局，从不同角度呼叫飞鹰战备 3–4 次（空袭 / 500kg / 机枪扫射 / 集束 都行）；
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

Import `dist/HD2-EagleDirectionProbe-0.1.0.zip` alongside Bingus Shared Loader v15+,
deploy, call a few Eagle stratagems from different angles, then leave the mission.
Results land in `EagleDirectionProbe.jsonl` and `EagleDirectionProbe.log` under
`%LOCALAPPDATA%\CowboyBingus\Helldivers2\Logs\`, and
`tools/analyze_eagle_probe.py` fits both candidate hypotheses and prints the
residuals and the aircraft's lead time.

Offline checks are not game acceptance: the gates prove the envelope is well formed
and the source compiles on LuaJIT, not that the probe produces data. The two most
likely places to fail in game are the beacon enumeration and the Eagle resource
lookup; the README's signal table is written for exactly those.
