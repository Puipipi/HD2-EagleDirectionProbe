# 飞鹰战备类型、范围与 CT 可用性研究

查询日期：2026-10-09。用途：离线资料准备；本文和 `research/eagle-stratagem-profiles.json` 均不参与运行，不代表已实现类型识别或范围自适应。

## 结论

根目录 CT 可以提供若干弹种的基础爆炸半径候选及共享关系，但没有提供经过验证的「某个普通战备球 → 本次呼叫类型 → 所属玩家 → 飞机/投弹事件」关联链。其四个 `STRATAGEM SLOT` 是 CT 手动选择的扫描目标，不是游戏装备槽或投掷类型读取器。因此不能用这些槽位给每次投掷自动定型，也不能据此给警戒条带自动换宽、换形或贴具体名称。依据是下文的静态源码检查；本次未执行 CT、未扫描或读取游戏进程。

八种战备的方向和效果可整理为候选档案，但单弹半径不能直接作为整轮投弹的长宽。只有可靠关联本次呼叫、确认实际投弹中心/散布、版本及舰船升级后，才有条件做范围适配。当前所有档案 `automatic_ready=false`，整轮长宽为 `null`。

## 来源与覆盖

用户指定的 [Eagle Stratagems 分类](https://helldivers.wiki.gg/wiki/Category:Eagle_Stratagems) 列出九页：以下八种攻击/区域效果战备及 Rearm。[Eagle Rearm](https://helldivers.wiki.gg/wiki/Eagle_Rearm) 是返舰补充弹药命令，单独排除，不建立攻击范围档案。

Wiki 是用户指定的社区资料源，不能视为开发商对运行时接口的保证。直接页面抓取返回 403，本次通过定向搜索取得该站索引正文，抓取时间各异；记录的是 2026-10-09 所见内容，未声称已核对页面最新修订或实机当前补丁。CT 则以本地文件原文为一手静态证据。

## 八种战备特点与形状建议

单位均为米。`内 / 外 / 冲击波` 是对应单颗弹药/效果记录的三个半径，不是三种整轮安全距离；冲击波半径不能一概标成致死边界。表中形状仅为待验证的表现建议，不是已经测定的伤害包络。

| 战备与来源 | 特点、方向 | 单弹/效果半径：内 / 外 / 冲击波 | 形状建议与缺口 |
| --- | --- | --- | --- |
| [Strafing Run，机炮扫射](https://helldivers.wiki.gg/wiki/Eagle_Strafing_Run) | 顺投掷方向扫射，自信标向前；弹幕含直击与爆炸弹。 | 爆炸弹：2.5 / 5 / 6.5 | 顺向窄走廊；单弹圆并集。整轮弹着间距、散布与地形遮挡未确认。 |
| [Airstrike，空袭](https://helldivers.wiki.gg/wiki/Eagle_Airstrike) | 基础为六枚炸弹成直线，横于投掷方向；兼顾群体、重目标和建筑。 | 单枚：5 / 10 / 14 | 横向投弹带；六个弹心并集。不能用直径 20m 当整轮长度。 |
| [Cluster Bomb，集束炸弹](https://helldivers.wiki.gg/wiki/Eagle_Cluster_Bomb) | 横向撒布；母弹空爆，每颗释放八枚子弹药，偏向清理中小目标。 | 母弹：1 / 2 / 10；子弹：3 / 6 / 8 | 横向散布包络；须区分母弹空爆与子弹着地。八枚子弹不等于整轮仅八枚。 |
| [Napalm Airstrike，凝固汽油空袭](https://helldivers.wiki.gg/wiki/Eagle_Napalm_Airstrike) | 横向投弹，先爆炸再留下火区；即时爆炸与燃烧为不同阶段。 | 即时爆炸：2 / 10 / 15 | 横向持续火区。火区边界/持续时间另建模型，不能从爆炸外径直接断言。 |
| [Smoke Strike，烟雾攻击](https://helldivers.wiki.gg/wiki/Eagle_Smoke_Strike) | 横向烟幕，遮挡视线；烟雾效果持续 30s，实体弹身仍能直击。 | Wiki烟雾：12 / 12 / 0；CT：8 / 8 / 0 | 横向遮蔽带，须与爆炸伤害边界区分。存在参数冲突，不能自动选取。 |
| [110mm Rocket Pods，110mm 火箭巢](https://helldivers.wiki.gg/wiki/Eagle_110mm_Rocket_Pods) | 三组、每组两枚火箭；选择信标附近最大目标，实际弹着中心不保证在球上。 | 每枚：1.60000002 / 5 / 8 | 已确认目标周围的点状弹着包络。不得以球为中心画「保证覆盖圆」。 |
| [500kg Bomb，500kg 炸弹](https://helldivers.wiki.gg/wiki/Eagle_500kg_Bomb) | 单枚重弹先嵌入地面再主爆；进场方向与投掷方向同向。 | 主爆：10 / 25 / 35；触地：1 / 3 / 6 | 实际弹着点周围两阶段圆形投影；地形、障碍和爆炸立体形状仍需核实。 |
| [Gas Airstrike，毒气空袭](https://helldivers.wiki.gg/wiki/Eagle_Gas_Airstrike) | 横向多弹毒气带，施加伤害与混乱；效果场持续 15s。 | 单个效果记录：1 / 12 / 15 | 横向持续气体区；效果记录半径不是整轮长宽。根 CT 未发现对应飞鹰毒气档案。 |

上述多页还说明投掷球弹跳可能改变入场/投弹方向。Wiki 的方向规律可用于候选模型，但不能把飞机当前朝向自动等同于每类战备的地面伤害带方向。

Airstrike、Cluster、Napalm、Smoke、Gas 各页列出 XXL Weapons Bay 会增加多弹战备的投弹数量；因此不能只存一个固定弹数/固定足迹。Expanded Weapons Bay 增加的是返舰前使用次数，不能误当投弹数量。这些升级的实际拥有状态、本次投弹间距及散布尚无可靠来源。Napalm 页面记录 1.007.000（2026-08-12）扩大爆炸半径并拉开投弹图案，进一步说明半径和投弹足迹必须分开。

## 根 CT 静态审计

文件：[helldivers2.CT](C:/Users/23825/Desktop/2-apex-x20/helldivers2.CT)。SHA256：`dbba984503c7bf3ccbfcafa14cf8be33879aac3464ce2a84dafdffed24917b4e`。

- [第644行](C:/Users/23825/Desktop/2-apex-x20/helldivers2.CT:644) 分配 `HD2Strat12_State`；第651–654行注释和初始化说明 `+10/+14/+18/+1C` 是四个选择索引。它是 CT 自己分配的状态区。
- [第865行](C:/Users/23825/Desktop/2-apex-x20/helldivers2.CT:865) 的 `groupNames` 及第866行 `selectorOffsets`，配合第868–876行 `selectedGroup`，从该状态区读整数映射到组名，没有从玩家或战备球读取投掷类型。
- [第1322行](C:/Users/23825/Desktop/2-apex-x20/helldivers2.CT:1322) 的手选下拉列表，第1353行地址为 `HD2Strat12_State+10`；其余三个槽同构。`ReadOnly` 限制列表输入形式，不等于列表内容来自游戏。
- [第1038行](C:/Users/23825/Desktop/2-apex-x20/helldivers2.CT:1038) 的 `scanRadiusOne` 生成三浮点签名并 `AOBScan`；第1078–1119行仅按手选组扫描弹药伤害/半径模板，候选数过多会拒绝半径写入。找到模板/候选地址不等于找到一个活跃投掷球或其所属玩家。
- [第753行](C:/Users/23825/Desktop/2-apex-x20/helldivers2.CT:753) 说明 Airstrike / Cluster / Napalm / Smoke 共用 100kg 弹身伤害记录；第761–763行说明 Cluster 与 Orbital Napalm 共用爆炸伤害记录；第768–769行说明 Strafing 与 Orbital Gatling 共用伤害记录。共享数据不能当本次呼叫独占指纹。
- [第825行](C:/Users/23825/Desktop/2-apex-x20/helldivers2.CT:825) 起 `radiusProfiles` 给出500kg、110mm及飞鹰多类单弹半径。烟雾第848行为8/8/0，而 [Smoke Wiki](https://helldivers.wiki.gg/wiki/Eagle_Smoke_Strike) 记录1.007.000将每弹8m增为12m：CT旧值与Wiki新值的冲突有版本解释线索，但未在本机运行版本验证。两份值均保留，禁止静默择一。CT把 Napalm 命名为即时爆炸/火场半径，也不能由这一注释认定持续火区独立形状已测定。

本次静态审计未获得普通战备球到类型/玩家的可靠链；不是对所有潜在游戏内部结构作不存在的证明。也未把 CT 的 Gas Mine/Gas Mortar 档案冒充 Eagle Gas Airstrike。

## 现有探针与文字标签

[identify_call](C:/Users/23825/Desktop/2-apex-x20/mods/eagle-direction-probe/src/eagle_direction_probe.lua:700) 查询世界中的各弹药资源，将「世界里存在某弹种」写到当前 call；没有按球、发起玩家、投弹事件逐个关联。任一世界级命中也不足以在多人或连续呼叫时归属到本次投掷。[接手记录](C:/Users/23825/Desktop/2-apex-x20/mods/eagle-direction-probe/docs/handoff-2026-10-08.md:68) 明记真实弹药查询均为0，本地菜单的最近选择不能证明投掷提交，也不能关联队友。

警戒条带上的具体名称与范围切换需要同一条每球关联链。建议只在来源已验证且唯一关联本次呼叫时显示具体名称；其余显示 `EAGLE ?` / 未知。不能从 CT 手动槽位、世界级弹种存在、最近本地菜单选择推断队友的类型。离线档案中的名称是资料字段，不是自动识别结果。

## 接入前还缺什么

1. 可读且已验证的投掷/呼叫类型ID，以及球/事件、发起玩家、飞机/投弹事件间的唯一关联；包含队友、同时呼叫、球弹跳与取消。
2. 各类实际弹着中心、基础弹数、舰船升级状态、弹间距和随机散布；110mm还须确认索敌目标与命中中心。
3. 当前游戏版本与模板版本对照，首先解决Smoke 8m/12m冲突；Gas补足本地来源。
4. 即时爆炸、冲击波、火/气/烟持续场的独立几何、时序及地形/遮挡条件。所画边界只能表达已经证实的语义。

在上述证据取得前，保留通用警戒走廊及未知名称是诚实的降级策略。JSON只为后续验证保存候选参数、来源和缺口，未增加运行依赖、原生调用或自动范围切换。
