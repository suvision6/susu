# Source and Beat Contract

本文件是输入边界、原文锁、source span、稳定内部 ID、Beat、受保护 fact、导演分析隔离、来源叙事顺序与输出命名素材的唯一规则源。

## 目录

- [1. 正式输入边界](#1-正式输入边界)
- [2. 文本锁](#2-文本锁)
- [3. Source span 与内部 ID](#3-source-span-与内部-id)
- [4. 场景、Beat 与来源顺序](#4-场景beat-与来源顺序)
- [5. Director Analysis](#5-director-analysis)
- [6. Fact](#6-fact)
- [7. 关键呈现](#7-关键呈现)
- [8. 对白](#8-对白)
- [9. 事实覆盖](#9-事实覆盖)
- [10. Gate 影响](#10-gate-影响)
- [11. 标题与编号解析](#11-标题与编号解析)

## 1. 正式输入边界

正式输入接受：

- 完整剧本。
- 有明确起止边界的剧本段落，无论是否带场号或段落编号。
- 用户明确提交或锁定为本轮连续范围的台词、动作、场景片段或其他连续原文。

不得强迫用户补完整剧本、外部场号、剧本编号或既有 `scene_id`。只要当前文本边界明确且能识别主体及动作、事件或对白，就可以锁源。

只有梗概、零散设想或无法确认连续原文边界时，拒绝正式拆镜。用户可以明确声明“把当前文本本身锁定为待拆片段”；此时按 `user_locked_fragment` 处理，而不是假装它来自一份未提供的完整剧本。

`source.input_kind` 只允许：

```text
full_screenplay | screenplay_segment | continuous_text
```

`source.boundary_lock` 只允许：

```text
entire_submitted_text | explicit_continuous_range | user_locked_fragment
```

把用户最新明确修正写入 `approved_corrections`；不得静默修正原文。

## 2. 文本锁

1. 把 CRLF/CR 规范为 LF；正式 `locked_text` 不得再含 `\r`。
2. 在任何 UTF-8 编码或 hash 前检测孤立 surrogate 等不可编码文本；返回稳定 validation issue，不得抛出裸 `UnicodeEncodeError`。
3. 对规范化全文的 UTF-8 字节计算 64个小写十六进制字符的 SHA-256。
4. 把边界说明写入 `source.scope`，不要用摘要替代锁定全文。
5. 任何事实、对白和原剧本段落都从 `locked_text` 的 source span 回切。
6. 文本改变后重新计算受影响的 span、hash、分析、Beat、规划与镜头；不得平移猜测。
7. 锁定文本的首行用于解析输出文件命名所需的编号与标题（见第 11 节）。

## 3. Source span 与内部 ID

每个 span 使用 0-based Unicode code point 左闭右开区间：

```json
{"start": 12, "end": 28, "text_hash": "64个小写十六进制字符的 SHA-256"}
```

- `start`、`end` 必须是真正 JSON 整数，且 `0 <= start < end <= len(locked_text)`。
- 同一 `source_spans` 数组按 `start` 严格递增，不重叠、不重复。
- `text_hash` 对 `locked_text[start:end]` 直接计算，由构建器复核。
- 多 span 的显示文本按数组顺序以 LF 拼接。
- 禁止用相同字面、概述、删字、换序或人工改写代替坐标关系。

缺少外部编号时，Skill 按锁定文本中的首次出现顺序生成：

```text
SC001, SC002, ...
B001, B002, ...
F001, F002, ...
```

这些是内部机器 ID，不声称恢复原剧本编号。只要锁定边界和前序单元不变，同一来源单元保持同一内部 ID；来源结构改变时重新生成受影响 ID 与引用。

## 4. 场景、Beat 与来源顺序

- 先识别时空、现实层和主要行动边界，再建立内部场景。
- 每个场景在拆镜前必须先完成整场 `directing_plan`，至少说明场景目标、推进和视点策略；入口、出口、节奏、受保护过程与视觉转折在能影响拆镜时补充。它不是 source fact，也不是表格完整度证明。
- 按人物目标、阻力、行动、信息或关系的实际变化建立 Beat。
- 不预设镜头数；一个 Beat 可跨多镜，多 Beat 也可在同一镜内清楚推进。
- 稳定推进本身可以是合法 Beat 功能，不得为了戏剧模板伪造转折。
- `beat_order` 表达来源叙事顺序；`beats[]` 与各 Beat 内 `facts[]` 默认保持 source span 锚点单调，不得隐式倒序。
- 导演性重排只改变已确认规划与最终镜头顺序，不改变 `beats[]`、`facts[]` 的来源事实顺序。
- 任何重排必须在 Gate 2 的 `shot_plan.reorders[]` 中绑定具体来源范围和规划单元并得到确认。

## 5. Director Analysis

场景或 Beat 可以增加可选 `director_analysis`：

```json
{
  "narrative_function": "建立两人互相试探的关系状态",
  "dramatic_turn": null,
  "pov_owner": "跟随周的观察位置",
  "power_relation": "林发问，周控制回应时机",
  "subtext": "双方都知道声音来源，却都不先点破",
  "directorial_intent": "让观众先注意沉默中的权力拉扯"
}
```

六项含义：

- `narrative_function`：当前场景或 Beat 的叙事功能。
- `dramatic_turn`：来源事实支持的认知、关系、决定或状态转折；没有时使用 `null` 或 `steady`。
- `pov_owner`：观众主要跟随的人物或观察位置。
- `power_relation`：人物间主动权、压力与回应力学。
- `subtext`：基于事实的未说出口目标、回避或张力，不是已发生动作。
- `directorial_intent`：希望观众注意、理解或感受什么。

边界：

- 整个对象可省略；存在时任一项都可为 `null`，不要为填字段发明分析。
- 场景分析提供较宽背景，Beat 分析只收窄当前功能。
- 不给分析项分配 source span，不把分析文字写入 `facts[]`、`dialogue[]` 或对白。
- 不把潜台词改成剧情事实、因果、关键动作、道具状态或台词。与来源一致、不制造新事实的可逆表演或调度可以进入导演字段。
- 分析只参与候选生成与比较，不设置 `presentation_requirement`、`shot_isolation` 或任何必须切镜规则。
- 导演增加的表演或调度不得写入 `facts[]` 或对白，也不得借此声称来源已经发生了新的事实。
- 分析与事实冲突时，删除或修正分析，绝不修改事实迎合分析。

Gate 1 使用独立的 `source_analysis` 展示边界、叙事功能、推进、人物关系与来源约束；它同样不是 source fact。

## 6. Fact

事实类型：

```text
character | action | dialogue | prop | space | position | emotion | sound | reality
```

每个 fact 必须：

- 有全局唯一 `fact_id`、所属 Beat、原文字面或直接指称的 `text`。
- 有非空 `source_spans`，能回溯到锁定文本。
- 其每个 source span 都按坐标完全包含于所属 Beat 的 source spans；相同字面不能替代坐标包含。
- 由至少一个同场镜头通过 `covered_fact_ids` 与 source span 覆盖。
- 不含镜头、焦段、构图、运镜或下游生成语言。

`performers[]` 只在人物归属无法从 fact 本身判断时使用。旧合同中的 `presentation_requirement`、`shot_isolation`、`isolation_reason` 与 `isolation_group_id` 可作为兼容字段读取，但 2.5.1 不再默认生成，也不以它们反推镜头数。

## 7. 关键呈现

当一个事实虽已被镜头覆盖，但容易在复杂画面中被淹没时，可增加自然语言 `presentation_note`，说明观众需要看清什么。它不自动要求独立成镜。

是否需要独立镜头只能在整场规划中，通过以下比较得出：

- 留在主镜中能否清楚完成。
- 单独改变观察位置能增加什么。
- 切开是否会破坏同一物理过程。

不得扫描“真相”“反应”“关键道具”等关键词自动生成插镜。

## 8. 对白

- dialogue fact 的 `text` 是逐字对白正文，不含角色名前缀、冒号、表演说明及任何非对白文字。
- 同时登记 `speaker` 与来源声音性质 `script_voice_type`。闭合值为 `scene_dialogue | vo | os | mediated`。
- 角色名、VO、OS 标记与台词正文必须从原文直接锁定；禁止根据相邻人物、反应对象或画面主体推断说话者。
- `script_voice_type=vo` 永远是来源层 VO；摄影设计不能把它改成现场对白或 O.S.。现场对白即使在当前镜头看不见说话者，来源层仍是 `scene_dialogue`。
- 同一句对白不得因逗号、顿号、冒号、分号或人工换行拆成多个 fact 或相邻镜头。
- 对白拆镜不由标点或固定正反打机械决定；每次发言权交接先形成新事件与默认切点，再由观看对象、声音位置、空间关系和不切收益决定是否以明确例外保留同镜。具体规则以 [dialogue-staging.md](dialogue-staging.md) 为准。
- 镜头 `dialogue[*].fact_id` 必须指向 dialogue fact，`text` 与其逐字相等。
- 不得把情绪意图、动作说明或 `speaker + ：` 混入对白正文。
- 对白可以与动作和表演并行发生；时长归属由 [shot-design.md](shot-design.md) 决定。

## 9. 事实覆盖

- 每个镜头 source span 必须与已确认规划单元坐标一致。
- 每个 covered fact 的全部来源坐标必须完全包含于该镜头 source spans。
- `covered_fact_ids` 按来源 fact 顺序排列。
- 所有 facts 必须至少被一个同场镜头覆盖；不得用一个不包含其来源范围的镜头冒充覆盖。
- dialogue fact 必须在镜头 `dialogue[]` 与权威执行正文中逐字出现。
- 不可逆动作、关键状态、现实层和因果信息必须在镜头执行中清楚成立。
- 旧版 `coverage_evidence[]` 可作为兼容输入继续校验，但 2.5.1 不要求每个 fact 填写路径和逐字 quote。

## 10. Gate 影响

- Gate 1 digest 覆盖 source、实际展示的源分析、风格材料与 `director_profile`。
- Gate 2 digest 继承 Gate 1 digest，并覆盖实际展示的场级导演策略、`screen_events[]`、观看决策、规划单元、DOP 设计与导演可执行性报告。
- 来源或风格改变时 Gate 1 失效；场级策略、镜头单元、顺序、时长或剪辑点改变时 Gate 2 失效。
- 内部 Fact 分类、未展示的情绪分析或可选状态台账不充当用户已经确认的导演方案。
- 不得把“继续”解释为后续 Gate 的预批准。
- 正式交付只允许 Gate 1、Gate 2 两项确认，不设置最终分镜确认。

## 11. 标题与编号解析

输出文件名需要从锁定文本中获取编号与标题。解析规则如下：

1. 优先使用用户显式提供的 `project_id`、罗马字标识或英文标题。
2. 用户未显式提供时，从 `locked_text` 第一行非空文本解析编号与中文标题，例如：

```text
第15集·《第八天》  →  number="15", title="第八天"
EP15 · 第八天      →  number="15", title="第八天"
《第八天》第15集    →  number="15", title="第八天"
```

3. 编号统一为阿拉伯数字，前置 `ep` 或保留原前缀（如“第15集”→ `ep15`）。
4. 中文标题转标识符使用标准拼音（不带声调，小写，连续书写，去掉空格和标点），多音字取剧本语境下最常见读音；若存在歧义，使用用户提供的元数据覆盖。
5. 最终 `project_id` 与文件名只使用 ASCII 字母、数字、下划线和点，必须以字母或数字开头。
6. 解析结果用于构建 `project_id` 与输出文件名（见 [output-contract.md](output-contract.md)）。
7. 若首行无法解析出编号或标题，则回退使用用户提供的 `project_id`；仍无则使用内部项目标识，但必须在 Gate 1 材料中告知用户。
