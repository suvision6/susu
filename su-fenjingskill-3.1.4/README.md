# su-fenjingskill 3.1.4

导演、摄影师和剪辑师视角的文字分镜 Skill。正式合同为 `director-shot-data/3.1.4`，内部合同为 `director-workspace/3.1.4`。`projection-quality-02` 在 Gate 0、逐句对白观看、画幅执行和结构化时长基础上，补齐 XLSX 前端减冗与规范景别词表。

## 核心保证

- 每个非空来源行先进入不可省略台账；疑似动作或对白不能靠改成 metadata/non-narrative 绕过覆盖。
- JSON Schema 是正式结构唯一真相，运行时首先执行 Draft 2020-12 Schema 校验。
- 第三列由权威 passage 确定性派生。
- 后端 `execution_text` 完整保存 camera/staging/sound/edit/continuity/motivation/duration；有序 `shot_flow` 登记镜内实际发生顺序。
- Gate 2 每个镜头单元先确认 viewing design；正式 viewpoint、framing 与 visibility 必须双向落实。
- Gate 0 在拆镜前确认十分钟短剧、平台长剧集、3–20分钟短片、长片电影或 custom 节奏，并锁定目标时长、画幅、方向与对白速度。
- 非 custom 语速使用 `su-dialogue-pace/1.0` 固定区间：短剧 4.3–5.5、平台剧 3.3–4.3、短片 2.3–3.3、长片 2.7–3.7 字/秒；擅改区间会被阻断。
- 每镜 timing plan 必须引用 BASE 或明确 pace override；越界必须说明适用场景／角色／对白和具体表演原因。
- 每个来源对白必须在 `dialogue_edit_plan` 中恰好出现一次；没有新增可见发展的 O.S. 留镜会被阻断。
- `timing_plan` 无缝覆盖 shot_flow；并行块取最长，顺序块相加，最终镜长由时间块确定。
- 不机械正反打不等于不用单人镜头；保护完整过程不等于始终同框；摄影机克制不等于全平视、全固定。
- 不设摄影类别数量配额；极端同质必须有具体 uniformity intent，跨单元理由模板坍缩会被阻断。
- XLSX 第五列由 camera、shot_flow 与对白索引独立投影为 `【角度，景别，运镜】` 加一个连续 `【画面内容】`自然段。
- 第五列不设统一字数上限，但会阻断机位复述摄影头、构图复述动作、flow owner 换字段重复、模板焦点和同场重复普通环境／焦点／出口。
- 景别只使用规范中文词表；镜内变化用 `→`，非专业“紧中景”等词不能正式构建。
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
python -m scripts.storyboard_review confirm-gate0 \
  --workspace <workspace.json> --shot-data <shot-data.json> \
  --reviewer <name> --note <note> --output <new-workspace.json>

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

python -m scripts.migrate_contract_3_1_3_to_3_1_4 \
  --shot-data <historical-3.1.3.json> \
  --workspace <historical-workspace-3.1.3.json> \
  --output-dir <new-empty-directory>
```

迁移产物始终是 draft。3.1.3→3.1.4 不猜节奏、画幅、对白速度、遗漏切点或时长块，Gate 0、Gate 1、Gate 2 与 Alignment 全部失效，必须重新确认后才能正式构建。

## 测试

```bash
python -m unittest discover -s tests -v
```

本包的回归覆盖：来源与合同锁、Gate 0–2 失效矩阵、对白 edit-plan 完整性、漏切与合法留镜、画幅应用、结构化时长、XLSX 投影、迁移和原子构建。
