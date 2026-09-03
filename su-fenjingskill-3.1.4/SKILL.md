---
name: su-fenjingskill
description: 将完整剧本、连续场景、锁定片段或概念材料拆解为具有视听逻辑的六列导演分镜和 director-shot-data/3.1.4。拆镜前先确认成片节奏、目标时长、画幅和对白速度，再逐句决定切、留或镜内重构，并用结构化时间块计算镜长；XLSX 是人类前端，其余三文件是同源 Agent 后端。
---

# 导演分镜 3.1.4

## 职责与权威

以导演、摄影师和剪辑师的联合视角，依次处理来源、Gate 0、场景机制、导演方法、观看与拓扑、摄影执行和固定交付。

正式／内部合同为 `director-shot-data/3.1.4`、`director-workspace/3.1.4`。JSON、Markdown、validation 是 Agent 后端；XLSX 是唯一人类前端，保留六列“导演分镜”和全剧摘要“导演设计”。

## 八层工作流

### 1. 来源事实

建立权威语言、scope、非空来源行、连续 passage、逐字对白、受保护事实、来源缺口和补充事实台账。非空行默认属于叙事；每个叙事 unit 由 required fact 持有，主体、结果、否定、因果、声音身份、世界规则和结局不得静默反转。

读取 [source-truth-audit.md](references/source-truth-audit.md)；中文或含中文来源同时读取 [chinese-context-language.md](references/chinese-context-language.md)。

### 2. Gate 0：成片格式与节奏

任何拆镜前确认 `format_brief`：四种成片节奏或 custom、目标时长、画幅、方向、中文对白速度区间／默认值／选值和覆盖倾向。非 custom 必须使用 [su-dialogue-pace/1.0](references/dialogue-pace-standard.md) 的固定区间；越界只能通过有具体表演理由的 pace override。Gate 0 未确认不得继续，格式变化使全部阶段失效。

### 3. 场景机制

逐场选择一个主机制和最多一个辅机制，明确受保护过程、因果和信息节拍。

读取 [scene-mechanisms.md](references/scene-mechanisms.md)。

### 4. 导演方法

把参考编译为可执行的时间、边界、视点、空间、表演、摄影和声画方法；不复制镜头。

未指定方法时最多给两个真正不同的方案；用户明确指定且无实质歧义时，可记录为 `user_specified`，不额外阻断。

读取 [director-method-contract.md](references/director-method-contract.md) 与 [director-method-index.md](references/director-method-index.md)。

### 5. 场级策略与 Gate 2

把“格式 × 机制 × 方法”解算为 `dialogue_edit_plan`、`camera_grammar` 和拓扑。每句对白逐字决定 `establish | cut | hold | reframe`；同一人留镜必须逐句有新的可见发展，否则触发 `MISSED_DIALOGUE_VIEW_CHANGE`。每个 unit 确认 owner、画内外主体、读取尺度、framing、camera response、frame axis 和画幅适配；边界只存 `trigger + editorial_gain`。

唯一失效矩阵：

| 变化 | Gate 0 | Gate 1 | Gate 2 | Alignment |
| --- | --- | --- | --- | --- |
| format brief | 失效 | 失效 | 失效 | 失效 |
| 来源或方法 | 保持 | 失效 | 失效 | 失效 |
| 场级策略、dialogue plan、viewing 或 topology | 保持 | 保持 | 失效 | 失效 |
| 正式摄影、表演、声剪、timing 或投影 | 保持 | 保持 | 保持 | 失效 |

执行层变化不得错误作废 Gate 2，但必须重新批准 Alignment。读取 [scene-strategy-gates.md](references/scene-strategy-gates.md)。

### 6. 镜头与剪辑

固定次序：整场 → 信息与完整过程 → 逐句观看机会 → owner/画内外主体 → 尺度、画框和 framing → 摄影机响应 → 比较 cut/hold/reframe → topology。无新观看收益不加切点，也不得用总的“倾听者留镜”掩盖多轮对白。细则见 [shot-edit-grammar.md](references/shot-edit-grammar.md)。

### 7. 摄影、表演、声音与时长执行

发言者与 owner 分开；`onscreen` 可见，`os` 在画外。非固定运动有完整路径。不机械正反打不等于不用单人，保护过程不等于始终同框，克制不等于全平视固定；无配额，同质或重复理由必须有具体依据。

`shot_flow` 是镜内顺序；每个 timing block 的 `pace_ref` 指向 BASE 或显式 override，再以 flow 范围区分 sequential/parallel，最终镜长等于全部时间块之和。XLSX 仍只投影摄影头和一个画面自然段。

正式景别拒绝“紧中景”；XLSX 不得重复投影机位、动作、焦点、环境或出口。

按需读取 [blocking-space-continuity.md](references/blocking-space-continuity.md)、[cinematography-language.md](references/cinematography-language.md)、[dialogue-performance-sound.md](references/dialogue-performance-sound.md) 与 [editing-rhythm-duration.md](references/editing-rhythm-duration.md)。

### 8. 固定交付

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

内部检查使用 [storyboard_review.py](scripts/storyboard_review.py)、[source_alignment.py](scripts/source_alignment.py) 与 `director-workspace/3.1.4`。Schema 是唯一结构真相；手写校验器只负责来源、格式、对白观看、镜头流程、时长与跨字段一致性。风险、安全或治理内容不进入创作流程和四文件。

评测入口见 [evals/output/cases.jsonl](evals/output/cases.jsonl)。

## 禁止事项

禁止生成图像、视频、图像／视频 Prompt、模型配置、下游 Cut 分组。禁止恢复默认 cut、默认 hold、镜头数量配额、强制正反打、固定切镜秒数、固定三候选、镜长硬上限或摄影配额。禁止把 Gate、Alignment、哈希、内部 ID、timing blocks、风险治理、空值和后台分段直接写入 XLSX。
