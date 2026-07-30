# Output Contract

本文件是 `shot-data/2.5.1`、两 Gate digest、屏幕事件、观看决策、DOP 视觉规划、六列渲染、文件名、CLI 与 validation report 的唯一规则源。

## 1. 合同身份与顶层结构

正式身份固定为 `contract_name=shot-data`、`contract_version=2.5.1`、`source_skill=su-fenjingskill`、`source_skill_version=2.5.1`。

顶层允许字段为：

```text
contract_name
contract_version
source_skill
source_skill_version
project_id
content_hash
confirmations
source
source_analysis
director_style_options
selected_style_option_id
director_profile
screen_events
shot_plan
scenes
beats
emotion_arcs
performance_chains
shots
```

其中 `director_style_options`、`selected_style_option_id`、`emotion_arcs` 与 `performance_chains` 为按需字段。2.5.1 新生成不为填空而输出空分析结构。

`project_id` 以 ASCII 字母或数字开头，只含字母、数字、点、下划线或短横线。

`content_hash` 对删除自身后的完整 JSON 使用 UTF-8、`sort_keys=true` 和紧凑分隔符生成 canonical JSON，再计算 64个小写十六进制字符的 SHA-256。构建器负责写入；draft 可留空。

## 2. 两项人工确认与 digest

`confirmations` 必须恰含 `gate_1` 与 `gate_2`，每项恰含：

```text
status
stage_digest
confirmation_order
notes
```

- `status` 在正式交付中必须为 `confirmed`。
- `confirmation_order` 对 Gate 1 为 `1`，对 Gate 2 为 `2`。
- `stage_digest` 是 64个小写十六进制字符的 SHA-256。
- confirmation 对象中的 `notes` 是普通字符串，只记录确认语境；它与六列表格的镜头备注列无关。
- 不保存 `confirmed_by`、用户 ID、签名或其他身份字段；合同不声称认证用户身份。

Gate 1 canonical payload 恰含当前：

```text
source
source_analysis
director_profile
```

实际展示候选时，再加入 `director_style_options` 与 `selected_style_option_id`。默认候选必须是连续的 `STYLE-01` 至 `STYLE-03`；从更多索引展开一个候选时增加 `STYLE-04`。发现阶段的 `MORE-*` 不进入合同或 digest。用户明确指定导演时可省略候选数组与选择 ID。

候选 `rationale` 固定包含“适配依据、时间与剪辑、摄影机、空间与调度、表演与观看、主要收益、主要风险”七段。用户选择候选不等于确认；只有最终 profile 展示后的明确“确认”才能生成有效 Gate 1 digest。

Gate 2 canonical payload 恰含：

```text
gate_2_rule_revision
gate_1_digest
scene_plans
screen_events
shot_plan
visual_design
director_readiness
```

`gate_2_rule_revision` 固定为 `2.5.1-cut-atomicity-r2`。`scene_plans` 是 `scenes[]` 的派生字段；原子事件字段、`non_cut_basis`、长镜保护范围、节奏指标、`shot_plan`、DOP 字段、`visual_design` 与 `director_readiness` 全部进入 Gate 2 digest。计算前统一规范化 `locked_text`、源 hash 与全部 span hash。任何相关内容或规则修订号变化都会使旧 Gate 2 确认失效。

脚本公开 `stage_digest(data, 1 | 2)` 供 Gate 阶段计算。构建器只验证用户已经明确确认的 digest，绝不自动改写 digest 以越过 Gate。

## 3. 拆镜规划合同

每个 scene 必须有 `directing_plan`。必需字段：

```text
scene_objective
progression[]
pov_flow[]
entry_strategy
style_anchors[]
```

只在场景需要时增加：

```text
entry_state
exit_state
rhythm_curve[]
dialogue_geometry
protected_processes[]
visual_turns[]
```

该对象表达整场导演判断，不证明表格填写完整度。核心目标、推进、视点或风格锚点缺失为 FAIL；其他维度按场景需要使用。

每个 `style_anchors[]` 恰含：

```text
style_anchor_id
profile_basis[]
scene_application
avoidance
```

