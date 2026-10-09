# 1.10.0-rc14 原生灯生命周期对照与移除头顶提醒

rc14 是本地候选包，未部署或发布。它保留紫色原生灯对照，同时增加按需重建的资源原始颜色对照，并在每个绘制帧重新启用本 mod 自己的目标灯。这个生命周期差异有已安装头灯控制器的源码依据；它是可证伪的单变量诊断，不代表已找到紫光不可见的根因。红光、紫光或原始资源光在地面上的实际效果仍需用户手动验收。

MOM 的“原生紫色投光对照测试（需头灯资源）”仍默认关闭。打开后，默认配置为颜色 `(1,0,1)`、强度 `7000`；位置、旋转和资源光锥沿用 rc13。新的“资源原始白光对照”默认关闭；打开后，新建的自有 helper 跳过颜色及强度 setter，使用头灯资源预设值。切换模式时只标记状态；下一个绘制同步会释放并重建本 mod 拥有的 helper。每个 world、每种颜色模式的首个成功 helper 各记录一次颜色、强度和位置读回。状态读回不能证明灯已照亮地面。

每个自有目标灯在每个原生探针绘制 tick 至多调用一次 `set_enabled(true)`；新建帧不会重复调用。同步、位置更新和已退场 guide 的清理先于保活。保活只检查自有 helper 对应的当前 impact、已知 catalog 类型和当前类型 epoch；失败会释放该 helper并进入重试等待。没有 guide 时探针不枚举 world 或触碰灯光。关闭开关、world 改变、指引结束及渲染错误仍清理自有灯。其他头灯实例不会被访问或更改；每帧最多创建一个 helper，无 guide 数量上限。

本版移除了头顶的本机 DANGER/PATH? 提醒、对应的 MOM 开关和玩家位置轮询；旧 `warn_player` 保存值会忽略。飞机指示箭头、天空方向箭头、地面走廊、落点菱形及光片保留。本机玩家 pose 仍用于选择六块光片文字朝向，也用于绘制自检；不再用于危险区域提醒。

蓝色支援信标继续不能获得飞鹰走廊；横向战备的用户显示校准仍为总长约 66.67 m、总宽 20 m。该校准不是伤害边界。没有新增 Runtime 依赖、地形查询或活跃 guide 上限；terrain_query/terrain_contract 与 v1.9.10 字节一致。

298 项离线测试通过（`python -m unittest discover -s tests -v`，exit 0）；LuaJIT source gate、package build 与 verifier 均 exit 0。最终 ZIP 含 11 个 Lua 资源，大小 **2,230,967 bytes**，SHA-256 为 `41618773c909c048a44ad74d3dda3b803af0a09f4d64ebbbe6405ee236e51980`。Verifier 确认 ZIP CRC、manifest、11 个源码 payload、封面引用和 terrain_query/terrain_contract 与 v1.9.10 字节一致。详细原始输出在本机外部工作目录 `C:\Users\23825\Desktop\2-apex-x20\work\eagle-rc14-review\`，包括 `final-full-tests.txt`、`validate-only.txt`、`build.txt` 与 `verify-package.txt`。

离线计时不覆盖真实 engine light、GUI 剔除、GPU 或实机 FPS，不能验收实际投光、光片可读性或 0.05 ms/帧目标。用户需手动导入后完全退出并重启游戏；无需进入任务即可在主菜单读取启动 capability 行。实际灯光对照需要用户在游戏中自行开关 MOM 选项并查看地面效果。本地安装包为 `dist/HD2-EagleDirectionProbe-1.10.0-rc14.zip`，SHA-256 校验文件为 `dist/SHA256SUMS-1.10.0-rc14.txt`。
