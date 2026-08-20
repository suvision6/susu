# 合镜规则

合镜只组织 Prompt 单元，不改变或回写源镜。来源顺序不变，一条源镜始终对应一个 Cut。

## 两层合同

先审阅相邻边界的语义，再由脚本选择最终分区。不得用最终想拆或想合的结果反向填写语义：

1. `semantic compatibility` 回答两镜在十个维度是否可共处同一连续生成单元；
2. `classification` 只允许 `hard_split | prefer_join | prefer_split`；
3. `scene-global-dp-v1` 读取整个连续范围、全部边界和 Profile 容量后统一求解分区。

时长与 Cut 数是容量，不是语义。容量不足由分区器产生拆点，不得把 compatibility 改成 false。

## Profile 容量

| Profile | 单元最长 | 最大 Cut |
|---|---:|---:|
| `seedance-2.5-default` | 30 秒 | 10 |
| `seedance-2.0-default` | 15 秒 | 5 |
| `generic-video` | 15 秒 | 5 |

未知时长不能参与多 Cut 单元。单条源镜没有独立的 15 秒合镜门槛：例如 Seedance 2.5
中的 20 秒源镜可与 5 秒连续源镜组成 25 秒单元；Seedance 2.0 仍受单元 15 秒上限约束。

## 边界分类与证据

### 硬拆 `hard_split`

只用于来源可验证的断裂：`scene_change`、`reality_layer_change`、`time_change`、
`source_unavailable`。脚本从场景、现实层、时间和可编译状态复算；证据与来源冲突即拒绝。

### 偏好合 `prefer_join`

十项 compatibility 必须全部为 true，并至少有一项正向证据：`same_scene`、
`same_reality_layer`、`same_time`、`boundary_state_match`、`action_continuation`、
`causal_continuation`、`question_answer` 或 `dialogue_exchange`。

同场景本身不是无条件合镜命令，但同场景、同连续时空再加动作、因果、问答、对白或
边界状态承接，是强正向证据。可由来源直接观察的证据由脚本复算。

### 偏好拆 `prefer_split`

用于非硬性但值得保护的边界：`protected_performance`、`camera_state_discontinuity`、
`subject_focus_reset`、`narrative_phase_change`、`information_density`。十项全兼容时也可以
偏好拆，但必须给出上述具体理由，不能写空泛的“测试要求分开”。

信息密度按“一个阶段一个主要状态变化”审阅。高密度不是自动拆镜；只有同单元会迫使
多个主要状态在同阶段竞争时才作为偏好拆证据。

## `grouping-review/2.0.3`

多镜输入必须包含：

- `contract: grouping-review/2.0.3`；
- 与当前来源一致的 `source_observed_hash`；
- `partition_policy: scene-global-dp-v1`；
- N 个源镜恰好 N-1 个有序 boundary；
- 每个 boundary 包含左右镜号、十项 `compatibility`、`classification`、非空
  `semantic_evidence[]` 和具体 `reason`；
- 禁止旧字段 `decision`、`constraint_reason` 和 `groups`。

十项 compatibility 为 `scene`、`reality_layer`、`subjects`、`action`、`space`、
`time`、`continuity`、`dialogue`、`narrative_intent`、`camera_state`。

脚本验证完整覆盖、顺序、hash、受控枚举、来源可观察证据和硬拆一致性；然后用全范围
动态规划先最大化偏好满足度，再最少化单元数与孤立单镜，最后以“较早单元优先完整”
作为稳定 tie-break，并在 Profile 时长与 Cut 数内生成唯一分区。相同输入必须得到相同分区。
多镜单元保存 `partition_strategy` 与逐边界 `boundary_evidence`。

## Operations 与局部失败

每个 operation 独立审阅和分区。`generate`、`edit`、`extend` 不能混为一个主任务；
显式 operations 各自携带完整 `grouping_review`。不可读源镜只阻断对应单元，不能借相邻镜补写。
