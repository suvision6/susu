---
name: su-fenjingskill
description: 将剧本、连续场景、锁定片段或概念材料拆解为六列导演分镜和 director-shot-data/3.1.6；也用于比较导演方法，处理喜剧、群像、长对白长镜与平行剪辑。拆镜前确认节奏、时长、画幅和对白速度，再逐句决定切、留或镜内重构，以时间块测量并用整秒交付镜长；XLSX 是人类前端，其余三文件是同源 Agent 后端。
---

# 导演分镜 3.1.6

## 职责与权威

联合导演、摄影与剪辑视角处理来源、Gate、拓扑、执行和交付。

正式／内部合同为 `director-shot-data/3.1.6`、`director-workspace/3.1.6`。JSON、Markdown、validation 是 Agent 后端；XLSX 是唯一人类前端，保留六列“导演分镜”和全剧摘要“导演设计”。

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

把参考编译为可执行方法，不复制镜头。

未指定方法时最多给两个真正不同的方案；用户明确指定且无实质歧义时，可记录为 `user_specified`，不额外阻断。

读取 [director-method-contract.md](references/director-method-contract.md) 与 [director-method-index.md](references/director-method-index.md)。

### 5. 场级策略与 Gate 2

把“格式 × 机制 × 方法”解算为 `dialogue_edit_plan`、`camera_grammar` 和拓扑。每句对白逐字决定 `establish | cut | hold | reframe`；同 unit 留镜须逐句有新可见发展并落到正式执行。ID、镜号、复述对白和固定尾句不构成差异。每个 unit 确认 owner、画内外主体、读取尺度、framing、camera response、frame axis 和画幅适配；边界只存 `trigger + editorial_gain`，编号变化不能伪造切点。

唯一失效矩阵：

| 变化 | Gate 0 | Gate 1 | Gate 2 | Alignment |
| --- | --- | --- | --- | --- |
| format brief | 失效 | 失效 | 失效 | 失效 |
| 来源或方法 | 保持 | 失效 | 失效 | 失效 |
| 场级策略、dialogue plan、viewing 或 topology | 保持 | 保持 | 失效 | 失效 |
| 正式摄影、表演、声剪、timing 或投影 | 保持 | 保持 | 保持 | 失效 |

执行层变化不得错误作废 Gate 2，但必须重新批准 Alignment。读取 [scene-strategy-gates.md](references/scene-strategy-gates.md)。

### 6. 镜头与剪辑

先整场再逐句决定观看、主体、尺度、画框、摄影机响应与 cut/hold/reframe，最后形成 topology。无新观看收益不切；多轮对白不得共用笼统留镜理由。细则见 [shot-edit-grammar.md](references/shot-edit-grammar.md)。

### 7. 摄影、表演、声音与时长执行

发言者与 owner 分开；`onscreen` 可见，`os` 在画外。非固定运动有完整路径。不机械正反打不等于不用单人，保护过程不等于始终同框，克制不等于全平视固定；无配额，同质或重复理由必须有具体依据。

`shot_flow` 记录镜内顺序；timing blocks 按 flow 范围区分 sequential/parallel。分量可保留小数，但合计与正式 `duration_seconds` 必须是大于等于 1 的整数；不能事后四舍五入。目标总时长只作事后核对。`hold_seconds` 仅属于独立静默、等待、凝视、停滞或余波块，不与对白、动作、运镜或反应同块。

1–2 秒超短镜须说明可观察起点、结束条件和短促功能；缺证据硬失败。单镜与连续段进入人工审阅，不设数量配额。细则见 [editing-rhythm-duration.md](references/editing-rhythm-duration.md)。

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

机器阻断来源、Schema、对白、引用、Gate、shot_flow、Alignment、四文件同源性、编号／套话逃逸、无证据留镜、无事件停留、非整秒镜长和无证据超短镜；来源缺口由 assumption obligation 持有，镜头只引用已批准且双向绑定的 inference。

题材机制、方法、镜头密度、长镜和审美仍由人工判断；机器暴露超短镜供审阅，并阻断缺失的观看决定、时长证据和理由模板坍缩。

内部检查使用 [storyboard_review.py](scripts/storyboard_review.py)、[source_alignment.py](scripts/source_alignment.py) 与 `director-workspace/3.1.6`。Schema 是唯一结构真相；手写校验器只负责来源、格式、对白观看、镜头流程、时长与跨字段一致性。风险、安全或治理内容不进入创作流程和四文件。

评测入口见 [evals/output/cases.jsonl](evals/output/cases.jsonl)。

## 禁止事项

禁止生成图像、视频、图像／视频 Prompt、模型配置、下游 Cut 分组。禁止恢复默认 cut、默认 hold、数量配额、强制正反打、固定切镜秒数、固定三候选、镜长硬上限或摄影配额。禁止把 Gate、Alignment、哈希、内部 ID、timing blocks、风险治理、空值和后台分段直接写入 XLSX。
