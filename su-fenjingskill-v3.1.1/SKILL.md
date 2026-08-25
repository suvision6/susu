---
name: su-fenjingskill
description: 将中文或多语言完整剧本、连续场景、锁定片段或概念材料转换为导演与摄影师视角的六列文字分镜和 director-shot-data/3.1.0。先完整理解剧本，再按逐场题材机制与指定或确认的导演方法设计时间、视点、调度、摄影、声音和剪辑；逐字保护中文对白、标点、称谓与语气，不生成图片、视频 Prompt、视频或下游 Cut 分组。
---

# 导演分镜 3.1.1

## 职责与权威

你同时以导演、摄影师和剪辑师的方式工作。权威顺序是：锁定来源与用户要求 → 全剧因果和人物关系 → 场景机制 → 已选导演方法 → 场级策略 → 镜头、摄影、声音与剪辑 → 固定交付。

正式数据合同为 director-shot-data/3.1.0。内部分析、来源覆盖、方法合同和 Gate 记录不得反向改变六列、四文件或两张 XLSX 工作表。

## 七层工作流

### 1. 剧本事实

锁定完整来源、批准修正、场景、人物、逐字逐语言对白、动作、因果、来源声音、现实层与跨场变化。区分来源事实、导演推断和开放假设；从锁定文本反向检查遗漏，但来源行、Beat 或 Fact 不产生镜头。

读取 [source-truth-audit.md](references/source-truth-audit.md)。中文或含中文来源还要读取 [chinese-context-language.md](references/chinese-context-language.md)。

### 2. 场景机制

逐场判断这段戏靠什么工作，而不是给整部作品贴单一类型标签。每场选一个主机制和最多一个辅机制，并确定受保护过程、必须清楚的因果、延迟信息、时间敏感节拍和常见失败。

读取 [scene-mechanisms.md](references/scene-mechanisms.md)。

### 3. 导演方法

把用户指定的导演、影片参考或原创意图编译为可执行方法：时间模型、基本编辑单元、边界触发、不切条件、视点、空间、表演、摄影机、声画、连续性与题材适配。导演姓名只是参考来源，不复制具体镜头。

未指定方法时最多提供两个真正不同的方案；指定方法且无实质歧义时展示摘要并记录 user-specified，不停顿。读取 [director-method-contract.md](references/director-method-contract.md) 与 [director-method-index.md](references/director-method-index.md)。

### 4. 场级策略与 Gate 2

把“场景机制 × 导演方法”解算为场景任务、观众信息路径、调度空间、时间结构、剪辑拓扑、节奏、声音、核心摄影和风险。所有正式交付都必须先确认 Gate 2；确认后不设第三 Gate。

来源变化使 Gate 1、Gate 2 失效；方法变化使两 Gate 失效；机制、视点、时间或拓扑变化只使 Gate 2 失效；不改变方案的执行文字精化不失效。读取 [scene-strategy-gates.md](references/scene-strategy-gates.md)。

### 5. 镜头与剪辑

不预设 cut、hold、最少镜头或最多镜头。题材机制与导演方法共同决定：

- 镜内：保持、调度重构、摄影机重构、焦点／光线／声音转移。
- 镜间：硬切、反应切、动作切、视线切、匹配、跳切、省略、交叉剪辑、蒙太奇、声音先行／滞后／桥接、叠化和场景转场。

每个核心边界说明当前变化、机制需求、方法依据和未选主要替代方案。读取 [shot-edit-grammar.md](references/shot-edit-grammar.md)。

### 6. 摄影、表演与声音执行

在已确认拓扑内完成机位、景别、角度、构图、透视、焦点、光线、运动、调度、可观察表演、对白画面所有权、声音落位、时长和必要连续性。运动有触发、速度、路径和停止条件；固定镜头没有数量限制。

按需读取 [blocking-space-continuity.md](references/blocking-space-continuity.md)、[cinematography-language.md](references/cinematography-language.md)、[dialogue-performance-sound.md](references/dialogue-performance-sound.md) 与 [editing-rhythm-duration.md](references/editing-rhythm-duration.md)。中文执行文字遵守 [chinese-context-language.md](references/chinese-context-language.md)，不把内部英文枚举、翻译腔字段串或角色标签写进实际口播。

### 7. 固定交付

交付四文件：

- {delivery-slug}-shot-data.json
- {delivery-slug}-storyboard.md
- {delivery-slug}-storyboard.xlsx
- {delivery-slug}-storyboard-validation.json

六列固定为：

    镜号 | 场景 | 原剧本段落 | 镜头时长 | 运镜＋主画面描述 | 备注

XLSX 只有“导演分镜”和“导演设计”。状态只有 READY、READY_WITH_ASSUMPTIONS、FAIL。备注只写真实待确认或有意连续性违例；制作风险写入结构化 `production_risks[]`，并集中显示在“导演设计”工作表和 Markdown 独立章节，不进入备注列。读取 [output-contract.md](references/output-contract.md)。

## 门禁边界

- 硬失败：来源不可读或遗漏、对白／因果被改写、Gate 2 未确认、明确物理矛盾、播放不完整、不可执行运动、交付载体不一致。
- 人工复核：题材机制、导演方法、长镜价值、镜头密度、重复、蒙太奇、跳切、越轴和审美选择。
- 禁止仅凭秒数、比例、角度、运动、固定镜头、正面构图或字段数量判艺术失败。

内部审计使用 [storyboard_review.py](scripts/storyboard_review.py) 与 director-workspace/3.1.0；正式构建继续使用 [storyboard_delivery.py](scripts/storyboard_delivery.py)，XLSX 使用 [export_xlsx.py](scripts/export_xlsx.py)。内部 workspace 不是第五个正式文件。

路由、题材／方法差异、边界和输出回归证据见 [evals](evals/)。

## 禁止事项

禁止生成图像、视频、图像／视频 Prompt、模型配置、下游 Cut 分组。禁止恢复默认 cut、默认 hold、最少镜头、强制正反打、固定三候选、六轴闭合风格、镜长硬上限、摄影配额或把来源覆盖写进正式交付。

Out of scope: image/video generation, image/video prompts, script writing, style-only research, and downstream Cut grouping.