`style_anchor_id` 是全片唯一的 `SAxxx`。每个 `profile_basis[]` 项恰含 `field + value`，必须与 Gate 1 已确认 `director_profile` 的对应闭合轴、`transition_language`、`priorities` 或 `natural_language_intent` 完全匹配。`scene_application` 说明该场具体执行方式；`avoidance` 说明应避免的表面化模仿。

`entry_strategy` 必须恰含：

```text
mode
observer_position
required_spatial_information[]
withheld_information[]
reason
```

`mode` 只允许：

```text
spatial_establish
relational_entry
character_entry
subjective_entry
deliberate_withhold
```

- `spatial_establish`：先建立后续叙事所依赖的环境、方向或空间轴线。
- `relational_entry`：先建立人物之间及人物与环境之间的可读关系。
- `character_entry`：从人物状态或情绪进入；若暂缓交代关键空间，必须在 `reason` 说明收益。
- `subjective_entry`：从明确人物的主观观察进入。
- `deliberate_withhold`：有意隐藏一项或多项空间信息；`withheld_information[]` 不得为空，`reason` 必须说明隐藏收益。

`observer_position` 写明第一镜观察者／摄影机进入场景的相对位置；`required_spatial_information[]` 写明首镜或入口镜组结束前观众必须理解的信息。除 `deliberate_withhold` 外，若存在未展示信息，也必须证明它不妨碍后续动作、视线、方向或遮挡关系。最终第一镜及必要的入口镜组必须匹配 Gate 2 已确认的 `entry_strategy`；改变入口模式、观察位置、必需空间信息或有意隐藏内容，均须重新展示并确认 Gate 2。

`shot_plan` 恰含：

```text
planned_shot_count
planned_edit_point_count
planned_total_duration_seconds
planned_units
viewing_decisions
edit_points
reorders
visual_uniformity_reviews
```

`screen_events[]` 的原子字段与 `viewing_decisions[]` 的 `non_cut_basis` 以 [screen-event-and-cut-map.md](screen-event-and-cut-map.md) 为准。机器先审计发言权、观看主体、尺度、信息落点与动作发起者，再接受规划单元。

统计公式、长镜语义和转场映射以 [shot-design.md](shot-design.md) 为准。机器重新计算三项统计，不接受自报数值。

每个 `planned_units[]` 必须含：

```text
plan_unit_id
plan_order
scene_id
beat_ids
screen_event_ids
source_spans
estimated_duration_seconds
narrative_purpose
visual_plan
```

普通剧情镜不得超过 10 秒。明确采用长镜头时同时增加 `shot_form=long_take` 与 `long_take_design={reason,supports[],protected_event_ids[]}`。只有相关时增加 `source_reuse` 与 `dialogue_design`；含多个对白轮次的同镜必须有 `dialogue_design`。规划单元禁止出现 `shot_id`、最终 camera、精确 composition、blocking、完整执行描述或最终六列内容；核心摄影语法必须在 `visual_plan` 中提前确认。

`visual_plan` 必需字段：

```text
viewpoint_owner
primary_subjects[]
secondary_subjects[]
shot_size
angle
camera_position
framing_relation
perspective_intent
focus_plan
spatial_strategy
movement_plan
start_frame
end_frame
motivation
```

可选 `style_anchor_ids[]` 与确有拍摄意义时的焦段毫米数。`perspective_intent` 只允许 `wide_spatial | natural_relation | compressed_distance | detail_isolation`。`spatial_strategy` 与 `movement_plan` 必须使用正式闭合结构。

`visual_uniformity_reviews[]` 没有命中高占比审计时为空数组；命中后必须逐项登记：

```text
review_id
scope
scene_id
dimension
dominant_value
reason
style_anchor_ids[]
```

`review_id` 为 `VRxxx`；`scope` 为 `project | scene`，项目级 `scene_id=null`；`dimension` 为 `angle | movement_class`。理由必须说明具体导演收益并引用范围内的风格锚点，不能靠自然语言关键词豁免。

审计阈值对视角与运镜类别相同：全片不少于 8 镜且同一值达到 75%；单场不少于 5 镜且同一值达到 75%；单场 3–4 镜时仅 100% 相同。比例只触发复核，不形成角度配额。多场作品 100% 单一视角且没有对应结构化复核时直接 FAIL。

