# Scene Strategy & Gates｜场级策略与审批失效

## 1. 场级策略

每场在设计正式镜头前形成：

- entry_state / exit_state；
- dramatic_task / turn_or_progression；
- primary_mechanism / optional secondary_mechanism；
- mechanism_shift_trigger（存在时）；
- protected_processes；
- required_clarity / delayed_information；
- audience_knowledge_path；
- blocking_space_strategy；
- time_edit_structure；
- shot_density_curve；
- performance_strategy；
- sound_strategy；
- camera_grammar：
  - `dominant_principle`：本场观看的主导摄影原则；
  - `change_triggers[]`：改变画面所有权、距离、角度、焦点或运动的具体事件；
  - `progression`：首镜至尾镜的观看发展；
  - `uniformity_intent`：仅在整场 framing、角度、运动和画面所有者全部同质时填写具体统一理由，否则为空；
- opening / turn / ending function；
- method_application；
- conflict_resolution；
- intentional_exceptions；
  - topology；每个 unit 的 `viewing_design`；每个真实相邻边界的 trigger 与 editorial_gain。

无明显转折的等待、劳动、观察、仪式或积累场景，不虚构转折。场级策略不额外承担制片管理字段。

## 2. Gate 1

- `user_specified`：用户明确指定方法，已展示编译摘要且无实质歧义；
- `confirmed`：用户从最多两个实质不同的方法方案中确认；
- `required`：未指定、只给模糊风格或存在会改变拓扑的解释冲突；
- `invalidated`：其内容依赖已经变化。

Gate 1 审批必须以当前 `source_model_hash + method_hash` 形成的内容哈希为依据。不能仅编辑状态字段恢复通过。

## 3. Gate 2

Gate 2 展示并确认：

1. 场景机制与变化；
2. 方法在本场的具体应用；
3. 观众位置和信息路径；
4. 每个镜头单元的画面所有权、画内／画外主体、读取尺度、framing、摄影机响应与具体理由；
5. 每个切点的具体触发和相对不切的观看收益；
6. 镜内与镜间编辑结构；
7. 节奏和声画关系；
8. 场级 camera grammar、核心摄影与调度；
9. 来源绑定与连续性例外。

Gate 2 的内容哈希覆盖 strategy、camera grammar、topology 与 viewing design。每个 `viewing_design` 必须包含：

- `owner_type`：`subject | relationship | object | space | subjective`；
- `owner_refs[]`；
- `visible_subjects[]` / `offscreen_subjects[]`；
- `reading_priority`：`space | relationship | body | face | detail`；
- `framing_intent`：`single | two_shot | group | over_shoulder | insert | subjective | space`；
- `camera_response`：`observe | isolate | reframe | follow | reveal | withhold`；
- 针对本单元事件的 `reason`。

每场 N 个单元必须恰有 N−1 个 `boundary_to_next`；末单元不填写边界。`relation + trigger + editorial_gain` 是唯一切点证明，类别词、换景别或“增强电影感”不能单独成立。Gate 2 只确认观看设计与切点，不把字段和证明写入 XLSX。

不设置单人、景别、角度、运动或 framing 数量配额。若整场 framing、角度、运动和画面所有者全部相同，`uniformity_intent` 必须针对当前场景事件和方法说明为什么统一优于变化，并由用户重新确认 Gate 2；缺失或空泛时不能正式构建。不同单元复用完全相同的观看／摄影理由触发 `CAMERA_DECISION_TEMPLATE_COLLAPSE`。周期轮换类别不能替代导演理由。

## 4. Alignment

Alignment 是正式执行层审批，不是第三个创作 Gate。它证明当前正式 shot model 与来源、推断、假设及已确认拓扑一致。

执行哈希覆盖：

- shot / scene ID；
- duration 与 duration basis；
- motivation；
- viewpoint；
- camera；
- staging；
- sound；
- edit；
- continuity；
- assumptions；
- notes；
- canonical execution text；
- shot_flow 镜内顺序；
- passage/fact/inference binding；
- scene 的空间、光线和色彩执行字段。

## 5. 唯一失效矩阵

| 变化 | Gate 1 | Gate 2 | Alignment |
| --- | --- | --- | --- |
| locked source、语言权威、分类、scope、unit、passage、fact、source gap、补充参考事实或导演方法 | invalidated | invalidated | invalidated |
| 场景机制、scene strategy、camera grammar、topology、viewing design、trigger 或 editorial_gain | 保持 | invalidated | invalidated |
| 正式 viewpoint、camera、framing、visibility、staging、performance、sound、edit、continuity、duration、motivation、assumption、notes、execution text、shot_flow 或 XLSX 投影 | 保持 | 保持 | invalidated |

规则只有这一份。运行时 `lock` 依据当前内容哈希执行，不允许文档另设例外。

## 6. 审批事件

`approval_events[]` 是按顺序追加的哈希链。每个事件至少保存：事件类型、当前内容哈希、reviewer、note、时间、前一事件哈希和事件哈希。

允许的正式状态转换由 CLI 完成：

```text
approve-gate1
confirm-gate2
approve-alignment
approve-classification
```

具有文件写权限的人仍可整体篡改文件，因此该事件链用于可审计一致性，不宣称提供操作系统级身份认证。正式项目若需要不可抵赖审批，应把已批准 workspace 的 hash 保存到外部只读系统。

## 7. 人机边界

机器检查 Schema、哈希、引用、审批状态、viewing design／正式执行一致性、无理由极端同质、重复理由模板和确定性矛盾。题材机制、具体摄影审美和长镜／跳切／蒙太奇是否有效，仍由导演或用户复核；统计比例不得替代判断。
