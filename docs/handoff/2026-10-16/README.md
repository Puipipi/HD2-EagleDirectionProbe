# 2026-10-16 开发交接资料

本页面与链接的归档属于开发交接材料，不是新的软件版本。完整归档作为 GitHub Release 附件提供：

- [完整工作区与版本包（ZIP）](https://github.com/Puipipi/HD2-EagleDirectionProbe/releases/download/developer-handoff-2026-10-16/HD2-EagleDirectionProbe-Developer-Handoff-2026-10-16.zip)
- [独立包校验报告（JSON）](https://github.com/Puipipi/HD2-EagleDirectionProbe/releases/download/developer-handoff-2026-10-16/HD2-EagleDirectionProbe-Developer-Handoff-2026-10-16.zip.verification.json)
- ZIP 大小：106,277,656 bytes；SHA-256：`5dfcf01e9900e06c7d40b17fb5662c20d04ac457e37482cc5fedea402834d9a0`。

归档内 `releases/` 包含原样保留的正式 1.10.0 和 1.10.1-beta.1 ZIP，未重建。beta.1 的渲染距离默认值是 80 m；用户只在临时设为 40 m 时实测同一 guide 离开范围隐藏、走回范围恢复。默认 80 m 没有单独实测结论。

归档中的 `workspace/eagle-direction-probe/src/` 是未提交工作树，不能假设与正式版或 beta.1 一致，也不要直接从中构建发布包。冻结 beta.1 源快照位于 `workspace/eagle-direction-probe/work/eagle-multi-perf-20261016/candidate/`。

## 最新隔离实验

[`latest-experiment/`](latest-experiment/) 单独提供静态原生文字原型及离线验证文件，便于审阅；它未集成到生产源码，15 项测试使用 fake engine，没有调用游戏原生 API、没有游戏内画面/性能验证。历史性能数据见 [`performance-results.md`](performance-results.md)；0.05 ms/帧目标尚未证明达到。完整文件级排除清单见 [`exclusions.tsv`](exclusions.tsv)，包 CRC、manifest 和成员哈希结果见 [`package-verification.json`](package-verification.json)。

## 后续开发约束

保持无 guide 数量上限、80 m 默认值、已建立的遮挡、真填充、颜色和语言保存行为；谨慎处理定制材质及原生 sidecar。请先从归档的正式/候选版本和研究证据确认基线，不要将 dirty `src/` 当作发布源。

技能交接材料对应 [`HD2-Agent-Skills` commit 03418b3420d06adf0465fb004c13c1442b8692bb](https://github.com/Puipipi/HD2-Agent-Skills/commit/03418b3420d06adf0465fb004c13c1442b8692bb)，四项技能的副本、patch 与验证记录也收录在总 ZIP 的 `skills/`。