`dialogue_design` 只在对白存在特殊观看策略或空间风险时提供。对象存在时 `speaker_sequence[]` 与 `justification` 必需；`mode`、`face_readable_speakers[]`、`listener_reaction_characters[]` 与 `axis_id` 按需使用。普通对白通过镜头单元目的和最终执行承接。

只有当前单元与同场上一单元完全复用同一 source spans 且结构上不可合并时，才使用 `source_reuse`：

```json
{
  "from_plan_unit_id": "PU001",
  "reason": "simultaneous_isolation | indivisible_source_action | unavoidable_overlap",
  "justification": "具体说明为何不能合并"
}
```

三个 reason 值的含义：

- `simultaneous_isolation`：同一 source span 内存在两条必须同时被隔离观察的叙事线，无法合并为单一镜头。
- `indivisible_source_action`：单一动作在 source 中连续，但导演明确需要用两个不同观察位置的镜头分别呈现同一动作的不同方面。
- `unavoidable_overlap`：相邻镜头必须复用同一 source 范围以维持时间或空间上的重叠关系，无法通过切分来源边界避免。

每个 `edit_points[]` 由 `viewing_decisions.mode=cut` 确定性派生，复制对应边界、`trigger` 与 `director_reason`，不得人工维护第二套剪辑理由。

每个 `reorders[]` 恰含 `reorder_id`、按规划顺序排列的连续 `plan_unit_ids`、坐标包含全部重排单元的 `source_spans` 和具体 `reason`。无实际来源倒序的空声明为 FAIL。

## 4. 来源与事实覆盖

`source` 必须包含合法 `input_kind`、`boundary_lock`、`scope`、规范化 `locked_text`、`locked_text_hash` 与 `approved_corrections`。相邻双语台词候选还必须含 `dialogue_language_policy`，恰含 `mode=original_with_translation`、原始语言 `original_language`、不含原始语言的 `translation_languages[]`、`resolution=source_explicit | user_confirmed` 与可审计 `evidence`；前者须有邻近来源角色标记，后者须与 `approved_corrections[].to` 的用户确认记录逐字一致。
双语候选缺少策略时返回 `DIALOGUE_LANGUAGE_AMBIGUOUS`；中文在前、英文斜体、字符体系和阅读便利性都不是主次依据。该对象属于 Gate 1 source payload，修改会使 Gate 1 及下游 Gate 2 确认失效。

每个 source span 使用 0-based Unicode code point 左闭右开坐标与 `text_hash`。hash 是对应切片的 64个小写十六进制字符的 SHA-256。构建器可从 draft 的坐标补写 hash。
fact span 必须按坐标包含于所属 Beat span；镜头 span 必须按坐标包含每个 covered fact span。相同字面不能替代坐标关系。

每个 fact 必须由至少一个同场镜头的 `covered_fact_ids` 覆盖，并满足：

- fact span 包含于所属 Beat。
- 镜头 span 包含该 fact span。
- fact、Beat 与镜头属于同一场景。
- 对白在 `dialogue[]` 与权威执行正文中逐字出现。
- 对白保持来源文字和语言；未经用户明确追加翻译需求，不生成译文替换来源对白。
- 存在双语语言策略时，dialogue fact 还必须含 `language=source.dialogue_language_policy.original_language` 与 `source_role=original_dialogue`；语言标记、文字体系或来源角色不一致即 FAIL。
- 不可逆动作、关键状态、因果与现实层不被执行正文改写。

`coverage_evidence[]` 是兼容字段。存在时仍验证路径和 quote 的真实性，但 2.5.1 不要求逐 fact 重复举证。复杂画面中的关键信息可用自然语言 `presentation_note` 指明观看重点。
对白 fact 与镜头对白的 `text` 只保存正文，不含角色名前缀、冒号、表演说明及任何非对白文字。

## 5. 最终镜头约束

`shots[]` 数量和数组顺序必须一对一匹配 `planned_units[]`。每镜最少保留：

