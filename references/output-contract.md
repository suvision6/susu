# Output Contract

本文件是 `shot-data/2.4.3`、两 Gate digest、整场规划、最小镜头结构、按需导演细节、规划／终稿一致性、六列渲染、禁字段、文件名、CLI 与 validation report 的唯一规则源。

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

正式身份固定为 `contract_name=shot-data`、`contract_version=2.4.3`、`source_skill=su-fenjingskill`、`source_skill_version=2.4.3`。

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
shot_plan
scenes
beats
emotion_arcs
performance_chains
shots
```

其中 `director_style_options`、`selected_style_option_id`、`emotion_arcs` 与 `performance_chains` 为按需字段。为兼容 2.4.0，存在时继续校验；2.4.3 新生成不为填空而输出空分析结构。

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
- `notes` 是普通字符串，只记录确认语境。
- 不保存 `confirmed_by`、用户 ID、签名或其他身份字段；合同不声称认证用户身份。

Gate 1 canonical payload 恰含当前：

```text
source
source_analysis
director_profile
```

实际展示候选时，再加入 `director_style_options` 与 `selected_style_option_id`。只影响交付文件名的 `source.delivery_slug` 不进入 Gate 1 payload，不使既有导演选择失效。

Gate 2 canonical payload 恰含：

```text
gate_1_digest
scene_plans
shot_plan
```

`scene_plans` 只提取每场实际展示的 `scene_id + scene + directing_plan`。计算前统一规范化 `locked_text`、源 hash 与全部 span hash。源、分析、风格或选择变化会使 Gate 1 与 Gate 2 旧确认失效；场级导演策略或规划变化会使 Gate 2 旧确认失效。未展示的情绪分析、表演链、状态台账或 Fact 分类不冒充用户确认内容。

脚本公开 `stage_digest(data, 1 | 2)` 供 Gate 阶段计算。构建器只验证用户已经明确确认的 digest，绝不自动改写 digest 以越过 Gate。

## 3. 拆镜规划合同

每个 scene 必须有 `directing_plan`。必需字段：

```text
scene_objective
progression[]
pov_flow[]
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

该对象表达整场导演判断，不证明表格填写完整度。核心目标、推进或视点缺失为 FAIL；其他维度按场景需要使用。

`shot_plan` 恰含：

```text
planned_shot_count
planned_edit_point_count
planned_total_duration_seconds
planned_units
edit_points
reorders
```

统计公式、长镜语义和转场映射以 [shot-design.md](shot-design.md) 为准。机器重新计算三项统计，不接受自报数值。

每个 `planned_units[]` 必须含：

```text
plan_unit_id
plan_order
scene_id
beat_ids
source_spans
estimated_duration_seconds
narrative_purpose
```

只有明确采用长镜头时增加 `shot_form=long_take`。只有相关时增加 `source_reuse` 与 `dialogue_design`。规划单元禁止出现 `shot_id`、camera、composition、movement、blocking、完整执行描述或最终六列内容。

`dialogue_design` 只在对白存在特殊观看策略或空间风险时提供。对象存在时 `speaker_sequence[]` 与 `justification` 必需；`mode`、`face_readable_speakers[]`、`listener_reaction_characters[]` 与 `axis_id` 按需使用。普通对白通过镜头单元目的和最终执行承接。

只有当前单元与同场上一单元完全复用同一 source spans 且结构上不可合并时，才使用 `source_reuse`：

```json
{
  "from_plan_unit_id": "PU001",
  "reason": "simultaneous_isolation | indivisible_source_action | unavoidable_overlap",
  "justification": "具体说明为何不能合并"
}
```

每个 `edit_points[]` 必须含 `edit_point_id`、相邻前后 `plan_unit_id`、`source_spans`、具体 `trigger` 和相对于不剪的 `editorial_gain`。类别词不能单独充当理由；剪辑点必须覆盖所有相邻规划边界且不得多出。

每个 `reorders[]` 恰含 `reorder_id`、按规划顺序排列的连续 `plan_unit_ids`、坐标包含全部重排单元的 `source_spans` 和具体 `reason`。无实际来源倒序的空声明为 FAIL。

## 4. 来源与事实覆盖

`source` 必须包含合法 `input_kind`、`boundary_lock`、`scope`、规范化 `locked_text`、`locked_text_hash`、`approved_corrections` 与 `delivery_slug`。

