# Output Contract｜director-shot-data/3.1.4

本文件只定义正式导演分镜如何保存、验证和导出。它不决定镜头数量、切点、风格或摄影选择。

机器结构唯一权威是 [director-shot-data.schema.json](../schemas/director-shot-data.schema.json)。运行时必须先执行该 Schema；手写校验器只处理跨字段语义，不复制 required-field 规则。Schema 使用 `additionalProperties: false`，未知字段不得静默进入正式合同。

## 1. 合同身份

```text
contract_name: director-shot-data
contract_version: 3.1.4
source_skill: su-fenjingskill
source_skill_version: 3.1.4
```

内部来源台账、事实、镜头绑定、Gate 和确认事件属于 `director-workspace/3.1.4`，不进入正式数据文件。3.1.3 只能通过显式迁移生成新目录中的 3.1.4 draft，不能只改版本字符串。

## 2. 顶层结构

```text
contract_name
contract_version
source_skill
source_skill_version
project_id
source
format_brief
assumptions[]
director_design
scenes[]
shots[]
validation
```

### format_brief

正式保存 Gate 0 已确认的 `rhythm_profile`、`target_runtime_seconds`、`aspect_ratio`、`orientation`、`dialogue_pace`、`coverage_bias` 和确认说明。`dialogue_pace` 包含 `standard_id`、`rate_basis`、固定 range、default、selected CPS、强弱停顿与 `overrides[]`；它与 workspace 中的 Gate 0 事实必须逐字一致。

### source

```text
title
delivery_slug
input_kind
locked_text
dialogue_lines[]
```

- `input_kind`：`screenplay | screenplay_segment | locked_fragment | concept_board`。
- `locked_text` 只规范换行，不改写内容。
- `dialogue_lines[]` 只登记需要逐字保护的实际口播。
- `delivery_slug` 使用 ASCII 小写 kebab-case。

### assumptions[]

每项必须包含稳定 ID、scope、statement、reason、impact 和 `open | confirmed | resolved` 状态。正式假设必须由 workspace 中独立的 assumption obligation 持有；删除或清空本数组不能消除来源缺口。

### director_design

固定保存：

```text
scene_purpose
dramatic_question
turning_point
audience_position
pov_strategy
emotional_arc
blocking_strategy
visual_strategy
sound_strategy
rhythm_strategy
```

### scenes[]

每场包含：

```text
scene_id
scene
source_excerpt
space_map
lighting_strategy
color_strategy
```

### shots[]

每镜包含：

```text
shot_id
scene_id
source_excerpt
duration_seconds
duration_basis
timing_plan
motivation
viewpoint
camera
staging
sound
edit
continuity
execution_text
shot_flow[]
notes
```

正式合同不接受未声明的镜头级或场级扩展字段。

## 3. 后端事实与前端投影

结构化 shot model 是唯一后台事实源。`execution_text` 由以下字段确定性渲染，供 JSON、Markdown 与 Agent 查询：

```text
camera
staging
sound
edit
continuity
motivation
duration
```

`shot_flow[]` 使用受限 owner 引用上述字段，数组顺序是镜内动作、对白、声音、焦点、运镜与结束状态的时间顺序。它不保存第二份自由正文。XLSX 第五列由 camera、shot_flow 与对白索引确定性投影，不得直接复制后台 `execution_text`。

每个 flow item 只有：

```text
owner
index?  # dialogue_segment / effect / state_update
span?   # blocking / performance / ambience / focus / edit_exit 的逐字子串
```

`camera_setup` 与 `movement` 直接引用结构对象，不使用 index/span。未提供 span 时表示引用整个字符串。正式构建要求 flow 非空、owner 合法、引用存在、span 逐字、对白片段恰好一次且顺序不变；非固定运动必须在 flow 中恰好出现一次。

### viewpoint、framing 与画内外主体

每镜必须保存：

```text
viewpoint.owner_type / owner_refs[] / reading_priority / camera_response / reason
camera.framing_mode / primary_subjects[] / foreground_subjects[]
camera.shot_size_reason / angle_reason / frame_axis / aspect_ratio_reason
staging.visible_subjects[] / offscreen_subjects[]
```

`staging.subjects[]` 是场内参与者；具名人物必须明确进入 visible 或 offscreen，二者不得重叠。`onscreen` 对白的说话者必须可见，`os` 说话者必须在画外。single／two_shot／group 按主要可见人物数验证；over_shoulder 必须有分离的前景与主要主体；insert 必须读取物件或身体细节。正式执行必须与 Gate 2 的 viewing design 一致。

`unresolved` 和空值只允许承载迁移 draft；正式 validate/build 以 `CAMERA_DESIGN_UNRESOLVED` 阻断。

## 4. 镜头动机与摄影对象

`motivation`：

```json
{
  "primary": "relationship",
  "reason": "让两人继续共享构图，直到其中一人真正越过门线。"
}
```

