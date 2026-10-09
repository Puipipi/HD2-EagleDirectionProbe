# 1.10.0-rc12 危险提醒、native-light 诊断与性能更新

rc12 基于 rc11，继续隔离未确认的蓝色支援信标，并增加本机潜兵危险提醒、native-light 颜色读回诊断、可读光片字形和缓存失效修正。该候选仅经过离线验证；没有在游戏中部署或操作。

## 本机危险提醒

MOM 的 **潜兵危险提醒** 默认开启。仅当两次唯一位置匹配已把落点确认到已知飞鹰战备后，才将现有本机玩家 pose 与 catalog 参考范围比较，并在可能波及时显示琥珀标记及具体战备短名。它不依赖 `show_type`、范围可视化或其它普通走廊开关；玩家身份或类型未确认时不猜测，也不表示参考范围外安全。

18 空袭、65 集束、38 烟雾、126 毒气、133 凝固汽油沿用统一的用户显示校准：总长约 66.67 m、总宽 20 m。500kg 用 25 m 圆形参考范围。30 Strafing Run 按 catalog 前伸范围判断。140 Rocket Pods 只显示潜在飞行路径提示，不称作准确伤害或安全边界。危险提醒每 0.1 秒更新已缓存的本机 pose，不增加地形查询；玩家离开范围、战备结束或 world 改变时撤除提醒。多人本机身份使用 PlayerCall 的玩家编号匹配，不选最近队友。

## 红光与光片

native-light 将目标颜色拆成归一化 RGB `(1, 120/7000, 180/7000)` 与 intensity `7000`。每个 world 中第一次成功拥有 helper 时，记录原灯颜色/强度和配置后读回值；后续 helper 不重复读取。getter 不存在或失败只影响诊断文本，不改变走廊。需要额外安装并启用 Helmet Headlamp 资源；MOM 原生灯开关仍默认关闭。

这些变化只提高 API 诊断性并遵守颜色接口的归一化约定；**真实红光是否照到地面、亮度、遮挡、光轴和 GPU 成本仍需用户手动实机确认**。没有把刺魟的蓝色地面标记效果或资源引用链视为已识别或已实现。

光片采用缓存的矢量笔画字形，B 与 8 使用不同轮廓；`show_type` 关闭时仍尊重通用 `EAGLE ?` 文案。文字使用单面 winding，保留面板内外两面的正读文本。代码几何法线和离线预览均已检查，游戏实际材质剔除、文字可见性和重复叠字仍需手动验收。危险标记加有水平可见的交叉图形，但不同视角下的游戏内可见性同样未验证。

## 热路径与边界

新增隔离的 QPC 计时模块。需要亚毫秒时序的 `clock_ms` 期限（包括 corridor 与本机 pose poll）使用该时钟；`os.clock` 期限继续留在自己的时钟域，所有期限只与同域时间比较。QPC 运行时失败会连续回退到非递减但不精确的来源，并在状态行报告 source/precision。状态统计按最近观察到的任务 session 状态区分 active/idle；它表示 session 分桶，不表示当前有可见 guide。日志报告 guarded 主路径总体平均和峰值、active/idle 平均，以及 draw 的总体/active/idle 平均与总体峰值；不报告每个分桶峰值。几何 key 缓存仅在源状态变化时重算，包含 terrain revision；移除走廊时立即使几何、flow 和 ground key 失效。native-light 以稳定 reconcile 节奏减少重复 work，新的 helper 仍每帧最多创建一个，关闭/成员变化立即清理。每帧 LineObject 提交、10 Hz 光片运动和普通走廊 cadence 保留。

没有新增地形查询，现有每帧最多两次、0.5 ms 软预算保留；没有 Runtime 依赖，也没有 guide 数量上限。MOM **详细采样记录** 默认关闭，以免默认保存每次采样 JSONL、空闲飞机 pose 序列化和每 call 弹药扫描；开启后恢复这些诊断数据，不改变指引、分类或跟踪。

## 验证

全量命令：

```powershell
python -B -m unittest discover -s tests -v
```

结果：**276 tests，exit 0**。命令原始输出位于外部工作目录 `work/eagle-rc12/final-full-tests.txt`，不打入游戏包。

公平离线对照在 `v1.10.0-rc11` 与当前源码使用相同的合成已确认 18 号 guide、600 warm-up/sample frames、3 repeats、1/4/8 guide 场景、类型快照、LuaJIT 与 Vector3 可调用代理。native line/GUI、terrain 与 type reader 是模拟边界；该场景没有本机玩家 pose 调用、真实引擎或 GPU，因此数字不是游戏帧率，也不是完整 active 运行成本。

| Renderer | Guides | rc11 ms/frame | rc12 ms/frame | rc11 face updates/frame | rc12 face updates/frame |
|---|---:|---:|---:|---:|---:|
| Solid fill | 1 | 0.0672 | 0.0626 | 190.79 | 101.27 |
| Solid fill | 4 | 0.3054 | 0.2270 | 763.16 | 405.08 |
| Solid fill | 8 | 0.5468 | 0.4719 | 1526.32 | 810.16 |
| Line fallback | 1 | 0.0659 | 0.0503 | — | — |
| Line fallback | 4 | 0.1766 | 0.1340 | — | — |
| Line fallback | 8 | 0.3360 | 0.2681 | — | — |

基准原文：`work/eagle-rc12/benchmark-solid.txt` 与 `work/eagle-rc12/benchmark-fallback.txt`。三种 guide 数量均在测量前后确认非空且保留同样数量；基准测量阶段新增 terrain query 与 rebuild 都为 0。该结果不证明 0.05 ms 游戏内目标已达到，特别是 solid-fill 1-guide 仍高于该数值。

## 本地候选包

`python -B work/standalone/build_probe.py --validate-only` 与 `python -B work/standalone/build_probe.py` 均退出码 0。全部 11 个 Lua 资源通过 LuaJIT 2.1 编译、resource declaration 和 `ffi.cdef` 门禁；构建后 `python -B work/standalone/verify_package.py` 退出码 0，验证 ZIP CRC、manifest、11 个 source payload、封面引用以及 `terrain_query.lua` / `terrain_contract.lua` 与 v1.9.10 字节一致。

本地包 `dist/HD2-EagleDirectionProbe-1.10.0-rc12.zip`：**2,230,169 字节**，SHA-256 `e374334f91094ac0cef801e935a1de0b91ac7e057a5e7a66c1bbd0db82287bcd`。校验文件为 `dist/SHA256SUMS-1.10.0-rc12.txt`。本候选没有部署或发布。