`delivery_slug` 根据剧本名称、编号和标题生成，只使用纯 ASCII、小写字母、数字和单短横线，不能含版本号、日期、状态词或中文。例如“第15集《第八天》”使用 `ep15-dibati`；若来源同时提供剧名，可使用 `<剧名拼音>-ep15-dibati`。

每个 source span 使用 0-based Unicode code point 左闭右开坐标与 `text_hash`。hash 是对应切片的 64个小写十六进制字符的 SHA-256。构建器可从 draft 的坐标补写 hash。

fact span 必须按坐标包含于所属 Beat span；镜头 span 必须按坐标包含每个 covered fact span。相同字面不能替代坐标关系。

每个 fact 必须由至少一个同场镜头的 `covered_fact_ids` 覆盖，并满足：

- fact span 包含于所属 Beat。
- 镜头 span 包含该 fact span。
- fact、Beat 与镜头属于同一场景。
- 对白在 `dialogue[]` 与权威执行正文中逐字出现。
- 不可逆动作、关键状态、因果与现实层不被执行正文改写。

`coverage_evidence[]` 是 2.4.0 兼容字段。存在时仍验证路径和 quote 的真实性，但 2.4.3 不要求逐 fact 重复举证。复杂画面中的关键信息可用自然语言 `presentation_note` 指明观看重点。

对白 fact 与镜头对白的 `text` 只保存正文，不含说话人前缀。

## 5. 最终镜头约束

`shots[]` 数量和数组顺序必须一对一匹配 `planned_units[]`。每镜最少保留：

- `shot_id`、`shot_order`、`plan_unit_id`；只有长镜头才增加 `shot_form=long_take`。
- scene、Beat、source spans 与 covered facts。
- 正整数 `duration_seconds`、标准 `duration_blocks[]`、`cut_design`、最小 camera、`execution_text` 与逐字 `dialogue[]`。
- `transition_to_next`、确定性渲染结果和 notes；只有长镜头才增加长镜审计。

以下字段按真实场景需要出现：`blocking`、`performance`、`speaker_presentation[]`、`visible_characters[]`、`visible_props[]`、`environment_behavior[]`、`continuity`、`continuity_updates[]`、`end_state[]`、`coverage_evidence[]`、`primary_fact_id`。

`performance_chains[]` 只在自然语言受保护过程不足以表达复杂跨镜表演时使用。对象存在时继续验证步骤与真实断点。

最小 `camera` 包含 `shot_size`、`angle`、`position`、`logic`、`composition` 与 `movement`。`framing_mode`、`primary_subjects[]`、`foreground_characters[]`、`start_frame` 与 `end_frame` 按需使用。字段用自然导演语言说明观看位置与画面关系，不要求为术语分类拆句；已登记字段不得互相矛盾或暴露内部 ID。

`execution_text` 是第五列正文的唯一权威自然语言描述。正式新建正文必须且只能使用一个 `【画面内容】`，把环境、摄影机相对位置与朝向、可见构图、人物动作表情、逐字台词和动作后的可见状态自然融合成一段。镜内存在环境变化、遮挡变化、人物位移或进出画时必须写出过程和落位。

不得出现独立的 `【机位与构图】`、`【站位位移】`、`【镜头调度】`、`【人物表演与声音】` 或 `【镜头结束】`。镜头结束状态仍由内部 `end_state`、`cut_design` 和转场承接，不在第五列重复显示。

逐字保留对白。原文动作可以进入画面内容，但只复制或改述原文、没有环境、摄影机关系、可见调度和表演状态时为 FAIL。与来源一致、不制造新事实的可逆表演和调度允许进入导演执行。

旧版 `execution_passages[]` 只能作为迁移来源，不能代替 2.4.3 正式交付中的 `execution_text`，也不得与其并列成为第二套权威正文。

每镜字符串字段 `notes` 必须以构建器从 `duration_blocks[]` 生成的 `[时长估算]` 开头：

```text
[时长估算]同步动作A秒；同步台词B秒；非同步动作C秒；情绪留白D秒；前两项取 max 后再加后两项，共T秒。
```

`T` 必须精确等于 `duration_seconds`。人物状态、场景／现实层、关键道具、连续性例外、特殊声音／特效或安全要求在需要时追加为 `[执行提醒]...`；不得复制第五列、写内部 ID，或以“无”“同上”等占位语代替。构建器覆盖人工编写的旧时长前缀，但保留合法执行提醒。

