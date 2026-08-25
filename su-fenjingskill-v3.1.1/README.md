# su-fenjingskill 3.1.1

导演、摄影师和剪辑师视角的文字分镜 Skill。3.1.1 使用 director-shot-data/3.1.0 正式合同、固定四文件、两张 XLSX 工作表和六列导演分镜；`source_skill_version=3.1.1`，并对中文来源、对白、执行文字、时长与表格交付进行原生优化。

## 核心变化

3.0.0 移除了默认切镜，却仍从“最少镜头”开始。3.1.0 同时取消默认 cut、默认 hold 和最少／最多镜头：

    剧本事实
      -> 场景机制
      -> 导演方法
      -> 场级策略
      -> 镜头与剪辑
      -> 摄影／表演／声音执行
      -> 固定交付

- 场景逐场识别喜剧、动作、悬疑、关系、威胁、群像、仪式、蒙太奇、主观记忆或奇观机制。
- 十五张导演卡改为可执行方法合同，真实拥有时间、边界、视点、空间、表演和声画规则。
- 镜头内部与镜头之间采用两层编辑语法，支持跳切、省略、交叉剪辑、蒙太奇和声音主导关系。
- 自适应 Gate 1：用户明确指定方法时可跳过停顿式确认。
- Gate 2 对所有正式交付强制确认场级策略与剪辑拓扑。
- director-workspace/3.1.0 在内部反向检查来源与 Gate，不进入正式交付。
- 长镜、短镜、固定镜、正面构图、高密度剪辑和越轴不因统计特征自动失败。
- 中文角色标签、括号表演说明与实际口播分离；全角标点、称谓、语气词和对白顺序逐字保护。
- 中文对白执行宽松的最低可播性检查，明显塞不进镜长时硬失败，但字符率不作为艺术节奏目标。
- 制作风险写入 `production_risks[]`，在 Markdown 独立章节和 XLSX“导演设计”工作表集中显示，不进入备注列。

## 正式交付

正式合同是 director-shot-data/3.1.0：

- {delivery-slug}-shot-data.json
- {delivery-slug}-storyboard.md
- {delivery-slug}-storyboard.xlsx
- {delivery-slug}-storyboard-validation.json

XLSX 只有“导演分镜”和“导演设计”。主表固定：

    镜号 | 场景 | 原剧本段落 | 镜头时长 | 运镜＋主画面描述 | 备注

内部来源单元、导演方法和 review lock 不得增加正式文件或工作表。六列“备注”默认空，只保存真实待确认或有意连续性违例；制作风险使用正式 `production_risks[]` 扩展字段，并在第二张工作表集中呈现。

## 使用顺序

1. 按 SKILL.md 完成剧本事实、场景机制和导演方法。
2. 使用 templates/director-analysis.md 展示 Gate 2。
3. 将内部工作区锁定并验证：

       python scripts/storyboard_review.py lock +         --workspace <workspace.json> +         --output <locked-workspace.json>

       python scripts/storyboard_review.py validate +         --workspace <locked-workspace.json> +         --shot-data <shot-data.json>

4. 构建正式后端文件：

       python scripts/storyboard_delivery.py build +         --input <shot-data.json> +         --output-dir <delivery-dir>

5. 导出正式 XLSX：

       python scripts/export_xlsx.py +         --input <shot-data.json> +         --output <delivery-dir>/<slug>-storyboard.xlsx

## 目录

- SKILL.md：七层工作流、Gate 和正式交付入口。
- references/source-truth-audit.md：锁源与反向覆盖。
- references/chinese-context-language.md：中文对白、标点、可播性、执行文字与备注分流。
- references/scene-mechanisms.md：逐场题材机制。
- references/director-method-contract.md：导演方法和 Gate 1。
- references/director-method-index.md、references/director-methods/：十五种方法。
- references/scene-strategy-gates.md：场级策略、Gate 2 和失效规则。
- references/shot-edit-grammar.md：镜内与镜间编辑语法。
- scripts/storyboard_review.py：内部来源、方法和 Gate 审计。
- scripts/storyboard_delivery.py：正式 3.1.0 JSON/Markdown/validation 构建。
- scripts/export_xlsx.py：固定两工作表 XLSX。

## 验证

    python -m unittest discover -s tests -v

人工创作评测见 tests/DIRECTOR_EVALUATION.md。Yao Meta 证据位于 evals/ 和 reports/；recorded fixtures、命令执行、模型执行与人类盲评必须分别标记，不得互相冒充。

## 边界

本 Skill 不生成分镜图、图像、视频 Prompt、视频、模型配置或下游 Cut 分组。导演姓名只用于编译方法，不用于复刻具体镜头。