- `shot_id`、`shot_order`、`plan_unit_id`；只有长镜头才增加 `shot_form=long_take`。
- scene、Beat、source spans 与 covered facts。
- 正整数 `duration_seconds`、有序 `shot_phases[]`、`cut_design`、最小 camera、`execution_text` 与逐字 `dialogue[]`。
- `transition_to_next`、确定性渲染结果和固定为空字符串的镜头 `notes`；只有长镜头才增加长镜审计。

以下字段按真实场景需要出现：`blocking`、`performance`、`speaker_presentation[]`、`visible_characters[]`、`visible_props[]`、`environment_behavior[]`、`continuity_updates[]`、`end_state[]`、`coverage_evidence[]`、`primary_fact_id`。

`performance_chains[]` 只在自然语言受保护过程不足以表达复杂跨镜表演时使用。对象存在时继续验证步骤与真实断点。

最小 `camera` 包含 `shot_size`、`angle`、`composition` 与 `movement`，并必须落实对应 `visual_plan` 的 `framing_mode`、`primary_subjects[]` 与 `position`；过肩镜同时落实 `foreground_characters[]`。为兼容现有数据键，内部继续使用 `angle`，但它只表示纯视角高度／俯仰关系；不得写主体、地点、镜头焦段、主观身份、构图模式或叙事结果。`shot_size` 只写纯景别，或用“→”连接的合法景别变化；不得拼入 `framing_mode`、人物名称、地点、主体或构图说明。`movement` 只写纯摄影机行为，以及执行该行为必需的速度、方向或承载平台；不得写人物动作、画面结果、曝光、对焦结果或执行提醒。`logic` 可精化运动路径与具体构图；已登记字段不得互相矛盾或暴露内部 ID。`framing_mode` 只负责单人、双人、多人、过肩、主观、插入、环境或连续重构等构图身份，绝不拼入 `shot_size`。`start_frame` 与 `end_frame` 仅用于动作接续编号，类型为字符串，不得进入第五列。

终稿 camera 的景别、角度、机位、构图、主体与归一化运镜必须兑现对应 Gate 2 DOP `visual_plan`。任何不一致直接 FAIL，不能靠临时改一镜、修改终稿文字或重算 hash 绕过 Gate 2。透视、焦点、空间策略、起止画面与阶段时间同样属于已确认执行承诺。

`execution_text` 是第五列正文的唯一权威自然语言描述。正式新建正文不再拆分为【镜头调度】【人物表演与声音】【镜头结束】三段，而是写成一个连续的【画面内容】段落，撰写顺序固定为：

```text
当前环境描写 → 摄影机当前相对位置和朝向 → 画面可见内容描写 → 人物动作与表情描写 → 人物台词 → 人物状态描写
```

镜内出现环境变化或人物位移（行走、奔跑、摔倒等）必须写明。逐字保留对白。原文动作可以进入画面内容，但只复制或改述原文、没有镜内调度、表演／声音处理和结束状态时不构成完整导演执行。可逆表演细节可以进入导演执行或按需 `performance.visible_behavior`，不得改变剧情状态或补写因果。

【画面内容】的生成性描述默认使用中文。只有两类非中文内容可以保留：

1. 通用标准术语，例如原样使用的 `V.O.`、`O.S.`、`POV`、`VFX` 等行业缩写。
2. 在本轮 `source.locked_text` 中逐字出现的原剧本内容，包括必须保持原语言的角色台词、专有名词或原文标记。

内部英文枚举、字段名或机器状态（例如 `wide_spatial`、`state`、`position`、`owner`）不得进入第五列；必须在自然语言画面描述中转换为中文。角色台词不得翻译、音译、转写或改换语言。用户明确追加翻译需求时，译文作为独立辅助交付，不替换 dialogue fact、`dialogue[].text` 或【画面内容】中的来源台词。

旧版 `execution_passages[]` 只能作为迁移来源，不能代替 2.5.1 交付中的 `execution_text`，也不得与其并列成为第二套权威正文。

每镜字符串字段 `notes` 固定为 `""`。第六列是人工预留列，Skill、构建器与确定性派生文件均不得自动填入声音、表演、连续性、情绪、时长、执行提醒或内部 ID。必要声音、可观察表演和影响后镜的连续性分别写入【画面内容】及对应结构化字段。人工在交付后填写 Excel 备注不回写机器事实源，也不参与本轮确定性校验。

