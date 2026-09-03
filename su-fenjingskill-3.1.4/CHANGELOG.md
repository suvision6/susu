# Changelog

## 3.1.4 — projection-quality-02

- 真实 EP02 回归发现机器 parity 可通过但第五列仍可能过密；新增前端重复来源阻断，不设置通用字数上限。
- 机位不得复述摄影头中的角度／景别，构图不得复制动作，不同 flow owner 不得换字段复述同一事件。
- 同场完全相同的普通环境、焦点或结束说明重复进入 XLSX 时触发 `XLSX_PROJECTION_REPEATED_OPTIONAL_FLOW`；模板焦点触发 `XLSX_PROJECTION_NONESSENTIAL_FOCUS`。
- 新增规范中文景别词表和 `SHOT_SIZE_TERM_NONSTANDARD`；“紧中景”等非专业转写不能正式构建，镜内变化使用 `中景→近景`。
- 3.1.3 迁移遇到非规范景别时改为 `unresolved` 并列入重建报告，不猜测替换。

- 新增内部语速标准 `su-dialogue-pace/1.0`：短剧 4.3–5.5、平台剧 3.3–4.3、短片 2.3–3.3、长片 2.7–3.7 字/秒，并锁定默认值与强弱停顿范围。
- Gate 0 必须保存标准区间、默认值和最终选值；超出范围只允许通过有 scope 和具体表演理由的 pace override。
- timing block 新增 `pace_ref`，保证每段对白使用 BASE 或 scope 匹配的明确 override 重算；字幕 CPS 不参与口播时长。
- 新增拆镜前 Gate 0：确认剪辑节奏预设、目标成片时长、画幅、方向、对白速度和覆盖倾向。
- 新增 `dialogue_edit_plan`，逐句覆盖来源对白，并把 `establish | cut | hold | reframe`、切点相位和新增画内发展绑定到 topology。
- 新增 `MISSED_DIALOGUE_VIEW_CHANGE` 与 `DIALOGUE_HOLD_TEMPLATE_COLLAPSE`，发现没有新画内价值却长期停在同一人物的 O.S. 留镜。
- viewing design 与正式 camera 增加 frame axis 和画幅适配；9:16 不禁横移，但要求窄画框中的具体收益。
- 新增结构化 `timing_plan`：时间块无缝覆盖 shot_flow，并行取最长、顺序相加；中文对白按 Gate 0 参数重算。
- XLSX 保持两张表和六列，标题区增加画幅、节奏和对白速度摘要，timing blocks 只留在 Agent 后端。
- 新增非覆盖 `3.1.3 → 3.1.4` 迁移器；所有新字段保持 unresolved，四阶段全部失效。

## 3.1.3 — camera-grammar-01

- 标记并归档未安装的 `frontend-backend-split-01`；其前后端分离保留，但不再作为导演质量完成证据。
- Gate 2 每个 topology unit 新增 viewing design，明确画面 owner、可见／画外主体、读取尺度、framing 与摄影机响应。
- scene strategy 新增 camera grammar，组织整场观看变化并要求极端同质摄影具有具体统一理由。
- 正式 shot 新增 viewpoint；camera 增加 framing、主要／前景主体及景别／角度理由；staging 增加可见／画外主体。
- 增加对白画内外、framing cardinality、Gate 2／正式执行对齐、camera response 和理由模板坍缩检查。
- 不设置单人镜头、景别、角度或运镜配额；周期轮换类别不能冒充导演设计。
- EP02 回归必须只读取原始 locked text，重新执行 Gate 1 与 Gate 2，不继承旧 14 镜、SHOT_META 或摄影数据。

## 3.1.3 — 前后端分离

- 正式与内部合同同步升级为 `director-shot-data/3.1.3`、`director-workspace/3.1.3`。
- 保留完整后台 `execution_text`，新增有序 `shot_flow`，使镜内动作、对白、声音、焦点与运镜顺序可确定性投影。
- XLSX 成为唯一人类阅读前端；第五列改为 `【角度，景别，运镜】` 加单段 `【画面内容】`，不再复制后台六段字段。
- 两张 XLSX 工作表和固定六列保持；“导演设计”继续使用全剧摘要，待确认项只显示自然语言。
- Gate 2 切点收敛为 `trigger + editorial_gain`；切点理由只证明一次，不在终稿重复。
- `READY_WITH_ASSUMPTIONS` 只表示真实开放假设，不再由镜长、角度比例或普通构建提示触发。
- 增加显式 3.1.2→3.1.3 draft 迁移；不覆盖历史输出，迁移后所有 Gate 与 Alignment 重新确认。
- 风险、安全和治理内容不进入创作流程与四文件；技术一致性、原子构建和版本回滚检查保留。

## 3.1.2 — P0 repair revision `p0-repair-01`

版本号保持 3.1.2；本修复不改变六列、四文件或两张 XLSX 工作表。

- 将 JSON Schema 接入正式运行时，并收紧为 `additionalProperties: false`。
- 来源行默认按叙事处理；非叙事例外需要机械判定或独立分类审批。
- 补充行中否定、精确实体归属、fact span/anchor 和 required ownership 校验。
- 执行锁覆盖 camera、staging、sound、edit、continuity、duration、motivation、assumptions、notes、canonical execution text 与来源绑定。
- 第五列改为 canonical renderer 的确定性结果，不允许与结构化字段双写分叉。
- 增加 source gap / assumption obligation，阻止删除假设后伪装 READY。
- topology 强制 scene、passage、fact 与 shot binding 双向一致。
- 正式镜头只允许引用已批准 inference。
- Gate 1、Gate 2、Alignment 使用唯一失效矩阵和显式审批事件。
- 正式四文件改为单一 `build-all` 原子事务，validation 最后写入。
- `READY_WITH_ASSUMPTIONS` 默认退出码改为 0；增加 `--fail-on-warn`。
- XLSX 统一为 openpyxl 单一 writer。
- 删除当前合同中的现场筹备管理子系统、字段、导出区块、关键字路由和评测用例。

## 3.1.2 — original candidate

- 引入 source units、passages、facts、shot bindings、Gate 2 与固定四文件合同。
- 同步正式和内部合同版本为 3.1.2。

## Earlier versions

旧版本保留在历史仓库中；本包不把历史行为作为当前规则。
