# Scene Strategy & Gates｜场级策略与自适应双 Gate

## 1. 场级策略

每场在设计镜头前形成：

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
- opening / turn / ending function；
- method_application；
- conflict_resolution；
- intentional_exceptions；
- production_risks。

无明显转折的等待、劳动、观察、仪式或积累场景，不虚构转折。

## 2. Gate 1 状态

- user_specified：用户明确指定方法，已展示编译摘要且无实质歧义；
- confirmed：用户从最多两个方法方案中确认；
- required：未指定、只给模糊风格或存在会改变拓扑的解释冲突；
- invalidated：来源或导演方法发生变化。

不解析复杂确认同义词，不把候选选择误当方法确认。

## 3. Gate 2 展示

先展示创作方案，再展示风险：

1. 场景机制与变化；
2. 方法在本场的具体编译；
3. 观众位置和信息路径；
4. 镜头单元及核心边界；
5. 镜内与镜间编辑结构；
6. 节奏和声画关系；
7. 核心摄影与调度；
8. 来源、连续性和制作风险。

统计只用于描述，不得成为通过条件。Gate 2 confirmed 后直接执行和交付。

## 4. Review lock

内部 review_lock 绑定：

- source_hash；
- method_hash；
- strategy_hash；
- topology_hash；
- gate_1 status / basis；
- gate_2 status / confirmation note。

失效规则：

- source_hash 变化：Gate 1、Gate 2 invalidated；
- method_hash 变化：Gate 1、Gate 2 invalidated；
- strategy_hash 或 topology_hash 变化：Gate 2 invalidated；
- 只有 execution_text、措辞、非核心执行细节改变：Gate 2 保持。

## 5. 人机边界

机器可以检查哈希、引用、状态和确定性矛盾。题材机制是否准确、方法是否真的改变剪辑、镜头密度是否有效、长镜／跳切／蒙太奇是否值得，必须由导演或用户复核。
