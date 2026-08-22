# su-fenjingskill v3.0.0

导演＋摄影师视角的分镜 Skill。v3 将代码、Schema、校验和文件导出降级为后端，把核心认知重新放回：

```text
剧本意图 → 人物关系 → Blocking → 空间与视点 → 摄影策略
→ 镜头动机 → 剪辑与声音 → 节奏与时长 → 连续性与生产复核
```

## 与 v2.5.8 的关系

- `su-fenjingskill-v2.5.8` 保持不变。
- v3 使用独立目录、独立合同和独立构建脚本。
- 旧项目可继续使用 v2.5.8；新项目建议从 v3 开始。
- 迁移说明见 [MIGRATION.md](MIGRATION.md)。

## 核心变化

1. 不再强制 Gate 1／Gate 2、digest 或候选确认流程。
2. 不再把说话者、事件或尺度变化默认映射成切镜。
3. 先做导演读场、Blocking、空间、视点和场级摄影策略，再生成镜头。
4. 每个镜头必须有具体 `motivation`，字段齐全不能替代镜头动机。
5. 风格参考改为可执行的时间、摄影机、空间、光线、声音和剪辑选择；不强制名导演候选。
6. 信息缺失采用假设清单和优雅降级，不因小问题卡死。
7. 后端只检查来源、对白、结构和确定性执行矛盾；艺术选择进入人工导演复核。
8. 保留原六列生产表格与 JSON／Markdown／XLSX／validation 交付方向。

## 目录

```text
SKILL.md                         核心导演方法与执行入口
references/
  director-method.md             场景任务、视点与镜头动机
  blocking-space-continuity.md   人物调度、空间和连续性
  cinematography-language.md     景别、机位、透视、构图、光线
  editing-rhythm-duration.md     剪辑、镜头连接、节奏和时长
  dialogue-performance-sound.md  对白、表演、声音与画外空间
  style-language.md              风格参考的导演化编译
  graceful-degradation.md        假设、缺失信息与工具失败
  output-contract.md             数据与六列交付映射
schemas/
  director-shot-data.schema.json 轻量数据合同
templates/
  director-analysis.md           导演分析模板
  storyboard-six-column.md       六列表格模板
scripts/
  storyboard_delivery.py         校验、Markdown 和 validation 构建
  export_xlsx.py                 artifact_tool XLSX 导出
examples/
  kitchen-farewell-shot-data.json
  kitchen-farewell-storyboard.md
  kitchen-farewell-storyboard.xlsx
  kitchen-farewell-storyboard-validation.json
  unknown-room-awakening-shot-data.json
  unknown-room-awakening-storyboard.md
  unknown-room-awakening-storyboard.xlsx
  unknown-room-awakening-storyboard-validation.json
tests/
  test_storyboard_delivery.py
  DIRECTOR_EVALUATION.md
CHANGELOG.md
MIGRATION.md
REFACTOR_REPORT.md
PACKAGE_MANIFEST.json
CHECKSUMS.sha256
VERSION
```

## 使用方式

将 `SKILL.md` 作为 Skill 入口。正常导演拆镜不需要先运行脚本。

后端校验：

```bash
python scripts/storyboard_delivery.py validate \
  --input examples/kitchen-farewell-shot-data.json
```

生成 JSON 副本、Markdown 和 validation report：

```bash
python scripts/storyboard_delivery.py build \
  --input examples/kitchen-farewell-shot-data.json \
  --output-dir build
```

生成 XLSX：

```bash
python scripts/export_xlsx.py \
  --input examples/kitchen-farewell-shot-data.json \
  --output build/kitchen-farewell-storyboard.xlsx
```

`export_xlsx.py` 使用 ChatGPT 环境的 `artifact_tool`。环境没有该工具时应记录 WARN，JSON 和 Markdown 仍可使用。

运行机器回归测试：

```bash
python -m unittest discover -s tests -v
```

人工导演测试使用 [tests/DIRECTOR_EVALUATION.md](tests/DIRECTOR_EVALUATION.md)，重点检查镜头动机、Blocking、观看位置、摄影选择、声画关系和剪辑连接。

## 示例状态

- `kitchen-farewell-*`：完整剧本片段，后端状态 `READY`。
- `unknown-room-awakening-*`：只有梗概且声源／空间未锁定，仍完成分镜，状态 `READY_WITH_ASSUMPTIONS`。

Schema 只约束核心字段，允许项目扩展字段；扩展不得覆盖来源事实或改变核心字段语义。

## 交付状态

- `READY`：无确定性问题。
- `READY_WITH_ASSUMPTIONS`：存在开放假设、人工复核项或可选工具缺失。
- `FAIL`：数据不可读、来源为空、对白不完整／被改写，或存在关键引用和执行矛盾。

WARN 不阻断导演成果。
