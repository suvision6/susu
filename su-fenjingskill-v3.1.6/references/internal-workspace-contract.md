# Internal Workspace Contract｜director-workspace/3.1.6

`director-workspace/3.1.6` 是来源、Gate 0、导演工作和正式 readiness 的内部事实载体，不是第五个正式交付文件。机器结构唯一权威是 [director-workspace.schema.json](../schemas/director-workspace.schema.json)。

## 顶层

```text
workspace_contract
source
format_brief
gate_0
supplemental_reference_facts[]
assumption_obligations[]
director_method
gate_1
scene_strategies[]
shot_bindings[]
director_inferences[]
approval_events[]
review_lock
```

## Gate 0

`format_brief` 保存节奏预设、目标成片时长、画幅、方向、`su-dialogue-pace/1.0` 固定区间／选值／overrides 和覆盖倾向。`gate_0` 保存当前 `format_hash`、状态与确认说明。非 custom 区间不匹配内部标准、选值越界或 override 理由空泛时不得确认 Gate 0。

Schema 使用 `additionalProperties: false`；扩展必须先修改合同和校验器，不能静默塞入未知字段。

## source ledger

`source` 必须包含：

```text
locked_text
source_hash
authority_policy
scopes[]
source_units[]
classification_reviews[]
source_gaps[]
source_passages[]
source_facts[]
```

- `source_units[]` 对 `locked_text` 每个非空行做一次 exact accounting。
- 非空行默认参与叙事完整性；只有机械可识别的页码、项目元信息和分隔线可自动归为 metadata。
- 场景标题、转场和非叙事分类必须与原始文字形式相符；疑似动作或对白即使伪造分类审批也不能降级。
- 人工分类例外必须保存 `classification_review`，其 hash 覆盖 decision、status、reason、source text hash 和 reviewer。
- `source_passages[]` 形成完整可显示的第三列来源段落，不决定镜头切点。
- 每个权威叙事 unit 必须至少有一个 required fact；受保护类型不得降为 supporting。
- fact 的 `source_span` 与 anchors 必须有语义长度并真实落在来源 unit 中，不能用无意义单字代替命题证据。

## supplemental reference facts

每条补充事实必须有稳定 RF ID、statement、source excerpt、source hash、provenance、approval status/note 和 approval hash。approval hash 包含审批状态与说明，因此从 pending 改为 approved 必须改变哈希。

正式推断只能引用 `approval_status=approved` 且所有哈希有效的补充事实。

## source gaps 与 assumption obligations

概念材料或缺失参考形成 `source_gaps[]`。每个 gap 必须由一条 `assumption_obligation` 关闭：

```text
assumption_required
或
supplemental_source_confirmed
```

- `assumption_required` 必须绑定一个正式 `assumptions[]` 项。
- `supplemental_source_confirmed` 必须绑定已批准、哈希有效的补充事实。
- 一个正式 assumption 只能关闭一个 gap。
- 删除 gap ledger、obligation 或 formal assumption 会使来源模型或 Alignment 失效；不能把 `READY_WITH_ASSUMPTIONS` 洗成 `READY`。

## shot bindings

每个正式镜头必须绑定至少一个权威 passage。`fact_realizations[]` 保存 fact、实现方式、精确 execution 片段、主体 owner、结果片段和 polarity。

主体绑定使用精确 entity label 或明确所有格身体／声音部位，不允许字符串包含匹配。例如“林”不能匹配“树林”。否定检测覆盖行中结构，不只检查行首。

## director inferences

层级固定为：

```text
locked source facts
→ approved supplemental reference facts
→ approved director inferences
→ open assumptions
```

正式镜头只能引用 `status=approved` 的 inference。`inference.shot_refs` 与 `shot_bindings[].director_inference_ids` 必须双向完全一致。`proposed`、`rejected` 或 `confirmation_required` 推断不得进入正式镜头。

## scene strategies 与 topology

每个 topology unit 必须：

- 只包含当前 strategy.scene_id 的 shot；
- 每个正式 shot 恰好出现一次；
- `source_passage_ids[]` 等于其 shot bindings 的 passage 并集；
- `source_fact_ids[]` 等于其 fact realizations 的 fact 并集；
- 与 shot binding 双向一致，而非只检查引用对象存在。
- 保存 `viewing_design`：画面 owner、画内／画外主体、读取尺度、framing intent、camera response 和当前事件理由；并与正式 viewpoint/camera/staging 双向一致。
- 保存 `dialogue_edit_plan[]`：每个来源对白恰好一次，逐字 picture steps 与 topology／正式对白双向一致；同 unit 继续不切必须有新的可见发展。
- viewing design 的 `frame_axis / aspect_ratio_fit` 与正式 camera 的画框轴向和画幅理由双向一致。
- 非末 unit 必须且只允许一个 `boundary_to_next`，包含 `relation`、具体 `trigger` 与相对继续不切的 `editorial_gain`；末 unit 不保存边界。

每场 N 个 topology units 必须恰有 N−1 个边界。旧版四段式 boundary reason 不进入 3.1.3。

每个 scene strategy 还必须保存 `camera_grammar`：dominant principle、具体 change triggers、首尾 progression 与按需 uniformity intent。整场 framing、角度、运动和 owner 全部同质时，缺少具体 uniformity intent 会阻断 Gate 2；跨单元复用同一观看／摄影理由会触发 `CAMERA_DECISION_TEMPLATE_COLLAPSE`。这不是摄影类别配额。

## review lock 与 approval events

`review_lock` 保存：

```text
source_hash
source_model_hash
method_hash
strategy_hash
topology_hash
execution_hash
alignment_hash
Gate 1 / Gate 2 / Alignment 状态与说明
```

camera grammar、viewing design 或 topology 变化使 Gate 2 与 Alignment 失效；正式 viewpoint、framing、visibility、景别、角度、运动和 shot flow 变化只使 Alignment 失效。

format brief 变化使 Gate 0、Gate 1、Gate 2 与 Alignment 全部失效；dialogue edit plan 变化使 Gate 2 与 Alignment 失效；正式 timing plan 或画幅执行变化只使 Alignment 失效。

`approval_events[]` 保存对应内容哈希的显式状态转换和事件哈希链。`lock` 只重算并按唯一依赖矩阵作废旧审批；不会自动批准任何 Gate 或 Alignment。3.1.6 继续对对白、观看、摄影和切点理由先移除 ID、镜号、单元号、复述台词与固定尾句再比较，并增加整秒镜长与超短镜证据校验；继续不切的画内发展还必须在正式执行字段中找到证据。

## 正式边界

只有 workspace Schema PASS、Gate 0 confirmed、来源对齐 PASS、Gate 2 confirmed、Alignment passed 且对应确认事件匹配当前内容哈希，才能进入正式 `build-all`。workspace 不进入正式 XLSX，不增加工作表，不成为正式第五文件；风险、安全与治理内容也不进入创作流程或四文件。