`shot_id` 必须按最终数组顺序连续编号为 `SH001`、`SH002`……。最终 `scene_id`、`beat_ids`、source spans 与存在的长镜意图必须匹配对应规划单元。每个非末镜的 `transition_to_next` 必须包含 `type` 与匹配该规划边界的 `edit_point_id`；末镜的 `transition_to_next` 固定为 `{ "type": "scene_end", "edit_point_id": null }`。任何增删、换序、长镜意图或剪辑点改变都先修改规划并重新 Gate 2。

## 6. 最小结构示例

以下片段只说明 2.5.1 的规划关系，不是可直接构建的完整 draft：

```json
{
  "contract_name": "shot-data",
  "contract_version": "2.5.1",
  "source_skill": "su-fenjingskill",
  "source_skill_version": "2.5.1",
  "screen_events": [
    {
      "screen_event_id": "SEV001",
      "scene_id": "SC001",
      "event_order": 1,
      "beat_ids": ["B001"],
      "source_spans": [{"start": 0, "end": 12}],
      "covered_fact_ids": ["F001"],
      "visual_subjects": ["B"],
      "visual_action": "B 听见画外问话后抬眼。",
      "viewing_requirement": "看清 B 承受声音的反应。",
      "scale_requirement": "面部反应可读。",
      "spatial_zone": "桌边",
      "temporal_relation": "sequential",
      "sound_fact_ids": ["F001"],
      "event_role": "dialogue_turn",
      "primary_viewing_subject": "B",
      "focus_scale": "face"
    }
  ],
  "shot_plan": {
    "planned_shot_count": 1,
    "planned_edit_point_count": 0,
    "planned_total_duration_seconds": 5,
    "planned_units": [
      {
        "plan_unit_id": "PU001",
        "plan_order": 1,
        "scene_id": "SC001",
        "beat_ids": ["B001"],
        "screen_event_ids": ["SEV001"],
        "source_spans": [{"start": 0, "end": 12}],
        "estimated_duration_seconds": 5,
        "narrative_purpose": "先留在倾听者身上，让画外问话形成压力。",
        "visual_plan": {
          "viewpoint_owner": "B",
          "primary_subjects": ["B"],
          "secondary_subjects": [],
          "shot_size": "近景",
          "angle": "平视",
          "camera_position": "B 正前方略偏门口一侧",
          "framing_relation": "B 单人占据画面，门口留作声音方向",
          "perspective_intent": "natural_relation",
          "focus_plan": "焦点保持在 B 的反应",
          "spatial_strategy": {"type": "not_applicable", "description": ""},
          "movement_plan": {
            "class": "fixed",
            "trigger": "",
            "speed": "",
            "path": "",
            "end_condition": "",
            "hold_reason": "保护 B 承受问话的完整反应"
          },
          "start_frame": "B 抬眼前保持静止",
          "end_frame": "问话落下后仍停在 B 的面孔",
          "motivation": "把画面所有权留给承受问话的 B。"
        }
      }
    ],
    "viewing_decisions": [],
    "edit_points": [],
    "reorders": [],
    "visual_uniformity_reviews": []
  }
}
```

普通镜头省略 `shot_form` 和 `director_audit`；长镜结构见 [shot-design.md](shot-design.md)。

### 六列渲染示例

```text
SH001 | 场景显示名 | B001～锁定原文 | 5秒 | 【近景｜平视｜固定】\n【画面内容】B 在桌边抬眼，画外问话落下后焦点仍停在他的面孔。 |
```

## 7. 正式四文件与六列

正式交付基础文件名为四文件；若用户额外提供剧本名称，可扩展为带剧本名的四文件。文件名禁止使用通用名 `storyboard.xlsx` / `storyboard.md` 等。文件名须使用用户提供的剧本名称、标题、编号作为前缀；未显式提供时，从锁定的剧本首行解析编号与标题，构建为：

```text
{编号}_{标题}_shot_data.json
{编号}_{标题}_storyboard.md
{编号}_{标题}_storyboard.xlsx
{编号}_{标题}_storyboard_validation.json
```

若用户额外提供了剧本名称，则扩展为：

