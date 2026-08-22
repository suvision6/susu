# Output Contract

本文件只拥有 `shot-data/2.5.8` 到 JSON、Markdown、Excel、validation report 与 CLI 的交付映射；旧 `2.5.3/2.5.4` 只保留只读验证兼容。字段、必填／可选、基础类型和闭合对象以 [shot-data.schema.json](shot-data.schema.json) 为机器权威；屏幕事件、DOP、来源、对白播放与节奏等含义以各自 owner reference 为语义权威。

## 目录

- [1. 合同身份与顶层结构](#1-合同身份与顶层结构)
- [2. 两项人工确认与 digest](#2-两项人工确认与-digest)
- [3. 拆镜规划合同](#3-拆镜规划合同)
- [4. 来源与事实覆盖](#4-来源与事实覆盖)
- [5. 最终镜头约束](#5-最终镜头约束)
- [6. 最小结构示例](#6-最小结构示例)
- [7. 正式四文件与六列](#7-正式四文件与六列)
- [8. 第五列确定性渲染](#8-第五列确定性渲染)
- [9. 禁止下游字段](#9-禁止下游字段)
- [10. CLI 构建与校验](#10-cli-构建与校验)
- [11. Validation report](#11-validation-report)

## 1. 合同身份与顶层结构

正式身份固定为 `contract_name=shot-data`、`contract_version=2.5.8`、`source_skill=su-fenjingskill`、`source_skill_version=2.5.8`。

顶层字段、按需字段、基础类型和未知字段拒绝策略只由 [shot-data.schema.json](shot-data.schema.json) 定义。2.5.8 Skill 只生成 `shot-data/2.5.8`，并要求固定 `rhythm_policy`、逐场 `rhythm_design`、`dialogue_playbacks[]`、结构化 `duration_design`、节奏复核与机器派生 `duration_review`。

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

候选 `rationale` 固定包含“适配依据、时间与剪辑、摄影机、空间与调度、表演与观看、主要收益、主要风险”七段。用户选择候选不等于确认；只有最终 profile 展示后的确认意图才能生成有效 Gate 1 digest。

**Gate 1 确认等价表达**：

- 明确确认：确认、确定、OK、同意、就这个、用 STYLE-01、可以、没问题、是的。
- 明确不确认：继续、先往下、看看、比较一下、再想想、待定、选第二个看看（仅选择候选，不等于确认）。

选择候选本身不等于确认；必须在展示最终 profile 并出现上述任一确认表达后，才绑定 Gate 1 digest。

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

`gate_2_rule_revision` 固定为 `2.5.8-rhythm-integrity-r1`。`scene_plans` 是 `scenes[]` 的派生字段；`rhythm_policy`、场级 `rhythm_design`、spoken/stage-direction spans、原子事件、`dialogue_playbacks[]`、结构化动作／反应时长、短镜／长镜证明、节奏复核、场次时长差、`shot_plan`、DOP 字段、节奏摘要、`visual_design` 与 `director_readiness` 全部进入 Gate 2 digest。

脚本公开 `stage_digest(data, 1 | 2)` 供 Gate 阶段计算。构建器只验证用户已经明确确认的 digest，绝不自动改写 digest 以越过 Gate。

## 3. 拆镜规划合同

每个 scene 必须有闭合的 `directing_plan`；完整字段、必填／可选关系及类型直接读取 Schema。该对象表达整场导演判断，不证明表格填写完整度。核心目标、推进、视点、结构化入口或风格锚点缺失为 FAIL；其他维度按场景需要使用。

`style_anchor_id` 是全片唯一的 `SAxxx`。每个 `profile_basis[]` 项恰含 `field + value`，必须与 Gate 1 已确认 `director_profile` 的对应闭合轴、`transition_language`、`priorities` 或 `natural_language_intent` 完全匹配。`scene_application` 说明该场具体执行方式；`avoidance` 说明应避免的表面化模仿。

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

机器只校验 entry 的 Schema 结构、`deliberate_withhold` 非空、required／withheld 冲突、Gate 2 digest 与计划—终稿绑定；“空间是否真正建立”“暂缓信息是否提前泄露”“连续镜组是否兑现观察位置”由 Agent 在 Gate 2 展示和终稿复核中判断，并由用户通过 Gate 确认。不得追加大全景、`environment`、后排中央或关键词硬判。

`screen_events[]` 的原子字段与 `viewing_decisions[]` 的 `non_cut_basis` 以 [screen-event-and-cut-map.md](screen-event-and-cut-map.md) 为准。机器先审计发言权、观看主体、尺度、信息落点与动作发起者，再接受规划单元。

统计公式、长镜语义和转场映射以 [shot-design.md](shot-design.md) 为准。机器重新计算三项统计，不接受自报数值。

普通剧情镜为 1–10 秒；1 秒镜必须增加 `short_shot_design`。11–19 秒必须增加 `shot_form=long_take` 与含至少两个阶段的 `long_take_design.temporal_progression[]`，并具备非纯口播的视觉／实时收益。任何达到 20 秒的镜头一律 FAIL。含多个对白轮次的同镜仍必须有 `dialogue_design`。

`duration_policy` 是 Gate 2 绑定的项目级口播策略；`rhythm_policy` 是不可放宽的固定节奏安全合同。每个规划单元必须以 playback segments、action segments 与 reaction holds 建立可重算 `duration_design`。每场 `duration_review` 派生口播下限、动作／反应下限、最低可播、计划、差值和比例；偏差超过 10% 进入复核，正向超时超过 50% 阻断 READY。

`shot_plan.dialogue_playbacks[]` 每条对应一个完整 dialogue fact。其 segments 按规划单元和文字坐标递增，必须从 `0` 到 `len(fact.text)` 无缝、无重叠、无遗漏覆盖一次；记录本单元起始时间、计划口播秒数和 `shot_delivery`。`shot_phases[].dialogue_playback_segment_ids[]` 与 `shots[].dialogue[].playback_segment_id` 必须引用相同片段。

固定 `rhythm_policy` 使用：样本 8 镜、1 秒密度 10%、≤2 秒密度 20%、连续短镜 3 个、长镜密度 20%、floor-lock 90%、机械模式 90%、模板坍缩 75%、场目标复核 10%、正向超时阻断 50%、普通镜上限 10 秒和绝对镜长上限 19 秒。2.5.8 不允许放宽这些值。

每场 `directing_plan.style_anchors[]` 至少有一个场级锚点。逐镜 `style_anchor_ids[]` 可选，只在关键风格应用、有意例外或风格复核中登记；普通镜头不机械复制。焦段毫米数也只在确有拍摄意义时增加。闭合结构由机器 Schema 定义，具体导演语义以 [shot-design.md](shot-design.md) 与 [angle-and-camera-execution.md](angle-and-camera-execution.md) 为准。

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
  "reason": "simultaneous_isolation | indivisible_source_action | unavoidable_overlap | continuous_dialogue_audio",
  "justification": "具体说明为何不能合并"
}
```

四个 reason 值的含义：

- `simultaneous_isolation`：同一 source span 内存在两条必须同时被隔离观察的叙事线，无法合并为单一镜头。
- `indivisible_source_action`：单一动作在 source 中连续，但导演明确需要用两个不同观察位置的镜头分别呈现同一动作的不同方面。
- `unavoidable_overlap`：相邻镜头必须复用同一 source 范围以维持时间或空间上的重叠关系，无法通过切分来源边界避免。
- `continuous_dialogue_audio`：同一完整 dialogue fact 的声音通过 playback 跨相邻画面镜头连续播放；复用来源坐标只服务声音连续性，不复制或重播全文。

每个 `edit_points[]` 由 `viewing_decisions.mode=cut` 确定性派生，复制对应边界、`trigger` 与 `director_reason`，不得人工维护第二套剪辑理由。

每个 `reorders[]` 恰含 `reorder_id`、按规划顺序排列的连续 `plan_unit_ids`、坐标包含全部重排单元的 `source_spans` 和具体 `reason`。无实际来源倒序的空声明为 FAIL。

## 4. 来源与事实覆盖

`source` 必须包含合法 `input_kind`、`boundary_lock`、`scope`、ASCII 小写 kebab-case 的 `delivery_slug`、规范化 `locked_text`、`locked_text_hash` 与 `approved_corrections`。`delivery_slug` 不进入 Gate digest，只负责四文件命名。

没有项目默认时，相邻双语台词候选必须含一种本集 `dialogue_language_policy`：

- 原文／译文并列：`mode=original_with_translation`，并提供 `original_language`、不含原始语言的 `translation_languages[]`、`resolution` 与 `evidence`。
- 两种语言都是角色实际说出的对白：`mode=multilingual_actual`，并提供至少两项 `spoken_languages[]`、`resolution` 与 `evidence`。

项目可一次确认 `project_dialogue_language_policy`，对象必须声明 `scope=project` 与 `exceptions_require_confirmation=true`；后续各集默认继承。某集与项目默认不同时才增加本集 `dialogue_language_policy`，且必须 `resolution=user_confirmed` 并写入本集 `approved_corrections`；相同策略不得重复声明为例外。

`resolution` 只能为 `source_explicit | user_confirmed`。原文／译文的 `source_explicit` 须有邻近来源角色标记；本集 `user_confirmed` 须与 `approved_corrections[].to` 的用户确认记录逐字一致。双语候选缺少任何可用策略时返回 `DIALOGUE_LANGUAGE_AMBIGUOUS`；中文在前、英文斜体、字符体系和阅读便利性都不是主次依据。项目默认和本集覆盖都属于 Gate 1 source payload，修改会使 Gate 1 及下游 Gate 2 确认失效。

每个 source span 使用 0-based Unicode code point 左闭右开坐标与 `text_hash`。hash 是对应切片的 64个小写十六进制字符的 SHA-256。构建器可从 draft 的坐标补写 hash。
fact span 必须按坐标包含于所属 Beat span；镜头 span 必须按坐标包含每个 covered fact span。相同字面不能替代坐标关系。

每个 fact 必须由至少一个同场镜头的 `covered_fact_ids` 覆盖，并满足：

- fact span 包含于所属 Beat。
- 镜头 span 包含该 fact span。
- fact、Beat 与镜头属于同一场景。
- 每个 `screen_event.beat_ids` 按来源顺序精确等于其 `covered_fact_ids` 所属 Beat；不得挂接无关 Beat。
- 对白在 `dialogue[]` 与权威执行正文中逐字出现。
- 对白保持来源文字和语言；未经用户明确追加翻译需求，不生成译文替换来源对白。
- `original_with_translation` 下，dialogue fact 必须含 `language=original_language` 与 `source_role=original_dialogue`；`multilingual_actual` 下，必须含属于 `spoken_languages[]` 的 `language` 与 `source_role=spoken_dialogue`。语言标记、文字体系或来源角色不一致即 FAIL。
- 不可逆动作、关键状态、因果与现实层不被执行正文改写。

`coverage_evidence[]` 只属于 `2.5.3/2.5.4` legacy 兼容路径。2.5.8 的来源完整性由锁源清单、spoken/stage-direction spans 与 playback 全文分区反向核对。
对白 fact 与镜头对白的 `text` 只保存正文，不含角色名前缀、冒号、表演说明及任何非对白文字。

## 5. 最终镜头约束

`shots[]` 的完整闭合结构只由 Schema 定义；其数量和数组顺序必须一对一匹配 `planned_units[]`。每镜 `dialogue[]` 只保存当前 playback segment 的逐字切片并引用 `playback_segment_id`；全片按 segment 顺序拼接必须等于完整 dialogue fact 一次。普通镜头省略长镜字段。

`performance_chains[]` 只在自然语言受保护过程不足以表达复杂跨镜表演时使用。对象存在时继续验证步骤与真实断点。

终稿 `camera` 的字段、类型和可选关系直接读取 Schema；除 `logic`、纯运镜文字和按需构图关系外，绑定字段必须与对应 Gate 2 `visual_plan` 完全一致。

为兼容现有数据键，内部继续使用 `angle`，但它只表示纯视角高度／俯仰关系；不得写主体、地点、镜头焦段、主观身份、构图模式或叙事结果。`shot_size` 只写纯景别，或用“→”连接的合法景别变化；不得拼入人物、地点或构图说明。`movement` 只写纯摄影机行为及必要速度、方向或承载平台；完整触发、路径、停止条件保存在与规划完全相同的 `movement_plan`。`logic` 只精化观察几何，不得与绑定字段矛盾或暴露内部 ID。起止画面必须按顺序进入第五列的自然语言过程，但不显示“起幅／落幅”标签。

`execution_text` 是第五列正文的唯一权威自然语言描述。正式新建正文不再拆分为【镜头调度】【人物表演与声音】【镜头结束】三段，而是写成一个连续的【画面内容】段落，撰写顺序固定为：

```text
当前环境描写 → 摄影机当前相对位置和朝向 → 画面可见内容描写 → 人物动作与表情描写 → 人物台词 → 人物状态描写
```

镜内出现环境变化或人物位移（行走、奔跑、摔倒等）必须写明。逐字保留对白。原文动作可以进入画面内容，但只复制或改述原文、没有镜内调度、表演／声音处理和结束状态时不构成完整导演执行。可逆表演细节可以进入导演执行或按需 `performance.visible_behavior`，不得改变剧情状态或补写因果。

【画面内容】的生成性描述默认使用中文。只有两类非中文内容可以保留：

1. 通用标准术语，例如原样使用的 `V.O.`、`O.S.`、`POV`、`VFX` 等行业缩写。
2. 在本轮 `source.locked_text` 中逐字出现的原剧本内容，包括必须保持原语言的角色台词、专有名词或原文标记。

内部英文枚举、字段名或机器状态（例如 `wide_spatial`、`state`、`position`、`owner`）不得进入第五列；必须在自然语言画面描述中转换为中文。角色台词不得翻译、音译、转写或改换语言。用户明确追加翻译需求时，译文作为独立辅助交付，不替换 dialogue fact、`dialogue[].text` 或【画面内容】中的来源台词。

旧版 `execution_passages[]` 只能作为 legacy 迁移来源，不能代替 2.5.8 交付中的 `execution_text`，也不得与其并列成为第二套权威正文。

每镜 `notes` 默认 `""`，非空值必须与 JSON、Markdown、Excel 第六列逐字一致。备注只承载用户明确要求、真实待确认事项或必要人工复核，不得堆入普通声音、表演、连续性正文或内部 ID。`script_voice_type=unresolved` 时备注必须写明“待确认”及 V.O./O.S. 候选；四文件照常生成，但返回 WARN／REVIEW_REQUIRED 和退出码 2。

`shot_id` 必须按最终数组顺序连续编号为 `SH001`、`SH002`……。最终 `scene_id`、`beat_ids`、source spans 与存在的长镜意图必须匹配对应规划单元。每个非末镜的 `transition_to_next` 必须包含 `type` 与匹配该规划边界的 `edit_point_id`；末镜的 `transition_to_next` 固定为 `{ "type": "scene_end", "edit_point_id": null }`。任何增删、换序、长镜意图或剪辑点改变都先修改规划并重新 Gate 2。

## 6. 最小结构示例

以下片段只说明规划关系；2.5.8 正式 draft 还必须包含固定 `rhythm_policy`、场级 `rhythm_design`、`dialogue_playbacks[]`、节奏复核与结构化时长，不可直接由本片段构建：

```json
{
  "contract_name": "shot-data",
  "contract_version": "2.5.8",
  "source_skill": "su-fenjingskill",
  "source_skill_version": "2.5.8",
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

正式交付文件名只由 `source.delivery_slug` 派生：

```text
{delivery-slug}-shot-data.json
{delivery-slug}-storyboard.md
{delivery-slug}-storyboard.xlsx
{delivery-slug}-storyboard-validation.json
```

例如：

```text
ep15-dibati-shot-data.json
ep15-dibati-storyboard.md
ep15-dibati-storyboard.xlsx
ep15-dibati-storyboard-validation.json
```

先从用户明确提供的罗马字、英文标题或项目标识构建 slug；编号可规范为 `ep15`。锁定文本只有中文标题且没有可靠罗马字时必须询问用户，不得臆测多音字，也不得声明构建器会自动转写。slug 只允许 ASCII 小写字母、数字与单个短横线分隔，不得含下划线、版本词或临时状态词。

`shot_data.json` 是机器事实源；其余文件必须由同一次构建确定性派生，不得手改。六列表格每镜只显示本镜实际播放的对白片段，跨镜拼接后保持来源完整，不在任一单镜重复整段长对白。

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
- 备注来自 `shots[].notes`；默认空，允许用户要求和真实待确认事项。

Excel 必须使用内容限幅列宽、CJK 双宽行高估算和 PingFang SC；冻结首行首列，横向单页宽度打印并重复首行表头。预计行高超过 Excel 409pt 上限时必须以 `XLSX_ROW_OVERFLOW` 停止构建，不得静默裁切。

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

结构化字段只负责事实绑定，不得逐项串接成第五列：

- `camera.position`、角度与观察方向合并为一次物理机位说明；同镜不得对同一目标重复朝向，也不得在运动路径中再次粘贴完整机位。
- `primary_subjects`、`secondary_subjects`、`viewpoint_owner` 与 `framing_relation` 转成具体可见构图，不显示“主位、次要层、观看权、保留主要行动方向”。
- `movement_plan` 转成一条连续、自然的触发—速度—路径—停止过程；固定镜头只写保持原因，不复述空运动字段。
- `start_frame`、事件动作、焦点和 `end_frame` 先做语义消重，再按真实发生顺序写入；不得用“按事件顺序、末项动作、当前可见结果”等分析结论代替结束画面。
- 对白正文逐字出现即可；人物名、动作与冒号可作为生成性连接，但不得用额外引号改变来源台词的标点层级。

校验先从正文中移除每项来源 fact 与逐字对白的一个权威出现，再审计剩余生成性语言。镜内重复机位／方向、实质重复长子句和内部分析词为 FAIL；不少于 8 镜的场或项目中，同一非来源长子句或句首骨架覆盖至少 75% 镜头时产生 `EXECUTION_TEMPLATE_COLLAPSE` WARN。WARN 仍生成完整四文件，但构建退出码为 2，自动化不得视为成功。

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
python scripts/storyboard_delivery.py init-draft --source-file <source.txt> --project-id <id> --delivery-slug <slug> --input-kind <kind> --boundary-lock <lock> --scope <说明> --output <draft.json>
python scripts/storyboard_delivery.py stage-digest --input <draft.json> --gate <1|2>
python scripts/storyboard_delivery.py schema --output <new-schema.json>
python scripts/scene_workspace.py extract --input <draft.json> --scene-id <SCxxx> --output <scene-workspace.json>
python scripts/scene_workspace.py merge --input <draft.json> --scene-workspace <scene-workspace.json> --output <new-draft.json>
python scripts/test_storyboard_delivery.py
```

`review-gate-2` 是 Gate 2 确认前的只读审计。它输出预计 `gate_2_digest`、逐场与全片视觉分布、平均镜头时长、每分钟剪辑点、超过 10 秒普通镜头数、说话者交接与实际切镜数、多事件单元、非切例外、长镜保护范围及 `READY | REVIEW_REQUIRED | BLOCKED`；不得写入确认、修改输入或生成正式四文件。

`init-draft` 从 UTF-8 锁定来源建立完整顶层脚手架；两个 Gate 均为 `pending`，不会伪造确认，且拒绝覆盖既有目标。`stage-digest` 与 `schema` 分别提供只读 digest 和机器结构导出。超长剧本可用 `scene_workspace.py` 提取单场工作集；内部合同固定为 `shot-data-scene-workspace/3`，携带 `rhythm_policy` 及该场 playbacks、rhythm design、timing basis 与 reviews。旧 `/1`、`/2` 工作区只能读取审计，必须从当前 draft 重新导出后才能 merge。合并时清空 project-scope rhythm reviews、替换目标场 scene reviews，并把 Gate 2 重置为 `pending`。

CLI 退出码固定为：`0=READY/PASS`、`1=BLOCKED/FAIL`、`2=REVIEW_REQUIRED/WARN`。自动化流程不得把需要人工复核的状态当作成功。

`build`：

1. 读取 draft，拒绝非标准 JSON 数值。
2. 在任何 UTF-8 hash 或编码前检测孤立 surrogate。
3. 规范化锁定文本并补写源 hash 与 span hash。
4. 生成确定性第五列与 `content_hash`。
5. 重新执行来源清单、原子事件、默认切镜、可播时长、非切依据、长镜保护范围和摄影三元素审计，并校验身份、两 Gate、digest、场级风格锚点、逐镜视觉规划、逐字逐语言对白、备注、连续性、规划／终稿一致、六列格式与禁字段。
6. 取得输出目录独占锁，在目标目录建立同级临时文件并回读自检；flush/fsync 后依次提交四个正式文件，最后提交隐藏的 `.storyboard-delivery-manifest.json`。manifest 记录四文件 SHA-256 与字节数，用于识别并发、残留或外部篡改；`Exception`、`KeyboardInterrupt` 与 `SystemExit` 均按已有文件逐项回滚并原样重新抛出。

`validate` 在同一目录锁保护下发现、读取和比对四文件与 manifest，重算结构、playback 全文分区、时长、节奏、渲染与 hash，并逐单元格比较 Markdown 与 Excel。对 `2.5.8` 继续检查 CJK 行高、限幅列宽、PingFang SC、首行首列冻结、横向打印和重复表头；内容节奏 FAIL 时即使排版正确也不得交付 PASS。

语义 FAIL、输入读取失败和 Unicode 失败都输出结构化 FAIL JSON 或稳定 issue code；CLI 不得泄漏裸 `UnicodeEncodeError`。FAIL 不写正式四文件。WARN 写入可审计的完整交付，但 `build` 返回退出码 `2`；调用方必须显式处理后才能发布。

测试必须使用系统临时目录并自动清理；不得在 Skill 目录创建 `.test-*` 或 `__pycache__`。

## 11. Validation report

报告结构：

```json
{
  "contract": "shot-data/2.5.8",
  "gate_2_rule_revision": "2.5.8-rhythm-integrity-r1",
  "contract_status": "PASS",
  "director_readiness": "READY",
  "status": "PASS",
  "content_hash": "完整 canonical JSON 的 SHA-256",
  "locked_text_hash": "规范化锁定文本的 SHA-256",
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
  "rhythm_design": {
    "project": {
      "median_shot_duration_seconds": 5,
      "p90_shot_duration_seconds": 9,
      "one_second_shots": [],
      "short_shots_at_or_below_2_seconds": [],
      "long_takes": [],
      "shots_at_or_above_20_seconds": [],
      "cut_ratio": 0.5,
      "floor_locked_ratio": 0.0
    },
    "scenes": {},
    "findings": [],
    "accepted_reviews": []
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

每条 issue 使用稳定 `code`、`path`、`message`。内部显式 issue 映射把纯导演执行错误与合同错误分开，不依赖临时字符串前缀；报告结构不增加字段。纯导演执行错误保持 `contract_status=PASS`，但必须为 `director_readiness=BLOCKED / status=FAIL`；任一合同错误同样不得显示 `READY`。WARN-only 与无问题状态保持原行为。

机器不裁决镜头是否“更电影化”、表演审美或景别比例，但确定性审计来源完整性、发言权交接、事件原子性、可播时长、非切依据、遮挡保护范围、三元素纯度、第五列语言规则、备注和 Excel 可读性。`long_take.needs_review` 与有理由的连续性例外可保留为 WARN。
