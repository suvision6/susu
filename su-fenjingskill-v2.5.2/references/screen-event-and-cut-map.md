# 屏幕事件与观看决策

本文件是 `screen_events[]`、`shot_plan.viewing_decisions[]`、切／留／镜内重构以及二者与规划单元关系的唯一规则源。

## 目录

- [1. 屏幕事件](#1-屏幕事件)
- [2. 相邻事件的观看决策](#2-相邻事件的观看决策)
- [3. 与规划单元和剪辑点的确定关系](#3-与规划单元和剪辑点的确定关系)
- [4. 同镜承载与多空间区域](#4-同镜承载与多空间区域)
- [5. Gate 2 展示](#5-gate-2-展示)

## 1. 屏幕事件

Beat 与 Fact 锁定来源事实；屏幕事件把事实翻译成观众必须看见或听见的事件。屏幕事件不是镜头，也不直接决定镜头数量。

每项必须包含：

```text
screen_event_id
scene_id
event_order
beat_ids[]
source_spans[]
covered_fact_ids[]
visual_subjects[]
visual_action
viewing_requirement
scale_requirement
spatial_zone
temporal_relation
sound_fact_ids[]
event_role
primary_viewing_subject
focus_scale
```

- `screen_event_id` 使用全片唯一的 `SEVxxx`。
- `event_order` 在同场从 1 连续递增，数组与来源锚点保持单调顺序。
- `beat_ids[]` 必须按来源顺序精确等于 `covered_fact_ids[]` 所属 Beat，不得引用无关 Beat 或遗漏所属 Beat。
- `covered_fact_ids[]` 与 `sound_fact_ids[]` 只能引用同场 Fact；后者只列本事件必须听见的声音或对白 Fact。
- `visual_subjects[]`、`visual_action`、`viewing_requirement` 与 `scale_requirement` 只说明观众需要取得的视觉信息，不预先指定景别或剪切。
- `spatial_zone` 使用清楚、可执行的自然语言描述事件所在区域。
- `temporal_relation` 只允许 `sequential | simultaneous_with_previous | continuous_from_previous`。每场首项必须是 `sequential`。
- `event_role` 只允许 `spatial | dialogue_turn | action | reaction | reveal | object_detail | information_landing | transition`。
- `primary_viewing_subject` 写明这一刻画面所有权归谁或什么；`focus_scale` 只允许 `space | relation | body | face | detail`。

一个来源事实可由一个或多个屏幕事件承接，但不得借此改变人物、说话者、VO／OS 身份、因果或动作结果。多 Fact 只有在同一主体、同一尺度和同一连续动作内才能合并。

原子性按以下顺序判断：

1. 说话者改变，拆事件；
2. 主要观看主体改变，拆事件；
3. `focus_scale` 改变，拆事件；
4. 新信息完成揭示与人物反应分开；“八天”“谁？”等认知落点独立成事件；
5. 动作发起者改变，拆事件；
6. 人物、物件细节、人物反应不得合成一个事件。

一个事件最多包含一个说话者和一次完整发言。同一人物的一次完整对白不得因标点、停顿或排版换行拆成多个事件。

规划单元内 `screen_event_ids[]` 与最终 `shot_phases[]` 必须保持 `event_order`。导演性倒序不能在单一规划单元内完成；应先拆成多个规划单元，再以受来源范围约束的 `reorders[]` 声明。

## 2. 相邻事件的观看决策

同场每对相邻屏幕事件都必须有一项 `viewing_decisions[]`：

```text
viewing_decision_id
scene_id
from_screen_event_id
to_screen_event_id
mode
trigger
viewing_change
director_reason
reframe_method
non_cut_basis
```

先识别原子边界，再默认建立 `cut`。`mode` 只允许：

- `cut`：在两个事件之间换镜。
- `hold`：保持同一镜头与基本观看组织，让事件在镜内继续。
- `reframe`：保持同一镜头，但通过人物调度、摄影机运动、焦点变化或景别变化重组观看。

`non_cut_basis` 在 `cut` 时必须为 `null`；在 `hold | reframe` 时必须选择：

```text
listener_ownership
offscreen_or_vo
continuous_action
blocking_proof
shared_staging
delayed_reverse
simultaneous_event
```

每次发言权从 A 转移到 B，双人或多人对白都默认 `cut`。只有上述依据与 `dialogue_design`、观看主体和 DOP 方案互相一致时才可不切。导演风格只能改变边界的节奏、距离与观看方法，不能用“停留感”抹掉必要覆盖。

`trigger` 写明实际发生的动作、声音、认知或观看边界；`viewing_change` 写明观众的关注对象、距离、空间信息或主观位置如何变化；`director_reason` 必须比较当前选择相对于另外两种选择的具体收益。

`reframe_method`：

- `mode=reframe` 时必须是 `blocking | camera_move | focus_shift | scale_change` 之一。
- `mode=cut | hold` 时必须为 `null`。

`focus_scale` 变化若不切，只能使用 `reframe`；`reframe_method` 必须由焦点、人物调度、摄影机路径或合法景别变化兑现。普通 `hold` 不能声称完成尺度重组。

不得以“台词结束”“动作边界”“换景别”等类别词单独充当理由。

## 3. 与规划单元和剪辑点的确定关系

每个 `planned_units[]` 必须含非空 `screen_event_ids[]`，按事件顺序列出。事件必须且只能落入一个同场规划单元。

- `hold` 与 `reframe` 的两项事件必须属于同一规划单元。
- `cut` 的两项事件必须分别位于相邻规划单元，且前一事件是前单元末项、后一事件是后单元首项。
- `edit_points[]` 由 `mode=cut` 确定性派生，不作为第二套人工剪辑理由。其 `trigger` 复制观看决策的触发，`editorial_gain` 复制观看决策的 `director_reason`。
- 规划镜头数等于 `planned_units[]` 数量；规划剪辑点数等于 `mode=cut` 的观看决策数量。

同场事件全部被覆盖、所有相邻边界都有决定、事件归属与决定一致，才能进入 Gate 2 确认。

## 4. 同镜承载与多空间区域

同一镜头可承载多个屏幕事件。判断依据不是事件数量，而是：

- 同时事件能否在同一观看组织中成立；
- 顺序事件是否有清楚的镜内观看路径；
- 观众是否知道先看什么、何时转移、最后落在哪里；
- 空间、焦点、调度和摄影机方案是否可执行。

同镜承载多个对白轮次时必须提供 `dialogue_design`，使 `speaker_sequence`、观看主体、`non_cut_basis`、轴线和 DOP 执行相互一致。

当同一镜头声称同时清楚呈现两个以上空间区域时，必须在 `visual_plan.spatial_strategy` 中选择并具体说明：

```text
foreground_background
deep_focus
compressed_depth
split_focus
blocking_reveal
sequential_reframe
```

分别用两个镜头拍摄空间两端人物时，不属于单镜多区域问题。即使两个镜头都是近景或特写，只要空间关系已经建立，视线方向、轴线侧别、银幕方向和相邻切换成立，就是合法的视听语言。机器不得用“距离远＋近景”或“多人＋特写”否定该方案。

只有单镜声称同时看清多个区域，却没有可执行的构图、光学、人物调度、焦点或摄影机重构方案时，才判定 `BLOCKED`。

遮挡消失只保护不可切的核心过程：遮挡开始、遮挡通过、遮挡驶离并显露结果必须在同一规划单元，使用 `non_cut_basis=blocking_proof` 与 `spatial_strategy=blocking_reveal`，并说明遮挡前后构图比对。关系建立、结果细节和人物反应分别接受切镜判断，不得被保护范围一并吞入。

## 5. Gate 2 展示

Gate 2 按场依次展示：

1. 场景视觉与声音策略；
2. 屏幕事件；
3. 切／留／镜内重构地图；
4. DOP 镜头表；
5. 轴线、视线、空间与执行风险；
6. 平均镜头时长、每分钟剪辑点、超过 10 秒普通镜头数、发言权交接与实际切镜数、多事件单元、非切例外和长镜保护范围。

逐场展示期间不产生新的确认。整集全部展示完成后只进行一次 Gate 2 确认。屏幕事件、观看决策、规划单元、长镜设计、节奏指标、DOP 视觉方案或内部规则修订号任一变化，旧 Gate 2 digest 立即失效。
