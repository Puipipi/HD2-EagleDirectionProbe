# 1.10.0-rc11 蓝色支援信标隔离与诊断

rc11 修复了未确认的蓝色支援信标被当成飞鹰攻击落点、进而继承最近飞机方向并绘制 Eagle 走廊的问题。飞行中的信标仍保留为待分类候选；只有通过现有两次唯一位置匹配、并确认属于已知飞鹰战备的记录，才会关联飞机、绘制地面/天空/警戒带，或进入可选 native-light helper。unknown、unsupported、ambiguous 和读取失败的未确认候选不会冒充 Eagle。独立飞机箭头继续按飞机跟踪显示；已经确认的 Eagle 在短暂读取失败时保留现有指引。

分类继续使用原有 5 Hz 轮询；只要有活跃候选，即使战备名称和范围开关都关闭也继续识别。没有候选时不会查询。正向确认状态与 UI 显示开关解耦。多个真实飞鹰、队友和 Eagle Storm 记录仍分别处理，没有按资源 ID 或距离合并，也没有 guide 数量上限。

## 横向战备参考范围

飞鹰空袭（18）、集束炸弹（65）、烟雾（38）、毒气（126）和凝固汽油（133）共用总长约 **66.67 m**、总宽 **20 m** 的矩形参考范围，保持原落点中心和来袭方向。该范围是用户选择的显示校准，不是测得的伤害、弹着或火场边界。Strafing Run（30）、500kg（3）和 110mm Rocket Pods（140）保持原有形状及范围。

## 启动与信标归属诊断

启动时只记录一次 native-light binding 类型快照。用户手动导入 rc11、完全退出并重启游戏，到主菜单即可查看：

`%LOCALAPPDATA%/CowboyBingus/Helldivers2/Logs/EagleDirectionProbe.log`

查找 `native-light capabilities` 行；启动快照只访问全局 API/成员的可见类型，不调用灯光 getter/setter、不构造向量、不创建 Unit，也不安装额外 update hook。它记录的是加载时可见性，不证明实机调用签名或照明效果。

如果之后在正常游戏中再次出现多条走廊，请反馈对应 `beacon B#` 事件。每个 tracking record/episode 使用匿名递增编号；它不是引擎永久 Unit ID，同一 Unit 在记录清理、重置或超过 60 秒后重新出现时可能取得新编号。JSON sample 保留原 resource ID，并附 `trace` 与 `motion`；事件记录当时已有的位置、速度、位移、strike 与 call 关联。`pending`、`pending-next-call` 或 `-` 表示当时尚未绑定已知 call，不代表原因已确定。诊断只在事件变化时记录，不修改落点/走廊选择。

## 原生灯与刺魟效果状态

原生红色投光开关仍默认关闭，需另外安装并启用 Helmet Headlamp 资源。rc11 不声称红光已经照亮地面，也没有验证投光轴、亮度或 GPU 成本。

现有 Stingray 研究只确认目标敌机模型不含 `KHR_lights_punctual`，官方导出器可处理原生灯；环境 `il_spotlight_01` 有蓝色聚光灯，但未发现攻击状态机到地面蓝色标记效果的引用链。因此 rc11 不声称已经识别或实现 Stingray 的蓝色地面标记效果。

## 验证与范围

Fresh 全量离线测试：`python -B -m unittest discover -s tests -v`（228 项，退出码 0）。构建门禁通过 7 项 LuaJIT 2.1 编译、resource declaration 与 `ffi.cdef` 检查；`python -B work/standalone/verify_package.py` 验证 ZIP CRC、manifest、7 项 source payload、封面引用和两个地形资源字节一致。

最终包 `dist/HD2-EagleDirectionProbe-1.10.0-rc11.zip` 为 **2,220,895 字节**，SHA-256：`14a63c5a352ea5e9870060898c3920499b59f8eecdabbd049fa730247c60f3d0`；`dist/SHA256SUMS-1.10.0-rc11.txt` 与包一致。`src/native_light_probe.lua` 与 rc10 字节一致；`src/terrain_query.lua` 与 `src/terrain_contract.lua` 与 v1.9.10 字节一致。不把离线模拟结果描述为游戏内照明或 FPS 验证。

普通方向指引不依赖 HD2Runtime；没有新增地形查询、每帧 guide 上限或活跃 guide 数量限制。既有地形查询预算保持每帧最多 2 次、0.5 ms 软预算。用户仍需手动导入并实机确认显示效果。