`primary` 可使用：

```text
information | emotion | relationship | space | subjective | rhythm | transition
```

`camera` 至少包含：

```text
shot_size
angle
position
composition
lens_intent
movement
focus
lighting_change
framing_mode
primary_subjects
foreground_subjects
shot_size_reason
angle_reason
```

`shot_size` 只允许以下规范中文词：

```text
大远景 | 远景 | 中远景 | 全景 | 中全景 | 中景 | 中近景 | 近景 | 特写 | 大特写 | 极特写
```

镜内真实景别变化用 `→` 连接，例如 `中景→近景`。`unresolved` 只允许迁移草稿；“紧中景”等非标准词触发 `SHOT_SIZE_TERM_NONSTANDARD`。

非固定运动必须说明触发、速度、路径、停止条件和理由；固定镜头也必须说明为什么拒绝响应当前动作。

`frame_axis` 必须与 Gate 2 viewing design 一致；`aspect_ratio_reason` 说明当前构图或运动如何使用 Gate 0 画幅。“适配画幅”等空泛理由不能正式构建。

## 5. 结构化时长

每镜 `timing_plan` 包含 `status`、`blocks[]`、计算总时长、置信度与依据。正式镜头只允许 `status=ready`；每个 block 的 `pace_ref` 必须指向 `BASE` 或一个已登记且 scope 匹配的 `POxxx` override。

每个 block 用 flow 起止索引无缝覆盖 `shot_flow`，并保存 dialogue/action/camera/sound/reaction/hold 六个时间分量：

- `parallel`：`computed_seconds` 等于六项最大值；
- `sequential`：`computed_seconds` 等于六项之和；
- 全部 blocks 之和等于 `computed_duration_seconds`；
- `computed_duration_seconds` 等于正式 `duration_seconds`。

中文 dialogue seconds 从 pace_ref 对应的选定字速与标点停顿参数重算。基础字速口径固定为排除停顿的 articulation rate，防止二次叠加停顿。动作、摄影、声音和反应的人工估值必须与对应 flow owner 同时存在；不能用自由文字或无事件停顿填充镜长。

## 6. 对白播放

来源对白：

```json
{
  "dialogue_id": "D001",
  "speaker": "A",
  "text": "我明天走。",
  "voice_type": "scene_dialogue"
}
```

镜头内片段：

```json
{
  "dialogue_id": "D001",
  "text": "我明天走。",
  "delivery": "os"
}
```

同一 `dialogue_id` 的全部片段按镜头顺序拼接，必须逐字等于来源文本。`delivery` 为 `onscreen | os | vo | mediated | unresolved`，不能改变来源声音身份。

## 7. 连续性与备注

`continuity` 包含：

```text
axis
screen_direction
state_updates[]
intentional_breaks[]
```

有意违例必须说明：`what_breaks`、`audience_effect`、`dramatic_reason`、`reorientation`。后端不以镜头比例或越轴本身判艺术失败，但会阻断无理由且造成确定性矛盾的状态。

`notes` 默认空，只允许：

- 会改变当前镜头决策的真实待确认项；
- 已说明理由和重新定向方式的连续性例外。

本合同不建立现场筹备管理字段、独立章节、关键字路由或校验分支。此类信息应在分镜合同之外另行管理，不自动搬入备注。

## 8. XLSX 人类前端

固定列名和顺序：

```text
镜号 | 场景 | 原剧本段落 | 镜头时长 | 运镜＋主画面描述 | 备注
```

映射：

- 镜号：`shot_id`
- 场景：`scenes[].scene`
- 原剧本段落：`shots[].source_excerpt`
- 镜头时长：`duration_seconds`
- 运镜＋主画面描述：由 camera、shot_flow 与对白索引生成的 XLSX projection
- 备注：`notes`

第三列不是模型摘要。`build-all` 根据 workspace 的权威 passage 与 locked text 确定性派生；同一 passage 多镜可重复完整显示，多个 passage 用空行连接，不添加省略号或改写。

第五列固定为：

```text
【角度，景别，运镜】
【画面内容】一个按 shot_flow 实际发生顺序写成的自然段
```

逐字对白显示角色名，不显示 dialogue ID。camera setup 必须自然体现单人、双人、群像、过肩、插入、主观或空间构图，以及主要／前景／画外关系。特殊画外／介质声音、非固定运镜、焦点或状态变化只在 flow 引用时出现；固定镜头不显示拒绝运动的理由。不得出现后台六段标签、Gate、Alignment、哈希、Fact/Dialog ID、普通轴线证明、空值或风险治理文字。

“导演设计”保持十个全剧摘要维度。真实待确认项以 statement 与 impact 的自然语言显示，不展示 assumption ID 或状态枚举。

