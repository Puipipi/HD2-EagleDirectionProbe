# 1.10.0-rc15 地形贴合与透视轮廓候选

rc15 延续 rc14 的紫光投光与资源原始白光对照。紫光仍不可见的原因尚未定位；本版没有改变颜色、强度、旋转或资源光锥。头顶 DANGER/PATH? 本机提醒及其轮询已经移除，飞鹰箭头、天空方向箭头、地面走廊、落点菱形和文字光片仍保留。玩家姿态解析仍用于文字观察侧选择与绘图自检。

地面边带和条带顶点现在沿用缓存 terrain grid 的轴向采样站点，并保留显示范围端点。mesh 能在已采样站点处表达地形窄峰，不发起额外碰撞查询。轴向边带外的图形仍由原来的高度插值生成；网格插值不能表示查询点之间未采到的地形细节。查询仍最多每帧两次、沿用 0.5 ms 软预算；计划网格只在类型、参考范围或自适应设置变化时重建。

“透视显示”关闭时，主线段请求深度测试，填充沿用原有 world GUI 绘制，并且不提交额外透视轮廓。开启时保留 GUI 填充和主线段，并增加独立的无深度测试虚线轮廓通道；该通道仅含组件外轮廓及原有非填充线，不含填充面、三角形内部对角线、扫描填充线或文字字形碎边。文字仍保留在正常可见绘制中。选项切换会重建相关地面几何缓存；关闭、world 切换和清理会释放第二条线对象。离线测试验证了线段参数通道、轮廓过滤、缓存和对象生命周期。

以上是传给引擎的绘制策略。Stingray retained GUI 的深度比较和 pass 排序没有离线像素 oracle，因此“透视关闭后遮挡图形完全隐藏”与“透视开启后只有被挡边界显示虚线”仍需实机确认；本说明不将其称为已验证的像素行为。没有增加按图元 raycast，也没有降低真实填充或裁剪有效 guide。

性能状态行新增“guide work”分桶：一帧在开始或结束时有指引几何或自有投光对象就纳入。它汇总完整 guarded Lua 工作与 draw 的均值、样本数和峰值；这个口径不代表屏幕像素可见、GPU 时间或帧率。

最终 72-run 配对离线基准（1/4/8 个确认 guide）报告三次运行均值的中位数。透视关闭时，rc14 中位耗时为 0.0642/0.2457/0.4708 ms/frame，rc15 为 0.0846/0.2969/0.5065 ms/frame，回退约 8–32%。透视开启时 rc15 中位耗时为 0.2631/0.8352/1.7510 ms/frame；rc14 开启透视会强制旧线段回退，而 rc15 保留 GUI 填充并增加轮廓，因此负载不同，不比较比例。以上是离线 Lua/native-mock 测量，不覆盖完整游戏 pose/native/GPU，也不证明实际可见性；0.05 ms/frame 目标尚未达到。

RC14 的原生投光和资源原始白光模式、每绘制帧保活、白光/紫光自有 helper 读回、每帧最多创建一个 helper、无 guide 数量上限继续保留。它们是诊断对照，不代表灯光一定照到地面。真实照明、透视像素和标签可读性只能由用户手动在游戏中验收。

验证结果：`python -B -m unittest discover -s tests -v` 为 330 项通过（exit 0）。`python -B work/standalone/build_probe.py --validate-only` 与 `python -B work/standalone/build_probe.py` 均 exit 0；13 个 Lua 资源分别通过 LuaJIT 2.1 编译、声明名匹配和 `ffi.cdef` 不含 `user32` 检查，构建另通过 archive 中无脚本文件门禁。`python -B work/standalone/verify_package.py` exit 0：ZIP CRC、manifest、13 个 source payload 与 cover 校验通过；两个 terrain native 资源与 v1.9.10 字节一致。候选 ZIP 为 2,237,125 字节，SHA-256：`984fea68052189d08b46c24338be42410aac1dcdc153754cea60e6391a4cdf58`。测试日志为 `work/eagle-rc15-progress/final-full-tests-rc15.txt`；最终包文案修正后的构建与校验日志为 `build-rc15-docfix.txt`、`verify-package-rc15-docfix.txt`。没有 HD2Runtime 依赖。