```text
{剧本名称}_{编号}_{标题}_shot_data.json
{剧本名称}_{编号}_{标题}_storyboard.md
{剧本名称}_{编号}_{标题}_storyboard.xlsx
{剧本名称}_{编号}_{标题}_storyboard_validation.json
```

例如锁定剧本首行为“第15集·《第八天》”时，输出文件应为：

```text
ep15_dibati_shot_data.json
ep15_dibati_storyboard.md
ep15_dibati_storyboard.xlsx
ep15_dibati_storyboard_validation.json
```

标题到标识符的转换规则：

1. 优先使用用户显式提供的 `project_id`、罗马字标识或英文标题。
2. 用户未提供时，对中文标题使用标准拼音（不带声调，小写，连续书写，去掉空格和标点），多音字取剧本语境下最常见读音；若存在歧义，使用用户提供的元数据覆盖。
3. 编号统一为阿拉伯数字，前置 `ep` 或保留原前缀（如“第15集”→ `ep15`）。
4. 最终文件名只使用 ASCII 字母、数字、下划线和点。

`shot_data.json` 是机器事实源；其余文件必须由同一次构建确定性派生，不得手改。

六列名称和顺序固定：

```text
镜号
场景
原剧本段落
镜头时长
运镜＋主画面描述
备注
```

- 镜号来自 `shot_id`。
- 场景来自清洁的 `scenes[].scene`，不得包含“约一分钟”“约55秒”等预计场长。
- 原剧本段落按 `covered_fact_ids` 对应的 source spans 回切，按 Beat 顺序渲染为 `Bxxx～原文`；过滤标题、场景头和人物表，去除重复片段、首尾空白和连续多余空行，动作与对白之间最多保留一个有意义空行。
- 时长来自 `duration_seconds`。
- 第五列逐字等于 `rendered_shot_description`。
- 备注固定为空，作为人工预留列。

## 8. 第五列确定性渲染

按固定顺序渲染：

```text
【景别｜角度｜运镜】
【画面内容】
```

不再单列【机位与构图】【站位位移】【人物表演与声音】【镜头结束】等段落。机位、构图关系、人物位移、表演与声音处理全部自然融入【画面内容】段落中。

镜头头统一为标准格式 `【景别｜角度｜运镜】`，恰含三个纯摄影语义项：

- 第一项逐字来自 `camera.shot_size`，只写纯景别；合法景别变化可用“→”连接。
- 第二项逐字来自 `camera.angle`，只写纯视角高度／俯仰。
- 第三项逐字来自 `camera.movement`，只写摄影机行为及必要速度、方向或平台。

人物、地点、构图结果、主体关系、动机和揭示结果不得进入三元素。`camera.position`、`camera.composition`、`framing_relation`、主体、焦点、空间策略和焦段只保留在 DOP 结构与【画面内容】中。镜头头不显示内部轴线、机器状态、曝光提醒或执行提醒。

【画面内容】为单一连续自然语言段落，撰写逻辑固定为：

```text
初始画面 → 镜内动作／焦点／摄影机变化 → 结束画面
```

三个阶段融合为一个自然语言段落，不显示“起幅／过程／落幅”标签。镜内环境变化或人物位移必须写明，逐字对白必须出现。不能使用“按原文”“完成信息”“所在区域”“处于主要观看位置”等占位或模板套话，不得显示 phase ID、coverage 路径、内部转场 ID 或机器状态。

除通用标准术语和 `source.locked_text` 中逐字出现的原剧本内容外，段落内的生成性描述词统一使用中文。台词保持原语言，不得自动翻译。

## 9. 禁止下游字段

JSON 任意层级递归禁止：

```text
prompt
prompt_text
prompt_units
model_profile
timeline
```

同时禁止任何包含 `prompt` 的 key，禁止 `model`、`model_name`、`model_config`、`model_settings`、`max_clip_duration_seconds`，以及 `cut_label`、`cut_index`、`grouping_reason`、`standalone_reason` 等下游 Cut 链／分组字段。允许的 `cut_design` 及其 `action_cut` 类型只表达导演剪辑意图。

## 10. CLI 构建与校验

从 Skill 根目录运行：