第五列减冗校验包括：机位不得复述摄影头中的角度或景别；构图不得包含已经由 blocking／performance／effect／ambience／focus／edit_exit 投影的同一事件；同镜不同 flow owner 不得互相包含同一段正文；同场完全相同的普通 ambience、focus 或 edit_exit 不得重复进入 XLSX。普通稳定事实仍保存在 JSON／Markdown 后台。该规则检查重复来源，不设置通用字符数上限。

标题区第二行增加 Gate 0 的自然语言摘要：`画幅｜节奏｜对白速度｜共 N 镜｜总时长 T 秒`。timing blocks、Gate 和内部 ID 不进入 XLSX。

## 9. 固定四文件与原子事务

```text
{delivery-slug}-shot-data.json
{delivery-slug}-storyboard.md
{delivery-slug}-storyboard.xlsx
{delivery-slug}-storyboard-validation.json
```

XLSX 固定只有“导演分镜”和“导演设计”两张工作表。

正式入口只有：

```bash
python -m scripts.storyboard_delivery build-all \
  --input <shot-data.json> \
  --workspace <director-workspace.json> \
  --output-dir <empty-or-absent-directory>
```

执行顺序固定为：

```text
Schema
→ 来源与审批语义校验
→ staging 生成 JSON
→ 生成 Markdown
→ 生成 XLSX
→ 三载体同源事实与 XLSX projection parity 校验
→ 计算三个文件 SHA-256
→ 最后写 validation
→ 原子提交整个目录
```

任一步骤失败都删除 staging；正式目录保持不存在或为空，不允许留下 READY validation 与残缺文件组合。已有非空目标目录一律拒绝覆盖。

## 10. 校验边界

后端硬失败包括：

- 正式或 workspace Schema 不合法；
- 来源为空、合同身份错误或 workspace 缺失；
- 来源 unit 漏失、重复、不当降级、scope/authority 错误；
- required fact 无实现，或主体、结果、否定、因果错绑；
- topology 与 scene、passage、fact 或 shot binding 不一致；
- 正式镜头引用未批准推断；
- Gate、Alignment 或其审批事件不匹配当前内容哈希；
- canonical execution text 与结构化 shot model 不一致；
- 对白被改写、重复、倒序或物理上不可播放；
- 非固定运动缺少基本执行路径；
- 有意连续性违例没有理由；
- JSON、Markdown、XLSX 或 validation 构建／parity 失败；
- shot_flow 缺失、引用失效、对白缺失／重复／乱序，或 XLSX projection 与 camera/flow 不一致。
- viewpoint、framing、可见性、对白画内外、camera response 与 Gate 2 viewing design 不一致；
- Gate 0 未确认、format brief 前后端不一致、画幅方向矛盾或画幅应用理由空泛；
- dialogue edit plan 漏句、重复、乱序、逐字片段不完整、与 topology/正式画面不一致，或用无新可见发展的 O.S. 留镜吞掉换人对白；
- timing blocks 未覆盖 shot_flow、并行／顺序公式错误、对白重算不一致或正式镜长不等于时间块总和；
- 景别不是规范中文词，或使用“紧中景”等边界不清的自造术语；
- XLSX 机位复述摄影头、构图复述动作、flow owner 换字段重复同一事件、模板焦点进入前端，或同场普通环境／焦点／出口重复投影；
- 极端同质摄影缺少已确认的 uniformity intent，或跨单元摄影理由模板坍缩。

后端 warning 包括：

- 存在开放假设；
- slug 为临时值；
- 非空备注需要人工确认其必要性。

后端不以景别、角度、运动、固定镜头比例、镜头数量、长镜、正反打、共享构图、蒙太奇、跳切或越轴本身判艺术失败。

## 11. 状态与退出码

- `READY`：确定性结构、来源、审批、Alignment 与四文件 parity 全部通过，且无开放假设或 warning。
- `READY_WITH_ASSUMPTIONS`：仍有明确开放假设；默认退出码为 0。
- `FAIL`：存在确定性阻断；退出码为 1。
- JSON 读取、依赖或 I/O 异常可返回退出码 2。

CI 需要把 warning 当失败时使用 `--fail-on-warn`。

## 12. 相关 CLI

```bash
python -m scripts.storyboard_delivery structure-validate --input <shot-data.json>
python -m scripts.storyboard_delivery validate --input <shot-data.json> --workspace <workspace.json>
python -m scripts.storyboard_delivery build-all --input <shot-data.json> --workspace <workspace.json> --output-dir <directory>
python -m scripts.storyboard_review validate --workspace <workspace.json> --shot-data <shot-data.json>
python -m scripts.storyboard_review confirm-gate0 ...
python -m scripts.storyboard_review status --workspace <workspace.json> --shot-data <shot-data.json>
python -m scripts.migrate_contract_3_1_0_to_3_1_2 --shot-data <historical.json> --output-dir <empty-directory>
```

`export_xlsx.py` 仅保留为经过同一 preflight 的开发／兼容工具；它不是正式四文件流程的第二阶段。
