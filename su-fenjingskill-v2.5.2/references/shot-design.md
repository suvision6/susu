# Shot Design

本文件是 Gate 2 镜头规划、DOP 执行、人物调度、转场、阶段时长与长镜导演审计的唯一规则源。屏幕事件及切／留／重构以 [screen-event-and-cut-map.md](screen-event-and-cut-map.md) 为准。

## 目录

- [1. Gate 2 拆镜规划](#1-gate-2-拆镜规划)
- [2. 镜头决策](#2-镜头决策)
- [3. 拆合判断](#3-拆合判断)
- [4. 摄影机与调度](#4-摄影机与调度)
- [5. 来源顺序与导演性重排](#5-来源顺序与导演性重排)
- [6. 镜头阶段](#6-镜头阶段)
- [7. Long Take](#7-long-take)
- [8. 转场映射](#8-转场映射)
- [9. 规划到最终镜头](#9-规划到最终镜头)

## 1. Gate 2 拆镜规划

Gate 1 风格确认后，建立 Beat 与受保护 facts，再生成 `shot_plan` 并停在 Gate 2。规划是可确认的视觉镜头承诺：既决定为什么切，也决定切到谁、从哪里看以及采用什么核心摄影语法；它不是最终执行正文，也不得再称为“抽象规划”“大致方向”或留待终稿决定的摄影意向。

规划必须展示：

- 每场 `directing_plan`，且先于该场规划单元展示。
- 每场 `directing_plan.entry_strategy`，明确首镜如何进入、观众从哪里观看、必须先建立与有意暂缓的信息；它与 `pov_flow` 一起进入 Gate 2 digest。
- 把 Gate 1 profile 编译为场级的时间组织、摄影机参与、空间揭示、表演距离和声音策略。
- 计划镜头总数。
- 计划剪辑点总数。
- 计划总时长。
- 按场景与屏幕事件排列的全部规划单元，以及每单元完整 DOP `visual_plan`。
- 每对相邻屏幕事件的 `cut | hold | reframe` 决定；剪辑点由 `cut` 确定性派生。
- 逐场与全片的视角／景别／运镜分布、视觉坍缩提示，以及确有导演理由时提交的结构化 `visual_uniformity_reviews[]`。
- 场景确有需要时才展示特殊对白观看策略、受保护过程、`source_reuse`、导演性重排或连续性风险。

`planned_units[]` 只允许提供：

- 独立规划单元 ID 与顺序。
- 场景、Beat 和来源范围。
- 一个或多个 `screen_event_ids[]`。
- 估算时长。
- 抽象叙事目的。
- 必需的 `visual_plan`，锁定核心视觉语法。
- `shot_form=long_take + long_take_design`，只在导演明确采用长镜头并登记理由、收益与受保护事件范围时填写。
- `source_reuse`，只在相邻同场单元因结构原因必须完全复用 source spans 时登记。
- `dialogue_design`，只在对白存在特殊观看策略或空间风险时按 [dialogue-staging.md](dialogue-staging.md) 登记。

`visual_plan` 必须包含：

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

只有关键风格应用或有意例外才增加 `style_anchor_ids[]`。`perspective_intent` 只允许：

```text
wide_spatial
natural_relation
compressed_distance
detail_isolation
```

毫米数只在确有拍摄意义时作为可选信息。`movement_plan` 和 `spatial_strategy` 使用 [angle-and-camera-execution.md](angle-and-camera-execution.md) 的执行规则。`motivation` 必须说明当前观看方案的具体收益，不能写“丰富角度”“避免重复”或“更有电影感”。

规划不得提前提供最终镜号、人物 blocking、表演细节、确定性第五列或最终六列表。观看主体、景别、角度、机位、构图、透视、焦点、空间策略、运镜计划及起止画面必须在 Gate 2 前决定。`edit_points[]` 只从 `viewing_decisions.mode=cut` 派生，不维护第二套理由。

Gate 2 按场展示视觉与声音策略、屏幕事件、切／留／重构地图、DOP 镜头表及轴线与执行风险。DOP 表必须显示 `viewpoint_owner`、主体、景别、角度、机位、构图、透视、焦点、空间策略、完整 `movement_plan`、起止画面与动机；风格锚点只在关键应用或有意例外时显示。确认前运行只读 `review-gate-2`：`READY` 可展示确认，`REVIEW_REQUIRED` 必须把警告与拟保留理由一起交给用户，`BLOCKED` 必须先修复。逐场展示不产生新确认，全部场次结束后只确认一次。

`directing_plan.entry_strategy` 是场景首镜的结构化导演承诺：

```json
{
  "mode": "spatial_establish",
  "observer_position": "街道外部，可辨认汽车行驶方向和人物所在一侧",
  "required_spatial_information": ["汽车行驶方向", "外部目标所在一侧", "后续遮挡经过的轴线"],
  "withheld_information": [],
  "reason": "后续发现和遮挡依赖观众先理解街道与视线关系"
}
```

- `mode` 只允许 `spatial_establish | relational_entry | character_entry | subjective_entry | deliberate_withhold`。
- `observer_position` 必须说明观众／摄影机相对于场景、人物或主观锚点从哪里观看，不能只写“车内”“外景”“跟拍”等类别词。
- `required_spatial_information[]` 记录首镜或入口连续过程必须让观众理解的方向、位置、关系或视线条件；没有必需空间信息时可为空数组。
- `withheld_information[]` 记录有意暂缓揭示的信息；没有有意隐藏时可为空数组。被暂缓的信息不得与同一入口要求立即建立的信息互相冲突。
- `reason` 必须说明这种入口相对于其他可行入口为当前叙事、人物、空间或观看关系增加什么。
- `spatial_establish` 从可读空间关系进入，不等于机械使用大全景；`relational_entry` 先建立人物关系；`character_entry` 先贴近人物；`subjective_entry` 把观察位置绑定到具体人物或主观锚点；`deliberate_withhold` 有意延迟空间或信息揭示。
- 最终首镜及其必要入口连续过程必须兑现已确认的 `entry_strategy`。改变 mode、观察位置、必需／暂缓信息或其实现所依赖的镜头单元，必须更新规划并重新 Gate 2。

移动汽车场景若后续剧情依赖车外目标、道路方向、车辆行进关系或交通遮挡，默认采用 `spatial_establish`，先建立后续事件所需的空间条件。可以改用前挡玻璃关系镜等 `relational_entry`、人物近景等 `character_entry`、具体人物主观的 `subjective_entry` 或 `deliberate_withhold`，但必须在 `reason` 中写明不先完整建立空间的叙事收益，并保证后续发现、视线和遮挡仍可理解。后排中央等通用覆盖机位不是移动汽车场景的默认入口；只有当它对人物关系、疏离、压迫或信息隐藏具有明确收益时才成立。

统计由规划单元和观看决策确定性计算：

```text
planned_shot_count = len(planned_units)
planned_edit_point_count = count(viewing_decisions where mode == "cut")
planned_total_duration_seconds = sum(estimated_duration_seconds)
```

数量字段使用非负 JSON 整数。统计只报告当前导演方案，不反向形成风格配额。

## 2. 镜头决策

先理解整场，再按观看变化建立默认切点，最后审查哪些边界有足够证据不切：

1. 完整通读当前场，写出场景目标、推进和视点策略；节奏、出口、受保护过程与视觉转折按需补充。
2. 确定观众站在哪里看：先用 `entry_strategy` 锁定入口模式、观察位置、必须建立与有意暂缓的信息，再由 `pov_flow` 说明后续视点如何保持或转移，为景别、视角高度、机位、构图与人物调度提供方向。
3. 依次识别发言权、主要观看主体、观看尺度、信息／认知落点和动作发起者变化；每一变化先建立事件边界和默认 `cut`。
4. 再检查连续行动、持续表演、声音过程、空间穿越、遮挡证明、共享调度或延迟反打是否会因剪切受损；只有收益明确且 DOP 可执行时，才以 `non_cut_basis` 撤销切点。
5. 保护范围只覆盖真正不可切的核心过程，不得顺带吞并它前后的关系建立、信息细节或人物反应；不得从原文行数、标点或景别轮换机械反推镜头数。

候选镜头先判断起止边界、承担的视听过程，以及切与不切各自带来的结果。这里只形成导演判断；正式结构只记录镜头单元目的和已确认剪辑点的具体触发与收益，不增加逐镜问卷。

候选观看边界可以来自信息揭示、动作边界、视线对象变化、关系变化、空间重定位、主观视角、声音来源、表演停顿、节奏压力或延迟揭示。每个边界都必须明确选择切、留或镜内重构。

“信息揭示”“动作边界”等类别词不能单独构成合法理由。每个确认切点必须写清：

```text
trigger：触发边界的具体事件、声音、节奏或观看变化
editorial_gain：切开相对不切具体增加什么
```

按以下顺序消费上游信息：

1. 用 source facts、对白与连续性限定不可改写的可行范围。
2. 读取场景／Beat `director_analysis`，生成不同观察位置、视觉距离、关系重心、停留和剪辑点候选。
3. 用 `director_profile` 比较候选的节奏、镜头能量、空间策略与表演重心。
4. 回查候选是否改写对白、剧情事实、因果、关键动作或状态；出现改写即丢弃。与来源一致、不制造新事实的可逆表演或调度可以保留在导演字段中。

`dramatic_turn: null | steady` 合法，不要求制造转折镜。非空 `dramatic_turn` 也只提高候选价值，不自动产生独立镜头。`subtext` 可影响观察位置、停留与信息隐藏方式，不能直接成为画面动作。

## 3. 拆合判断

保留在同一镜头，只在时空与行动连续、表演不会被压扁、镜内调度能清楚呈现变化，并已登记有效 `non_cut_basis` 时成立。

拆为多镜是发言权、观看主体、尺度、认知落点和动作发起者改变后的默认方案；切点仍须写清具体触发和观看收益。

禁止：

- 一 Beat 一镜、按标点拆一句完整台词，或每次细小表情变化一镜。
- 只为换景别而切，没有任何信息、声音、节奏、情绪、空间、主观或观看收益。
- 为“电影感”补写无源事实空镜。
- 把“必须看清”机械等同为必须独立成镜。
- 为风格统计、模型限制或下游分组改变镜头。
- 同一句对白因标点或换行拆镜。
- 把没有独立观看价值的细小表情机械切出；新信息完成后的认知反应仍须先建立独立事件。
- 完全复用相同 source spans 却没有结构性理由。

连续过程确实可能被剪切破坏时，优先把它写入场级 `protected_processes[]` 或规划单元目的。只有复杂表演关系无法用自然语言清楚表达时才使用兼容的 `performance_chain`。

最终镜头的 `cut_design` 只记录 `entry_trigger` 与 `exit_trigger`；`isolation_intent` 仅作为旧版兼容字段。Gate 2 已确认的剪切理由和节奏不在终稿重复证明。

## 4. 摄影机与调度

Gate 2 确认后，每镜依次落实：

1. 原样采用已确认的观看主体、景别、角度、机位、构图关系、透视意图、焦点与空间策略。
2. 精确执行 `start_frame` 和 `end_frame`。
3. 执行 `movement_plan` 的触发、速度、路径和停止条件；固定镜头执行保持理由。
4. 人物起始位置、动作、结束位置、朝向与视线。
5. 表演、对白和环境行为的发生关系。
6. 到下一镜的真实转场，以及下一镜需要继承的结束状态。
7. 把同一连续过程写成一个权威 `execution_text`，以单一【画面内容】自然语言段落描述，顺序为：当前环境 → 摄影机当前相对位置和朝向 → 画面可见内容 → 人物动作与表情 → 人物台词 → 人物状态。镜内环境变化或人物位移必须写明。

摄影机运动必须服务信息、空间、关系或表演，不为消除校验提示而机械替换。`camera_energy=static` 只表示运动克制的风格倾向，不授权全片默认平视或固定；每镜的视角高度与运镜仍须由当前叙事目的、空间条件、人物关系、观察位置和表演过程推导。

首镜必须执行 Gate 2 已确认的 `directing_plan.entry_strategy`，并与 `pov_flow` 和首个规划单元的 `narrative_purpose` 一致。入口可以从空间、人物、物件、声音、缺席、遮挡、身体局部或主观感知进入，也可以有意延迟空间揭示；但选择必须归入已确认的入口模式，且不能漏掉 `required_spatial_information[]` 或提前泄露 `withheld_information[]`。

摄影机至少说明景别、视角高度／机位、构图关系和运动。字段不承担术语考试；只要观看位置、主体关系和运动清楚、可执行且不自相矛盾即可。不得把整场观察位置、导演风格或上一镜选择直接复制成后续所有镜头的视角高度或运镜。发现 Gate 2 规划不成立时，回到规划并重新确认，不得在终稿靠临时改一镜规避告警。

第五列镜头头统一渲染为：

```text
【景别｜角度｜运镜】
```

例如：

```text
【全景｜微俯视｜摇臂下降】
【中景｜平视｜缓慢推进】
【中景→特写｜微仰视｜缓慢推进】
【全景｜平视｜斯坦尼康跟随】
【近景｜平视｜固定】
```

景别、角度与运镜按需自然组合，景别变化可用“→”连接。景别只写合法景别，角度只写高度／俯仰关系，运镜只写摄影机行为及必要速度方向。人物、地点、构图结果、主体关系、动机和揭示结果不得混入三元素。机位、构图、主体、焦点、空间策略与焦段保留在结构化 DOP 方案和【画面内容】中。

终稿 camera 必须逐项绑定规划的观看归属、主次主体、景别、角度、机位、构图、透视、焦点、空间策略、完整运镜计划、起止画面和动机。第五列不得显示内部轴线 ID 或机器状态，也不要求逐字复述结构化字段，但自然语言过程不得与其冲突。

已明确登记的视觉关系必须互相兑现：

- `over_shoulder` 的 position 必须位于 `foreground_characters[]` 对应人物肩后或肩侧，logic 朝向主拍人物。
- `subjective` 必须把观察位置绑定到具体人物或明确主观锚点。
- 俯视机位不得写成主体下方仰看，仰视机位不得写成主体上方俯看。
- 固定／静止运镜不得在 logic 中再次声明推进、拉出、横移、跟随、环绕或摇摄。
- `insert` 围绕明确道具或局部建立位置，`environment` 围绕空间方向建立位置；二者不得套用人物肩后关系。
- 景别不由人物间物理距离机械决定。走廊两端人物分别使用近景或特写完全合法；只检查空间关系、轴线、视线、银幕方向与相邻切换。
- 单镜覆盖多个空间区域时，只有缺少可执行的前后景、深焦、压缩、分焦、遮挡揭示或顺序重构方案才 FAIL。

每镜第五列以【景别｜角度｜运镜】开头，随后直接接【画面内容】段落。人物位置、朝向、视线或在场状态真实改变并影响后镜时，应在【画面内容】中自然写出位移或状态变化，并由 `continuity_updates[]` 登记供后续继承。

正文只读取唯一 `execution_text`。旧版 `execution_passages[]` 只能作为迁移材料，不是 2.5.2 权威正文。正式新建正文不再拆分【镜头调度】【人物表演与声音】【镜头结束】三段，而是写成一个连续的【画面内容】段落，顺序为：

```text
初始画面 → 镜内动作／焦点／摄影机变化 → 结束画面
```

镜内出现环境变化或人物位移（行走、奔跑、摔倒等）必须写明。分段内容必须是摄影机和演员可执行、现场可观察的过程。原文动作可以保留，但只复制或改述原文、没有调度关系、表演／声音处理或结束画面时不构成完整导演执行。可逆表演细节可以进入导演执行或按需 `performance.visible_behavior`，不得改变剧情状态或补写因果。

每场镜头完成后连续通读该场全部权威执行正文，修正主语、指代、动作因果、句式重复和翻译腔。`承载、落实、验证、作为落点、具体化` 等导演分析语言不得代替可见画面；分析只留在内部导演字段。

相邻镜头检查已确认的 `trigger + editorial_gain` 是否仍然成立。改变景别不等于获得剪辑收益；声音、节奏、情绪、主观性或延迟揭示可以构成真实收益，不要求伪造信息增量。

不要使用以下伪硬规则：

- 不强制每场首镜为全景；依据 `entry_strategy`、当前观众已知空间、人物关系和导演策略选择首镜。移动汽车且后续依赖外部目标、道路方向或交通遮挡时，按本节的条件默认先建立必要空间，不把这一条件规则扩大为所有场景的首镜配额。
- 不用“变化不足 30°”自动判错；检查实际信息增量、轴线和空间可读性。
- 不把相邻推／拉方向变化一概判错；检查动机、结束构图与空间连续性。

## 5. 来源顺序与导演性重排

- `beats[]`、`facts[]` 永远保留来源顺序。
- `screen_events[]` 按同场 `event_order` 保持来源单调顺序；每个事件的 `beat_ids` 精确来自其 `covered_fact_ids`。
- `planned_units[]` 默认按来源锚点单调前进。
- 需要导演性重排时，在 Gate 2 规划的 `reorders[]` 中列出连续规划单元、完整来源范围和具体导演理由。
- 重排来源范围必须坐标包含所有被重排单元；声明必须实际对应至少一次来源倒序。
- Gate 2 digest 绑定重排；未声明或旧确认失效时禁止最终镜头倒序。
- 最终镜头只复现已确认规划顺序，不得临时新增倒叙、插叙或反应提前。
- 同一规划单元内的 `screen_event_ids` 与最终 `shot_phases[]` 不得倒序；需要重排时先拆成多个规划单元，再用 `reorders[]` 声明。

## 6. 镜头阶段

每镜同时登记 `duration_seconds` 与有序 `shot_phases[]`。每阶段包含：

```text
phase_id
phase_order
screen_event_ids[]
duration_seconds
camera_state
sound_fact_ids[]
```

镜头时长等于阶段时长求和。同时发生的事件可以共用阶段；明确顺序发生的事件必须进入不同阶段。阶段只表达真实观看进程，不把所有动作、对白、表演和摄影机默认塞入一个同步块。对白时长、动作时间、停顿、焦点和运动都必须在对应阶段的自然语言摄影机状态中可读。

## 7. Long Take

普通剧情镜省略 `shot_form`，且 `estimated_duration_seconds` 不得超过 10 秒。超过 10 秒必须拆镜；只有确有连续时间、空间或表演收益时才可显式写 `shot_form=long_take`，并提交：

```json
{
  "reason": "完整保留表演发展与真实时间压力。",
  "supports": ["performance_development", "real_time_tension"],
  "protected_event_ids": ["SEV008"]
}
```

`supports[]` 只允许 `continuous_action | performance_development | spatial_progression | blocking_proof | real_time_tension`。保护范围只能引用当前单元事件。

终稿 `director_audit.long_take` 继续使用：

```json
{
  "status": "supported",
  "reason": "表演与空间关系持续变化。",
  "supports": ["performance_development", "spatial_progression"]
}
```

- 状态只允许 `supported | needs_review`。
- `needs_review` 产生 WARN。
- 超过 10 秒且包含说话者变化、多个观看主体、尺度跳变、认知落点或多个顺序动作时，不允许靠长镜理由保留，必须拆镜。
- 遮挡证明只保护遮挡开始至结果显露的核心区间；前置关系、后置细节与人物反应不在保护范围内。

## 8. 转场映射

`director_profile.transition_language` 与 `shot.transition_to_next.type` 使用闭合映射：

| director profile | shot transition |
| --- | --- |
| `hard_cut` | `cut` |
| `action_cut` | `action_cut` |
| `gaze_cut` | `gaze_cut` |
| `sound_bridge` | `sound_bridge` |
| `long_hold` | `hold` |
| `dissolve` | `dissolve` |
| `fade` | `fade` |

映射保证术语稳定，但 `director_profile.transition_language` 只表达风格倾向，不是具体场景转场的许可白名单。

每个非末镜的 `transition_to_next` 包含 `type` 与匹配该规划边界的 `edit_point_id`；末镜的 `transition_to_next` 固定为 `{ "type": "scene_end", "edit_point_id": null }`。`scene_end` 只作为末镜类型使用，不携带生成分组或下游 Cut 链含义。

`action_cut` 仍须满足连续性合同中的动作接续 ID。

## 9. 规划到最终镜头

Gate 2 确认后：

- 每个最终镜头按数组顺序一对一引用一个 `plan_unit_id`。
- 最终镜头总数、顺序、场景、Beat 范围与 source spans 必须匹配规划；存在 `shot_form=long_take` 时也必须匹配。
- 最终 camera 的景别、角度、机位、构图、主体与归一化运镜必须兑现对应 DOP `visual_plan`；透视、焦点、空间策略和起止画面由规划与阶段执行共同兑现。
- 每个相邻最终镜头边界通过 `transition_to_next.edit_point_id` 一对一引用已确认剪辑点；末镜 `edit_point_id` 为 `null`。
- 任何增删、换序、长镜意图、剪辑点或核心视觉字段改变都先更新规划并重新 Gate 2。
- 最终分镜完成后直接构建正式交付，不增加人工确认 Gate。
