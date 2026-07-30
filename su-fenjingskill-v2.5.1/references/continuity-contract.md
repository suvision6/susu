# Continuity Contract

本文件是人物、道具、空间、轴线、视线、银幕方向、动作接续与状态迁移的唯一规则源。

## 1. 场景初态

只在存在跨镜影响时，在 `initial_continuity` 登记：

- 人物位置、朝向、视线、在场状态、服装、妆容、伤势和剧情状态。
- 道具位置、持有者和状态。
- 固定物位置和状态。
- 声源位置、可见性和状态。
- 现实层。

首镜不使用封闭锚点枚举。它可以立即建立空间，也可以从人物、物件、声音、缺席、遮挡、身体局部或主观感知进入并延迟揭示；只要 `directing_plan.pov_flow` 与首个规划单元明确该策略，后续镜头能维持可理解的连续性即可。

简单静态场景可省略 `initial_continuity`。只登记本场实际会变化、需要跨镜继承或存在拍摄风险的字段；不要为填表编造未知状态。

跨场延续使用 `inherits_from` 与 `inherited_states[]`。每个继承项明确 `entity_type`、`entity`、`field`，其子场初值必须等于父场全部镜头结束后的终值。未声明继承的字段按新场初态处理。

## 2. 空间轴线

只有镜头关系存在越轴、方向或动作接续风险时，才在场景 `axes[]` 登记可复核的轴线，并在相关镜头写 `axis_id` 与 `side`。

- 同一轴线从 `side_a` 直接切到 `side_b`（或反向）默认是越轴。
- 有意越轴时，在后镜 `intentional_exceptions[]` 写 `type: axis_cross` 和具体导演理由。
- 位于轴线上、主观镜或空间重新建立时如实使用 `on_axis | not_applicable`，不要伪造侧别。

## 3. 视线与银幕方向

`eyelines[]` 记录人物、目标和画面方向；`screen_directions[]` 记录人物面对、视线或移动方向。

相邻同场镜头中，同一实体同一种方向从 `screen_left` 反为 `screen_right`，或从 `toward_camera` 反为 `away_camera` 时，必须满足之一：

- 当前镜头有位置、朝向、视线或在场状态的可见迁移；
- 场景在当前镜头重新建立空间；
- `intentional_exceptions[]` 记录 `screen_direction_break` 和理由。

摄影机推拉方向变化本身不属于银幕方向违例。

## 4. 动作接续

`action_match.incoming` 与 `action_match.outgoing` 使用稳定动作接续 ID。当前镜到下一镜声明 `action_cut` 时，前镜 outgoing 必须等于后镜 incoming。

需要有意打断动作时，后镜登记 `action_discontinuity` 及理由；不得用模糊“承上镜”代替具体接续状态。

blocking 中出现“走向／朝……走／看向／望向／转向”等明确方向动作时，最终 `facing` 或 `eyeline` 必须兑现同一目标。动作指向与朝向／视线冲突为 FAIL。

## 5. 状态迁移

发生真实状态变化时，在镜头上登记 `continuity_updates: continuity_update[]`。单个 `continuity_update` 对象包含：

```json
{
  "entity_type": "character",
  "entity": "A",
  "field": "position",
  "from": "门口",
  "to": "桌边",
  "evidence_fact_ids": ["F003"]
}
```

- `from` 必须精确等于当前台账状态，`to` 必须不同。
- 有初态台账时，更新实体与字段必须已登记；无初态台账时，更新本身建立后续需要继承的状态。
- 证据 fact 必须由当前镜头覆盖，并能支持该变化。
- 人物位移、朝向、视线、进出场，道具持有/位置/状态，伤势、服装、妆容和现实层变化都按镜头顺序推进。
- 姿态、握持、目光落点或人物距离只要会影响后镜，同样必须登记；不能以“只是表演细节”为由省略。
- 后镜开场继承更新后的状态，不得覆盖历史。
- `continuity_updates` 只登记真实变化：position 写位移、facing 写朝向变化、eyeline 写视线转移、presence 写进出画。不得因为同镜其他人物发生变化而给未变化人物补写“转向”。

## 6. 画面内容中的位移

在最终镜头的【画面内容】段落中，人物位移必须作为可见动作连续写出，不要只在 `continuity_updates` 中登记而在第五列遗漏。例如：

```text
林晓彤转身走回汽车，坐进副驾驶，说：“走吧。”汽车随后驶入车流。
```

连续的位置变化、朝向变化和进出场应自然融入环境描写与可见内容之间，确保第五列本身即可阅读完整的空间过程。

## 7. 有意违例

允许类型：

```text
axis_cross | screen_direction_break | eyeline_break |
action_discontinuity | state_discontinuity
```

每个例外必须有非空、具体的 `reason`。合法例外产生导演审计 WARN，而不是静默通过；无理由例外或未登记的核心冲突为 FAIL。

## 8. 审计边界

机器只校验已经显式登记的轴线侧别、方向反转、动作 ID、状态 from/to 与继承值。未登记无风险对象不构成错误。镜头空间是否“好看”、越轴是否值得、视线是否有张力属于人工导演审计。

空间两端人物可以分别使用近景或特写。此时机器只检查相邻镜头的轴线侧别、视线方向、银幕方向与已建立空间关系，不以物理距离或景别名称判错。只有上述关系出现无解释冲突时才阻断。
