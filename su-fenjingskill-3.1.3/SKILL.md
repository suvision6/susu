---
name: su-fenjingskill
description: 将完整剧本、连续场景、锁定片段或概念材料拆解为具有视听逻辑的六列导演分镜和 director-shot-data/3.1.3。锁定来源与对白后，按场景机制和已确认方法决定观看、完整过程、切点与摄影执行；XLSX 是人类前端，其余三文件是同源 Agent 后端；不生成图片、视频 Prompt、视频或下游 Cut 分组。
---

# 导演分镜 3.1.3

## 职责与权威

以导演、摄影师和剪辑师的联合视角工作：

```text
锁定来源与用户要求
→ 全剧因果和人物关系
→ 场景机制
→ 已选导演方法
→ 观众位置、画面所有权与完整过程
→ 场级摄影语法与镜头拓扑
→ 摄影、调度、表演、声音、剪辑与时长
→ 固定交付
```

正式／内部合同为 `director-shot-data/3.1.3`、`director-workspace/3.1.3`。JSON、Markdown、validation 是 Agent 后端；XLSX 是唯一人类前端，保留六列“导演分镜”和全剧摘要“导演设计”。

## 七层工作流

### 1. 来源事实

建立权威语言、scope、非空来源行、连续 passage、逐字对白、受保护事实、来源缺口和补充事实台账。非空行默认属于叙事；每个叙事 unit 由 required fact 持有，主体、结果、否定、因果、声音身份、世界规则和结局不得静默反转。

读取 [source-truth-audit.md](references/source-truth-audit.md)；中文或含中文来源同时读取 [chinese-context-language.md](references/chinese-context-language.md)。

### 2. 场景机制

逐场选择一个主机制和最多一个辅机制，明确受保护过程、因果和信息节拍。

读取 [scene-mechanisms.md](references/scene-mechanisms.md)。

### 3. 导演方法

把参考编译为可执行的时间、边界、视点、空间、表演、摄影和声画方法；不复制镜头。

未指定方法时最多给两个真正不同的方案；用户明确指定且无实质歧义时，可记录为 `user_specified`，不额外阻断。

读取 [director-method-contract.md](references/director-method-contract.md) 与 [director-method-index.md](references/director-method-index.md)。

### 4. 场级策略与 Gate 2

把“机制 × 方法”解算为信息路径、完整过程、`camera_grammar` 和拓扑。每个 unit 先确认 `viewing_design`（owner/refs、画内外主体、读取尺度、framing、camera response、具体理由）；相邻单元只存 `trigger + editorial_gain`。Gate 2 证明不进入 XLSX。

唯一失效矩阵：

| 变化 | Gate 1 | Gate 2 | Alignment |
| --- | --- | --- | --- |
| 原始来源、语言权威、来源分类、passage、fact、来源缺口或方法变化 | 失效 | 失效 | 失效 |
| 场景机制、场级策略、camera grammar、viewing design 或镜头拓扑变化 | 保持 | 失效 | 失效 |
| 正式 viewpoint、机位、运动、景别、可见性、调度、表演、声音、剪辑、连续性、时长、动机、备注或前端投影变化 | 保持 | 保持 | 失效 |

执行层变化不得错误作废 Gate 2，但必须重新批准 Alignment。读取 [scene-strategy-gates.md](references/scene-strategy-gates.md)。

### 5. 镜头与剪辑

固定次序：整场 → 观众信息 → 完整过程 → owner 与画内外主体 → 读取尺度与 framing → 景别／角度／焦点／摄影机响应 → 比较不切与切开 → 拓扑。无新增观看收益就不加切点。

- 镜内：保持、调度重构、摄影机重构、焦点／光线／声音转移。
- 镜间：硬切、反应切、动作切、视线切、匹配、跳切、省略、交叉剪辑、蒙太奇、声音先行／滞后／桥接、叠化和场景转场。

边界写具体触发与相对不切的收益；类别词、换景别或“增强电影感”不能成立。读取 [shot-edit-grammar.md](references/shot-edit-grammar.md)。

### 6. 摄影、表演与声音执行

在已确认拓扑内落实 viewpoint、framing、可见性和执行。发言者与 owner 分开判断；`onscreen` 可见，`os` 在画外。非固定运动有触发、路径、速度和停止条件。

不机械正反打不等于不用单人镜头；保护完整过程不等于始终同框；摄影机克制不等于全平视、全固定。不设单人、景别、角度或运动配额。整场观看、framing、角度和运动全部同质时，只有 Gate 2 已确认的具体 `uniformity_intent` 才可成立；跨单元复制观看理由属于模板坍缩，周期轮换类别不能冒充导演设计。

shot model 是唯一后台事实源；`shot_flow[]` 顺序引用镜内事实。XLSX 只从 camera、shot_flow 与对白投影摄影头和一个画面自然段。

按需读取 [blocking-space-continuity.md](references/blocking-space-continuity.md)、[cinematography-language.md](references/cinematography-language.md)、[dialogue-performance-sound.md](references/dialogue-performance-sound.md) 与 [editing-rhythm-duration.md](references/editing-rhythm-duration.md)。

### 7. 固定交付

通过 Schema、来源、Gate 2 和 Alignment 后，仅用原子入口生成四文件：

```text
python -m scripts.storyboard_delivery build-all \
  --input <shot-data.json> \
  --workspace <workspace.json> \
  --output-dir <empty-or-absent-directory>
```

固定六列：

```text
镜号 | 场景 | 原剧本段落 | 镜头时长 | 运镜＋主画面描述 | 备注
```

XLSX 只有两张表。只有真实开放假设使用 `READY_WITH_ASSUMPTIONS`；第三列由 passage 派生，第五列由 shot model 投影。validation 最后写入；失败回滚 staging。

备注默认留空，只保存真实待确认项或有重新定向方式的连续性例外；不建立现场筹备管理机制。

读取 [output-contract.md](references/output-contract.md)。

## 机器与人工边界

机器阻断来源、Schema、对白、引用、Gate、shot_flow、Alignment、四文件同源性和确定性观看错误；来源缺口由 assumption obligation 持有，正式镜头只引用已批准且双向绑定的 inference。

题材机制、方法、镜头密度、长镜和审美仍由人工判断，不按统计值判艺术失败；机器可阻断缺失的观看决定、无理由的极端同质和跨单元理由模板坍缩。

内部检查使用 [storyboard_review.py](scripts/storyboard_review.py)、[source_alignment.py](scripts/source_alignment.py) 与 `director-workspace/3.1.3`。Schema 是唯一结构真相；手写校验器只负责来源、镜头流程与跨字段一致性。风险、安全或治理内容不进入创作流程和四文件。

评测入口见 [evals/output/cases.jsonl](evals/output/cases.jsonl)。

## 禁止事项

禁止生成图像、视频、图像／视频 Prompt、模型配置、下游 Cut 分组。禁止恢复默认 cut、默认 hold、镜头数量配额、强制正反打、固定三候选、镜长硬上限或摄影配额。禁止把 Gate、Alignment、哈希、内部 ID、风险治理、空值和后台分段直接写入 XLSX。