```text
python scripts/storyboard_delivery.py build --input <draft.json> --output-dir <目录>
python scripts/storyboard_delivery.py validate --output-dir <目录>
python scripts/storyboard_delivery.py review-gate-2 --input <draft.json>
python scripts/test_storyboard_delivery.py
```

`review-gate-2` 是 Gate 2 确认前的只读审计。它输出预计 `gate_2_digest`、逐场与全片视觉分布、平均镜头时长、每分钟剪辑点、超过 10 秒普通镜头数、说话者交接与实际切镜数、多事件单元、非切例外、长镜保护范围及 `READY | REVIEW_REQUIRED | BLOCKED`；不得写入确认、修改输入或生成正式四文件。

`build`：

1. 读取 draft，拒绝非标准 JSON 数值。
2. 在任何 UTF-8 hash 或编码前检测孤立 surrogate。
3. 规范化锁定文本并补写源 hash 与 span hash。
4. 生成确定性第五列与 `content_hash`。
5. 重新执行原子事件、默认切镜、非切依据、长镜保护范围和摄影三元素审计，并校验身份、两 Gate、digest、场级风格锚点、逐镜视觉规划、来源覆盖、逐字逐语言对白、画面内容中文默认规则、空白备注、时长、连续性、规划／终稿一致、六列格式与禁字段。
6. 在目标目录建立同级临时文件并回读自检，成功后原子替换四文件。

`validate` 重新读取四文件，重算结构、渲染、hash，并逐单元格比较 Markdown 与 Excel。

语义 FAIL、输入读取失败和 Unicode 失败都输出结构化 FAIL JSON 或稳定 issue code；CLI 不得泄漏裸 `UnicodeEncodeError`。build 失败不写正式四文件。

测试必须使用系统临时目录并自动清理；不得在 Skill 目录创建 `.test-*` 或 `__pycache__`。

## 11. Validation report

报告结构：

```json
{
  "contract": "shot-data/2.5.1",
  "gate_2_rule_revision": "2.5.1-cut-atomicity-r2",
  "contract_status": "PASS",
  "director_readiness": "READY",
  "status": "PASS",
  "source_content_hash": "64个小写十六进制字符的 SHA-256",
  "errors": [],
  "warnings": [],
  "cut_atomicity": {
    "average_shot_duration_seconds": 2.5,
    "edit_points_per_minute": 12.0,
    "ordinary_shots_over_10_seconds": 0,
    "dialogue_handoffs": 1,
    "dialogue_handoffs_with_cuts": 1,
    "multi_event_plan_units": 0,
    "non_cut_exceptions": [],
    "long_takes": []
  },
  "visual_design": {
    "project": {
      "planned_shots": 2,
      "angles": {"平视": 1, "微仰视": 1},
      "shot_sizes": {"中近景": 1, "近景": 1},
      "movement_classes": {"fixed": 1, "push": 1}
    },
    "scenes": {},
    "uniformity_findings": [],
    "confirmed_uniformity_reviews": []
  },
  "summary": {
    "scenes": 1,
    "beats": 2,
    "shots": 2,
    "duration_seconds": 8,
    "planned_shots": 2,
    "planned_edit_points": 1
  }
}
```

每条 issue 使用稳定 `code`、`path`、`message`。拆镜原子性使用稳定码 `SCREEN_EVENT_MULTI_SPEAKER`、`SCREEN_EVENT_ATOMICITY_OVERLOAD`、`DIALOGUE_HANDOFF_CUT_REQUIRED`、`NONCUT_BASIS_REQUIRED`、`NONCUT_VISUAL_PLAN_MISMATCH`、`ORDINARY_SHOT_DURATION_EXCEEDED`、`LONG_TAKE_DESIGN_REQUIRED`、`PROTECTED_PROCESS_SCOPE_OVERREACH`、`CAMERA_HEADER_NOT_TRIAD`。存在任一结构错误时 `director_readiness=BLOCKED`，不能因字段齐全返回 READY。

机器不裁决镜头是否“更电影化”、表演审美或景别比例，但确定性审计发言权交接、事件原子性、普通镜头 10 秒上限、非切依据、遮挡保护范围、三元素纯度、第五列语言规则和空白备注。`long_take.needs_review` 与有理由的连续性例外可保留为 WARN。
