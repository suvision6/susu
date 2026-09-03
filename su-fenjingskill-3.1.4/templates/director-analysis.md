# 导演设计摘要

## Gate 0 成片格式与节奏

- rhythm_profile（十分钟以内短剧／平台长剧集／3–20分钟短片／长片电影／custom）：
- target_runtime_seconds：
- aspect_ratio：
- orientation：
- dialogue_pace_profile：
- standard_id：su-dialogue-pace/1.0
- rate_basis：articulation_rate_excluding_pauses
- range_min_cps / range_max_cps：
- default_cps / selected_cps：
- strong_pause_seconds：
- soft_pause_seconds：
- 对白速度依据：
- pace_overrides（无则空）：
- coverage_bias：
- 用户确认说明：

## 场景机制

- 主机制：
- 辅机制（无则省略）：
- 机制切换触发（无则省略）：
- 受保护过程：
- 必须清楚：
- 延迟信息：
- 时间敏感节拍：
- 常见失败：

## 导演方法

- 主方法：
- 方法来源：
- 时间模型：
- 基本编辑单元：
- 边界优先级：
- 不切条件：
- 视点与信息权限：
- 空间揭示：
- 表演与声画关系：
- 本场例外：

## 场景任务

- 开始状态：
- 人物目标：
- 阻力：
- 戏剧问题：
- 转折点：
- 结束状态：

## 观众与信息

- 观众位置：
- 主要视点：
- 必须先建立的信息：
- 有意暂缓的信息：
- 画外空间：

## Blocking 与空间

- 空间锚点：
- 人物起位：
- 主要动作路径：
- 关系线／轴线：
- 关键道具与声源：

## 摄影策略

- 摄影机参与：
- 视觉距离：
- 透视／焦段：
- 构图与焦点：
- 光线与色彩：

## 场级摄影语法（camera_grammar）

- dominant_principle：
- change_triggers：
- progression：
- uniformity_intent（仅当整场 framing、角度、运动和画面所有者全部同质时填写；否则留空）：

## 声音与节奏

- 声音视点：
- 环境与画外声：
- 剪辑连接：
- 节奏曲线：

## 对白观看机会

- 每个来源对白 ID 按顺序填写一次：
  - dialogue_id：
  - speaker：
  - listener_refs：
  - power_center_refs：
  - attention_shift：
  - picture_steps：
    - text_span：
    - topology_unit_id：
    - entry_decision（establish / cut / hold / reframe）：
    - cut_phase：
    - owner_type / owner_refs：
    - framing_intent：
    - visible_development：
    - picture_value：

## Gate 2 镜头拓扑

- 镜头单元（逐单元填写）：
  - unit_id：
  - 内容与完整过程：
  - viewing_design：
    - owner_type（subject / relationship / object / space / subjective）：
    - owner_refs：
    - visible_subjects：
    - offscreen_subjects：
    - reading_priority（space / relationship / body / face / detail）：
    - framing_intent（single / two_shot / group / over_shoulder / insert / subjective / space）：
    - camera_response（observe / isolate / reframe / follow / reveal / withhold）：
    - frame_axis（horizontal / vertical / depth / layered / centered / diagonal / subjective）：
    - aspect_ratio_fit：
    - reason（针对本单元事件，不使用跨镜套话）：
  - boundary_to_next（末单元省略）：
    - relation：
    - trigger：
    - editorial_gain：
- 镜内操作：
- 镜间关系：
- 交叉／蒙太奇／省略（存在时）：
- 首镜功能：
- 转折镜功能：
- 尾镜功能：
- 核心摄影承诺：

Gate 2 提交前复核：不机械正反打不等于不用单人，完整过程不等于始终同框，克制不等于全平视全固定；没有类别配额，极端同质必须有具体 uniformity_intent，跨单元不得复制 viewing reason。

## 逐镜时长

- timing_plan.status：ready
- pace_ref（BASE 或 POxxx）：
- blocks（无缝覆盖 shot_flow）：
  - block_id：
  - flow_start_index / flow_end_index：
  - mode（parallel / sequential）：
  - dialogue / action / camera / sound / reaction / hold seconds：
  - computed_seconds：
- computed_duration_seconds：
- confidence：
- basis：

## 假设与待确认项

- 无则省略。