`shot_id` 必须按最终数组顺序连续编号为 `SH001`、`SH002`……。最终 `scene_id`、`beat_ids`、source spans 与存在的长镜意图必须匹配对应规划单元。每个非末镜的 `transition_to_next.edit_point_id` 必须匹配该规划边界；末镜为 `null`。任何增删、换序、长镜意图或剪辑点改变都先修改规划并重新 Gate 2。

## 6. 最小结构示例

以下片段只说明 2.4.3 的规划关系，不是可直接构建的完整 draft：

```json
{
  "contract_name": "shot-data",
  "contract_version": "2.4.3",
  "source_skill": "su-fenjingskill",
  "source_skill_version": "2.4.3",
  "shot_plan": {
    "planned_shot_count": 2,
    "planned_edit_point_count": 1,
    "planned_total_duration_seconds": 8,
    "planned_units": [
      {
        "plan_unit_id": "PU001",
        "plan_order": 1,
        "scene_id": "SC001",
        "beat_ids": ["B001"],
        "source_spans": [{"start": 0, "end": 12}],
        "estimated_duration_seconds": 5,
        "narrative_purpose": "先留在倾听者身上，让画外问话形成压力。",
        "dialogue_design": {
          "mode": "listener_hold",
          "speaker_sequence": ["A"],
          "justification": "A 的声音作用于 B，暂不交出画面所有权。"
        }
      },
      {
        "plan_unit_id": "PU002",
        "plan_order": 2,
        "scene_id": "SC001",
        "beat_ids": ["B002"],
        "source_spans": [{"start": 13, "end": 24}],
        "estimated_duration_seconds": 3,
        "narrative_purpose": "在 B 作出决定后改变观察位置。"
      }
    ],
    "edit_points": [
      {
        "edit_point_id": "EP001",
        "after_plan_unit_id": "PU001",
        "before_plan_unit_id": "PU002",
        "source_spans": [{"start": 10, "end": 16}],
        "trigger": "B 的沉默结束并作出决定。",
        "editorial_gain": "把持续承压与主动回应分成两个观看阶段。"
      }
    ],
    "reorders": []
  }
}
```

普通镜头省略 `shot_form` 和 `director_audit`。只有明确采用长镜头时增加：

```json
{
  "shot_form": "long_take",
  "director_audit": {
    "long_take": {
      "status": "supported",
      "reason": "表演与空间关系持续发展。",
      "supports": ["performance_development", "spatial_progression"]
    }
  }
}
```

### 六列渲染示例

```text
SH001 | 场景显示名 | B001～锁定原文 | 5秒 | 【平视，中景，固定】\n【画面内容】…… |
```

## 7. 正式四文件与六列

正式交付使用 `source.delivery_slug` 作为前缀：

```text
<delivery-slug>-shot-data.json
<delivery-slug>-storyboard.md
<delivery-slug>-storyboard.xlsx
<delivery-slug>-storyboard-validation.json
```

例如第15集《第八天》：

```text
ep15-dibati-shot-data.json
ep15-dibati-storyboard.md
ep15-dibati-storyboard.xlsx
ep15-dibati-storyboard-validation.json
```

`<delivery-slug>-shot-data.json` 是机器事实源；其余文件必须由同一次构建确定性派生，不得手改。输出目录必须且只能有一组正式四文件；验证器先发现唯一的 `*-shot-data.json`，再依据其中的 `delivery_slug` 校验整组文件名。

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
- 备注来自由时间块确定性规范化后的 `notes`。

## 8. 第五列确定性渲染

按固定顺序只渲染两行：

```text
【角度，景别，运镜】
【画面内容】自然语言镜头执行
```

三元组使用中文方括号和中文逗号，三项都是清楚、可执行的自然导演语言。第二项在提供 `framing_mode` 时按语义映射：

```text
single              -> 景别
over_shoulder       -> 过肩景别
two_shot            -> 双人景别
multi_shot          -> 多人景别
continuous_reframe  -> 连续重构景别
subjective          -> 主观景别
insert              -> 插入景别
environment         -> 环境景别
```

不得把 `framing_mode` 与已经带前缀的景别盲目拼接。`固定镜头` 与 `静止镜头` 在显示时规范为 `固定`；其他合法角度、景别、镜头内景别变化和运镜组合保持开放。

