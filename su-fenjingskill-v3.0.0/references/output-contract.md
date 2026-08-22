# Output Contract｜director-shot-data/3.0.0

本文件只定义导演方案如何保存和导出。它不决定镜头数量、切点、风格或摄影选择。

机器 Schema 位于 [../schemas/director-shot-data.schema.json](../schemas/director-shot-data.schema.json)。自然语言语义以 `SKILL.md` 与各导演 Reference 为准；Schema 只拥有字段类型和基础结构。

Schema 只约束核心字段并允许项目扩展字段。扩展字段不得覆盖来源事实、改变核心字段语义，或被提升为新的前置流程。

## 1. 合同身份

```text
contract_name: director-shot-data
contract_version: 3.0.0
source_skill: su-fenjingskill
source_skill_version: 3.0.0
```

v3 不要求人工 Gate、stage digest、确认语义、screen-event 原子表或计划—终稿双重绑定。

## 2. 顶层结构

```text
contract_name
contract_version
source_skill
source_skill_version
project_id
source
assumptions[]
director_design
scenes[]
shots[]
validation
```


### source

```text
title
delivery_slug
input_kind
locked_text
dialogue_lines[]
```

- `input_kind`：`screenplay | screenplay_segment | locked_fragment | concept_board`。
- `locked_text` 保存本轮依据的原始文本；只规范换行，不改写内容。
- `dialogue_lines[]` 只登记需要逐字保护的实际对白。梗概模式可为空。
- `delivery_slug` 使用 ASCII 小写 kebab-case。无法可靠命名时可用稳定临时 slug，不阻断。

### assumptions[]

只记录影响镜头、连续性、声音或交付的未确认假设。状态为 `open | confirmed | resolved`。

### director_design

保存整段材料的导演策略：

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

这些字段是导演判断，不是从 Schema 机械生成的摘要。多个场景可以在 `scenes[]` 中写场级补充。

### scenes[]

每场至少包含：

```text
scene_id
scene
source_excerpt
space_map
lighting_strategy
color_strategy
```

`space_map` 只记录必要锚点、人物起位、轴线说明和连续性风险；简单场景可保持精简。

### shots[]

每镜至少包含：

```text
shot_id
scene_id
source_excerpt
duration_seconds
duration_basis
motivation
camera
execution_text
notes
```

按需增加：

```text
staging
sound
edit
continuity
```

## 3. 镜头动机

`motivation` 为必需对象：

```json
{
  "primary": "relationship",
  "reason": "让两人继续共享构图，直到其中一人真正越过门线。",
  "cut_or_hold_reason": "关系尚未断裂前不切；越过门线后切开。"
}
```

`primary` 可使用：

```text
information | emotion | relationship | space | subjective | rhythm | transition
```

枚举只用于检索；真正权威是具体 `reason`。不得用通用词替代。

## 4. 摄影对象

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
```

其中 `lighting_change` 可为空字符串，表示继承场级光线策略。

`movement`：

```json
{
  "type": "fixed",
  "trigger": "",
  "speed": "",
  "path": "",
  "end_condition": "",
  "reason": "拒绝追随离开的人，把压力留给原地人物。"
}
```

- 固定镜头需要 `reason`，其他运动需要触发、路径、停止条件和理由。
- `lens_intent` 优先写透视效果，不强制毫米数。
- per-shot 字段可以简洁，不要重复场级策略。

## 5. 对白播放

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

- 同一 `dialogue_id` 的全部片段按镜头顺序拼接，必须与来源 `text` 完全一致。
- `delivery`：`onscreen | os | vo | mediated | unresolved`。
- 对白不必在每个镜头重复全文。

## 6. 连续性与有意违例

`continuity` 只在存在真实风险时填写：

```text
axis
screen_direction
state_updates[]
intentional_breaks[]
```

`intentional_breaks[]` 每项至少包含：

```text
what_breaks
audience_effect
dramatic_reason
reorientation
```

有理由的违例产生导演提示，不由后端自动改正。无理由且造成确定性矛盾时才 FAIL。

## 7. 六列交付

列名和顺序固定：

```text
镜号
场景
原剧本段落
镜头时长
运镜＋主画面描述
备注
```

映射：

- 镜号：`shot_id`
- 场景：`scenes[].scene`
- 原剧本段落：`shots[].source_excerpt`
- 镜头时长：`duration_seconds`
- 运镜＋主画面描述：`execution_text`（完整第五列）
- 备注：`notes`

第五列由 `execution_text` 完整保存，建议写成：

```text
【{景别}｜{角度}｜{运镜}】
【画面内容】初始画面 → 镜内动作／调度／焦点／摄影机／声音变化 → 结束画面
```

`execution_text` 应自然包含：

- 初始画面和相对机位。
- 人物调度、动作、表演和对白。
- 焦点、摄影机、光线或声音变化。
- 结束画面或切点状态。

不得显示内部枚举、ID、验证状态或逐字段模板。

## 8. 正式文件

默认文件名：

```text
{delivery-slug}-shot-data.json
{delivery-slug}-storyboard.md
{delivery-slug}-storyboard.xlsx
{delivery-slug}-storyboard-validation.json
```

- JSON 是结构化载体，不是创作上位规则。
- Markdown 是最低可用人类交付。
- XLSX 为生产表格；导出失败时其他文件照常交付。
- validation report 记录确定性错误、WARN、假设和缺失工具。

## 9. 校验边界

后端可以 FAIL：

- JSON 无法读取。
- 来源为空。
- 合同身份不正确。
- 镜头引用不存在的场景。
- 镜头 ID 重复或无有效执行正文。
- 对白片段拼接后与来源不一致。
- 来源明确对白被翻译、改写或重复。
- 非固定运镜缺少基本执行路径。
- 有意连续性违例没有任何理由。

后端只 WARN：

- 存在开放假设。
- slug 为临时值。
- 极短镜、长镜或高比例固定／同角度。
- 动机过于通用或多个镜头重复同一理由。
- 空间、声音、焦点或时长需要人工复核。
- XLSX 或可选工具不可用。

以下不由后端判定艺术错误：

- 同一角度、焦段、景别或固定镜头比例较高。
- 镜头数量多或少。
- 是否采用长镜、正反打、共享构图或主观镜。
- 越轴是否值得。
- 表演是否克制、准确或俗套。
- 构图和光线是否具有审美价值。

## 10. 构建状态

- `READY`：无错误或开放假设。
- `READY_WITH_ASSUMPTIONS`：有 WARN、开放假设或可选导出失败。
- `FAIL`：存在确定性来源、结构、对白或执行矛盾。

默认构建即使 FAIL 也尽量写出 Markdown、JSON 副本和 validation report，便于人工修复。使用 `--strict` 时才停止生成衍生文件。

## 11. CLI

```text
python scripts/storyboard_delivery.py validate --input <shot-data.json>
python scripts/storyboard_delivery.py build --input <shot-data.json> --output-dir <目录>
python scripts/storyboard_delivery.py build --input <shot-data.json> --output-dir <目录> --strict
python scripts/export_xlsx.py --input <shot-data.json> --output <storyboard.xlsx>
python tests/test_storyboard_delivery.py
```

`storyboard_delivery.py` 只负责 JSON、Markdown、validation 和后端校验；XLSX 独立导出，失败不影响导演方案。
