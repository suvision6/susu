# Migration Guide｜3.0.0 → director-shot-data/3.1.0 + Skill 3.1.1

Skill 3.1.1 使用正式合同 `director-shot-data/3.1.0`。新交付必须写入 `contract_version=3.1.0` 与 `source_skill_version=3.1.1`；已有 3.0.0 文件保持历史只读，不会被静默改写或冒充新交付。

## 保持不变的交付结构

- `contract_name=director-shot-data` 与 `source_skill=su-fenjingskill`；
- 四个正式文件；
- “导演分镜”“导演设计”两张 XLSX 工作表；
- 六列主表和第五列自然执行文字；
- READY / READY_WITH_ASSUMPTIONS / FAIL；
- scenes、shots、dialogue playback、camera、staging、sound、edit 和 continuity 的正式结构。

## 3.1.0 正式身份与字段变化

- `contract_version=3.1.0`；
- `source_skill_version=3.1.1`；
- 镜头或场景可使用 `production_risks[]`；
- `notes` 默认空，只保留真实待确认或有意连续性违例；
- 制作风险在 Markdown 独立章节和 XLSX“导演设计”工作表展示，不进入备注列；
- 中文对白执行角色标签分离、全角标点保持、最低可播性和中文第五列检查。

## 新的内部工作区

新创作使用 director-workspace/3.1.0 保存：

- source units 与反向覆盖；
- director method contract；
- adaptive Gate 1；
- scene mechanisms；
- scene strategies 与 shot topology；
- review lock；
- mandatory Gate 2。

这些内容不迁入正式 shot data，也不增加公开工作表。

## 从 3.0.0 重新导演

1. 锁定原 3.0.0 source.locked_text 和 dialogue inventory。
2. 建立 source units，反向检查每个非空叙事单元。
3. 逐场识别 primary/secondary mechanism。
4. 选择或确认 director method；不得直接沿用“风格是偏置”的六轴。
5. 用机制与方法重新形成 scene strategy。
6. 重新判断镜内和镜间结构，不沿用“最少镜头”作为起点。
7. 将合同身份更新为 `director-shot-data/3.1.0`，把备注中的制作风险移入 `production_risks[]`。
8. 确认 Gate 2 后，先验证内部 workspace，再构建并复验正式四文件。

## 不应迁移

- “从最少镜头开始”或删除测试作为普遍生成规则；
- 只有 cut / hold / reframe 的单层编辑模型；
- 通用六轴作为导演方法身份；
- 来源行、Beat 或 Fact 与镜头一对一关系；
- 镜长、角度、固定镜、正面构图或运动比例作为艺术 FAIL；
- source coverage、Gate 或 review lock 进入正式 JSON/XLSX。

## 兼容、迁移与回滚

- 3.0.0 正式数据是历史合同；3.1.1 Skill 的后端会明确返回合同身份不匹配，不自动升级。
- 旧数据在没有 3.1.0 workspace 时只能视为既有交付，不获得“已完成新双 Gate”或“已迁移 3.1.0”的声明。
- 迁移必须从锁定来源和既有导演决定建立可审计副本，完成中文语境与备注分流检查后再生成新四文件。
- 回滚只需继续使用保存的 3.0.0 Skill 或正式文件；不要覆盖历史目录。
