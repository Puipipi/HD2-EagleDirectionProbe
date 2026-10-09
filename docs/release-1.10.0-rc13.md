# 1.10.0-rc13 紫色原生灯对照与单侧光片文字

rc13 是本地候选包，未经部署或发布。相较 rc12，本版为原生灯颜色提供隔离对照，并按缓存的本机观察位置为每块光片只绘制一侧文字；同时接入本机 pose 与观察侧选择模块。红光未出现的根因仍未定位。

## 原生灯颜色对照

MOM 中的“原生紫色投光对照测试”默认关闭。开启后，仅把本原型拥有的 task-fill 灯颜色设为归一化 RGB `(1,0,1)`，强度保持 `7000`；位置、旋转、资源光锥与可见性不变。自有 helper 首次成功配置后，记录原始及配置后颜色/强度、灯节点世界位置和根 forward。后续移动仍先设置 local transform、再调用 `World.update_unit`，但不会反复读回。该刷新次序与已安装头灯控制器一致；rc12 已有 optional update 调用，因此本版不声称修复了缺失刷新。root forward 也不证明嵌入灯的实际光束轴。是否照亮地面、实际颜色和遮挡仍需用户手动实机确认。

## 光片文字与危险提醒

光片保留六块名称，B 与 8 使用不同的矢量笔画。每个 10 Hz 面板更新桶仅取一次缓存的本机 pose，并为每块文字选择一个 inner 或 outer 副本；没有可靠 pose 时保留单侧回退，不绘制镜像的第二份文字。几何测试覆盖正反观察侧、圆弧和线条回退，并核对实际 producer 三角方向。游戏 GUI 的深度/剔除行为及实际文字可读性仍待手动验收。

潜兵危险提醒只对已确认的飞鹰类型使用 catalog 参考范围；玩家离开范围或 guide/world 结束时撤除。140mm 只表示潜在路径，不是伤害 footprint 或安全边界。危险标记和提醒文字的实际游戏内可见性仍待验收。

## 性能和边界

离线公平对照使用 rc11/current 源码、相同合成 guide 与 3×600 帧场景。solid-fill 的 rc11→当前 ms/frame 为 1 guide `0.1225→0.0908`、4 guides `0.4068→0.2853`、8 guides `0.5934→0.4375`；line fallback 为 `0.0744→0.0600`、`0.2270→0.2031`、`0.4633→0.4058`。本组测量覆盖模拟 native/terrain 边界，没有覆盖真实本机 pose 读取、游戏引擎提交、GPU 灯光或游戏帧率；结果没有达到并不能证明或满足 `0.05 ms/frame` 的实机目标。所有场景维持相同的 1/4/8 个 confirmed guides，测量期间无 terrain query 或几何 rebuild。

QPC 计时用于一致时钟域内的期限；运行时 QPC 失败会连续回退到标记为不精确的时钟。状态行的 active/idle 是按最近任务 session 状态分桶，并不代表该帧一定显示 guide。缓存失效、每帧 LineObject 提交、10 Hz 光片运动与普通走廊 cadence 保留。没有新增 terrain query、Runtime 依赖或 guide 数量上限；`terrain_query.lua` 与 `terrain_contract.lua` 不在本次修改中。

## 验证

全量离线测试命令：

```powershell
python -B -m unittest discover -s tests -v
```

结果：**302 tests，exit 0**。原始输出保存在外部工作目录 `C:\Users\23825\Desktop\2-apex-x20\work\eagle-rc13-review\final-full-tests.txt`，不随包发布。

构建与包校验命令：

```powershell
python -B work/standalone/build_probe.py --validate-only
python -B work/standalone/build_probe.py
python -B work/standalone/verify_package.py
```

所有 12 个 Lua 资源由 LuaJIT 编译并由 package verifier 检查 ZIP CRC、manifest 与逐个源码 payload；terrain 两文件与 v1.9.10 字节一致。包体积 **2,232,323 bytes**，SHA-256 `e9942237c06f6f4531fa6732e9b64277709956efb164272dea13f7bbc2b005cd`，校验文件为 `dist/SHA256SUMS-1.10.0-rc13.txt`。本地候选未经部署、提交或发布。
