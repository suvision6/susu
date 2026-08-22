# Migration Guide｜v2.5.8 → v3.0.0

v3 是重大认知重构，不覆盖 v2.5.8。迁移目标不是把旧 JSON 无损转换成新 JSON，而是保留来源与导演成果，同时删除会压制导演判断的流程层。

## 1. 版本策略

```text
保留：su-fenjingskill-v2.5.8/
新增：su-fenjingskill-v3.0.0/
```

旧项目可以继续由 v2.5.8 构建。需要迁移时，先复制旧项目数据，再生成 v3 新文件；不要原地覆盖旧 JSON 或旧交付。

## 2. 核心观念迁移

| v2.5.8 | v3.0.0 |
| --- | --- |
| Schema 与脚本拥有最高结构权威 | 导演语义拥有创作权威，Schema 只拥有字段类型 |
| Gate 1 风格确认 | 用户指定风格时才编译，不强制 Gate |
| Gate 2 DOP 规划确认 | 默认直接生成导演方案；用户要求时再分阶段评审 |
| stage digest / confirmation intent | 删除，不进入 v3 数据 |
| screen events 先原子化 | 先理解戏剧变化和 Blocking |
| 相邻事件默认 cut | cut / hold / reframe 每次独立判断 |
| planned_units 与 shots 一对一绑定 | shots 直接承载镜头动机和执行 |
| 视觉均匀度比例复核 | 只作为人工 WARN，不产生艺术 FAIL |
| 严格字段闭合 | 核心字段必需，其余按镜头需要填写 |
| 小歧义暂停流程 | 假设清单＋READY_WITH_ASSUMPTIONS |
| build WARN 返回非成功并易卡住 | WARN 保留完整交付，不吞掉导演成果 |

## 3. 字段映射

### 来源

| v2.5.8 | v3.0.0 | 处理 |
| --- | --- | --- |
| `source.locked_text` | `source.locked_text` | 原样保留 |
| `source.delivery_slug` | `source.delivery_slug` | 原样保留；缺失可用临时 slug |
| `source.input_kind` | `source.input_kind` | 映射到四种 v3 模式 |
| `approved_corrections` | `assumptions[]` 或外部变更记录 | 只迁移仍影响方案的项目 |
| `dialogue_language_policy` | `source.dialogue_lines[]` + assumptions | 保留真实口播，不保留复杂 Gate 状态 |
| facts / source spans | `shots[].source_excerpt` | 回切实际原文段落；不强制保留全部内部 fact ID |

### 导演分析与风格

| v2.5.8 | v3.0.0 | 处理 |
| --- | --- | --- |
| `source_analysis` | `director_design` | 重写为场景任务、转折、观众位置等导演语言 |
| `director_profile` | `director_design.visual_strategy` 等 | 将闭合轴编译为可执行场级策略 |
| `director_style_options[]` | 删除或迁移为方案备忘 | 不进入正式合同 |
| `style_anchors[]` | 场级 visual / sound / rhythm strategy | 只保留真正影响镜头的指令 |

### 屏幕事件、规划和剪辑

| v2.5.8 | v3.0.0 | 处理 |
| --- | --- | --- |
| `screen_events[]` | `shots[].staging`、`source_excerpt` | 合并回真实镜头过程，不保留事件配额 |
| `viewing_decisions[]` | `shots[].edit` + `motivation.cut_or_hold_reason` | 重新判断，不机械沿用默认 cut |
| `planned_units[]` | `shots[]` | 每镜直接保存镜头动机和执行 |
| `visual_plan` | `shots[].camera` | 保留有导演意义的摄影信息 |
| `edit_points[]` | `shots[].edit` | 只保留真实切点与连接 |
| `reorders[]` | `shots[].edit` 或场级说明 | 仅在导演性时间重组存在时保存 |

### 对白与声音

| v2.5.8 | v3.0.0 | 处理 |
| --- | --- | --- |
| dialogue facts | `source.dialogue_lines[]` | 逐字保留 |
| `dialogue_playbacks[]` | `shots[].sound.dialogue_segments[]` | 按镜头顺序拼接完整 |
| `script_voice_type` | `dialogue_lines[].voice_type` | 保留来源属性 |
| `shot_delivery` | `dialogue_segments[].delivery` | 保留当前镜头落位 |
| `dialogue_design` | `shots[].motivation`、`sound`、`staging` | 用自然导演判断替代特殊对象堆叠 |

### 时长、表演和连续性

| v2.5.8 | v3.0.0 | 处理 |
| --- | --- | --- |
| `duration_design` | `duration_seconds` + `duration_basis` | 保留同步／顺序／停顿逻辑，不保留重型分解 |
| `rhythm_design` | `director_design.rhythm_strategy` | 改为场级节奏曲线 |
| `performance.visible_behavior` | `shots[].staging.performance` | 只保留真正影响观看的可见行为 |
| `initial_continuity` | `scenes[].space_map.protected_continuity` | 风险型追踪 |
| `continuity_updates` | `shots[].continuity.state_updates[]` | 只记录真实变化 |
| `intentional_exceptions` | `shots[].continuity.intentional_breaks[]` | 增加观众效果和重新定向 |

### 交付

| v2.5.8 | v3.0.0 |
| --- | --- |
| `shot-data/2.5.8` | `director-shot-data/3.0.0` |
| 六列 Markdown / XLSX | 六列保持不变 |
| validation report | 保持，但 WARN 不阻断 |
| Gate digest | 删除 |
| content hash | 可由外部版本系统负责，不是核心必需 |

## 4. 迁移步骤

1. 锁定一份 v2.5.8 原始数据和交付，不修改。
2. 复制 `source.locked_text`、title、slug 和逐字对白。
3. 重新做一次导演读场，不直接复制旧 screen events 和默认切点。
4. 从旧 Blocking、camera、continuity 中提取仍然成立的物理信息。
5. 对每个旧镜头做删除测试：无不可替代作用的镜头删除或合并。
6. 为保留镜头写新的 `motivation.reason` 和 `cut_or_hold_reason`。
7. 把旧 visual plan 编译到 v3 camera，删除仅为闭合字段而存在的内容。
8. 重建对白跨镜片段，校验逐字拼接。
9. 估算时长，保留表演与声音所需时间。
10. 运行 v3 validator，人工复核 WARN。
11. 新建 v3 交付文件，不覆盖旧文件。

## 5. 不应自动迁移的内容

- Gate 1 / Gate 2 状态、确认语句和 digest。
- 三候选风格清单及候选编号。
- 默认 cut 产生的事件边界。
- 仅为角度／运动比例审计而添加的镜头。
- 重复的 style anchor、reason、模板化 execution text。
- 没有实际拍摄或叙事价值的状态字段。
- 因旧 Schema 闭合而出现的空对象、占位数组和冗余 ID。

## 6. 回滚

v3 不修改旧目录，因此回滚只需继续使用 v2.5.8 数据和脚本。不要把 v3 JSON 直接传给 v2.5.8 构建器。
