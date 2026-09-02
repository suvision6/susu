# su-fenjingskill 3.1.3

导演、摄影师和剪辑师视角的文字分镜 Skill。正式合同为 `director-shot-data/3.1.3`，内部合同为 `director-workspace/3.1.3`。`camera-grammar-01` 在四文件前后端分离基础上补齐画面所有权、画内外主体、framing、摄影机响应和场级摄影语法。

## 核心保证

- 每个非空来源行先进入不可省略台账；疑似动作或对白不能靠改成 metadata/non-narrative 绕过覆盖。
- JSON Schema 是正式结构唯一真相，运行时首先执行 Draft 2020-12 Schema 校验。
- 第三列由权威 passage 确定性派生。
- 后端 `execution_text` 完整保存 camera/staging/sound/edit/continuity/motivation/duration；有序 `shot_flow` 登记镜内实际发生顺序。
- Gate 2 每个镜头单元先确认 viewing design；正式 viewpoint、framing 与 visibility 必须双向落实。
- 不机械正反打不等于不用单人镜头；保护完整过程不等于始终同框；摄影机克制不等于全平视、全固定。
- 不设摄影类别数量配额；极端同质必须有具体 uniformity intent，跨单元理由模板坍缩会被阻断。
- XLSX 第五列由 camera、shot_flow 与对白索引独立投影为 `【角度，景别，运镜】` 加一个连续 `【画面内容】`自然段。
- 执行锁覆盖摄影、剪辑、连续性、时长、动机、假设、备注、execution_text、shot_flow 及来源绑定。
- Gate 1、Gate 2、Alignment 使用唯一依赖矩阵，不再由文档和代码各自定义。
- 来源缺口通过 assumption obligation 保留，不能靠删除正式假设伪装成 READY。
- topology 必须与 scene、shot binding、passage 和 fact 双向一致。
- 正式四文件由 `build-all` 在 staging 目录一次生成、校验并原子提交；validation 最后写入。
- XLSX 统一使用 openpyxl，输出固定两张工作表；导演分镜保持六列，导演设计保持全剧摘要。
- 备注只保存真实待确认项或有意连续性例外。现场筹备管理不属于本合同，不设专门字段或导出区块。

## 固定交付

```text
{delivery-slug}-shot-data.json
{delivery-slug}-storyboard.md
{delivery-slug}-storyboard.xlsx
{delivery-slug}-storyboard-validation.json
```

```text
镜号 | 场景 | 原剧本段落 | 镜头时长 | 运镜＋主画面描述 | 备注
```

## 安装依赖

```bash
python -m pip install -r requirements.txt
```

## 审批与验证

查看状态或重新锁定：

```bash
python -m scripts.storyboard_review status \
  --workspace <workspace.json> \
  --shot-data <shot-data.json>

python -m scripts.storyboard_review lock \
  --workspace <workspace.json> \
  --shot-data <shot-data.json> \
  --output <new-locked-workspace.json>
```

明确状态转换：

```bash
python -m scripts.storyboard_review approve-gate1 \
  --workspace <workspace.json> --shot-data <shot-data.json> \
  --reviewer <name> --note <note> --output <new-workspace.json>

python -m scripts.storyboard_review confirm-gate2 \
  --workspace <workspace.json> --shot-data <shot-data.json> \
  --reviewer <name> --note <note> --output <new-workspace.json>

python -m scripts.storyboard_review approve-alignment \
  --workspace <workspace.json> --shot-data <shot-data.json> \
  --reviewer <name> --note <note> --output <new-workspace.json>
```

分类例外使用 `approve-classification`，不得直接编辑状态字段冒充审批。所有写入命令拒绝覆盖已有文件。

组合验证：

```bash
python -m scripts.storyboard_delivery validate \
  --input <shot-data.json> \
  --workspace <workspace.json>
```

`READY_WITH_ASSUMPTIONS` 只表示真实开放假设，默认退出码为 0；CI 可使用 `--fail-on-warn` 将该状态视为失败。

## 原子正式构建

```bash
python -m scripts.storyboard_delivery build-all \
  --input <shot-data.json> \
  --workspace <workspace.json> \
  --output-dir <empty-or-absent-directory>
```

`build` 保留为 `build-all` 的兼容别名。正式流程不再分成“先生成三文件、再单独补 XLSX”的两阶段事务。

## 结构诊断与迁移

```bash
python -m scripts.storyboard_delivery structure-validate --input <historical-or-draft.json>

python -m scripts.migrate_contract_3_1_0_to_3_1_2 \
  --shot-data <historical-3.1.0.json> \
  [--workspace <historical-workspace-3.1.0.json>] \
  --output-dir <new-empty-directory>

python -m scripts.migrate_contract_3_1_2_to_3_1_3 \
  --shot-data <historical-3.1.2.json> \
  --workspace <historical-workspace-3.1.2.json> \
  --output-dir <new-empty-directory>
```

迁移产物始终是 draft。3.1.2→3.1.3 不猜测 shot_flow 或新切点，Gate 1、Gate 2 与 Alignment 全部失效，必须重新确认后才能正式构建。

## 测试

```bash
python -m unittest discover -s tests -v
```

本包的 P0 回归覆盖：叙事行洗白、所有 present required 字段 mutation、完整执行锁、假设删除、错误 topology、XLSX 注入失败回滚、Gate 失效矩阵、推断审批、行中否定、实体 substring 错绑、审批哈希和模块化 CLI。