合法三要素例如：

```text
【微俯视，全景，摇臂下降】
【平视，中景，缓慢推进】
【微仰视，中景→特写，缓慢推进】
【平视，全景，斯坦尼康跟随】
【平视，过肩近景，固定】
```

以上只说明格式，不构成封闭组合清单。`【画面内容】` 必须自然写出摄影机相对位置和观察朝向，不得写 `AX001同侧`、`垂直于AX004` 等机器代码。已登记关系必须互相兑现：过肩镜头说明谁的肩后及朝向谁；主观镜绑定观察者；俯仰关系与物理位置不冲突；固定镜头不得同时声明移动。

首镜可以从人物、物件、声音、缺席、遮挡、身体局部、主观感知或空间进入，不要求填写首镜锚点分类，也不要求立即完成空间交代。

character 类型 `continuity_updates[]` 中真实发生的位置、朝向、视线或在场状态变化必须进入同一段 `【画面内容】`，但不另起标签；不得遍历未变化人物，也不得用 blocking 中未登记变化的 facing 猜测“转向”。

第五列正文只读取正式 `execution_text`。同一人物在同镜内的动作—反应—台词写成连续过程，逐字对白必须出现。画面内容不能使用“按原文”“完成信息”“结束状态”等占位语，不得为了通过校验堆叠微表情。不得显示 duration block ID、coverage 路径、内部转场 ID、机器状态或模板占位语。

## 9. 禁止下游字段

JSON 任意层级递归禁止：

```text
prompt
prompt_text
prompt_units
model_profile
timeline
```

同时禁止任何包含 `prompt` 的 key，禁止 `model`、`model_name`、`model_config`、`model_settings`、`max_clip_duration_seconds`，以及 `cut_label`、`cut_index`、`grouping_reason`、`standalone_reason` 等下游 Cut 链／分组字段。允许的 `cut_design` 与 `action_cut` 只表达导演剪辑意图。

## 10. CLI 构建与校验

从 Skill 根目录运行：

```text
python scripts/storyboard_delivery.py build --input <draft.json> --output-dir <目录>
python scripts/storyboard_delivery.py validate --output-dir <目录>
python scripts/test_storyboard_delivery.py
```

`build`：

1. 读取 draft，拒绝非标准 JSON 数值。
2. 在任何 UTF-8 hash 或编码前检测孤立 surrogate。
3. 规范化锁定文本并补写源 hash 与 span hash。
4. 生成确定性第五列与 `content_hash`。
5. 校验身份、两 Gate、digest、整场规划、具体剪切触发与收益、来源覆盖、逐字对白、时长、已登记的连续性、规划／终稿、六列格式与禁字段；详细导演结构存在时再校验其内部一致性。
6. 根据 `source.delivery_slug` 生成规范文件名，在目标目录建立同级临时文件并回读自检，成功后原子替换四文件。

`validate` 重新读取四文件，重算结构、渲染、hash，并逐单元格比较 Markdown 与 Excel。

语义 FAIL、输入读取失败和 Unicode 失败都输出结构化 FAIL JSON 或稳定 issue code；CLI 不得泄漏裸 `UnicodeEncodeError`。build 失败不写正式四文件。

测试必须使用系统临时目录并自动清理；不得在 Skill 目录创建 `.test-*` 或 `__pycache__`。

## 11. Validation report

报告结构：

```json
{
  "contract": "shot-data/2.4.3",
  "status": "PASS",
  "source_content_hash": "64个小写十六进制字符的 SHA-256",
  "errors": [],
  "warnings": [],
  "summary": {
    "scenes": 1,
    "beats": 2,
    "shots": 2,
    "duration_seconds": 5,
    "planned_shots": 2,
    "planned_edit_points": 1
  }
}
```

每条 issue 使用稳定 `code`、`path`、`message`。身份、Gate、digest、来源、逐字对白、Fact 覆盖、规划与终稿、已声明特殊观看策略、明确状态连续性、无具体触发或剪辑收益、模板占位语、场景预计时长、对白标点拆镜、时长、转场、Unicode、禁字段、hash 或四文件不一致为 FAIL。

镜头密度、对白独立成镜比例、景别循环、构图／运镜重复、摄影术语纯度、表演是否俗套、长镜是否有价值和剪切是否“电影化”不由机器裁决。`long_take.needs_review` 与有理由的连续性例外可保留为 WARN。
