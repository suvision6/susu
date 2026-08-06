---
name: su-image9
description: 从任意已锁定版本的 su-fenjingskill-zh shot_data.json 派生 Image2 3x3 黑白石墨电影分镜提示词、九格原图与外围标注 PNG。以 panel_plan.json 为唯一机器事实源，严格保持源镜顺序、原构图、场景、现实层、人物、道具和连续性；不修改导演主表。
---

# su-image9

## 版本

`2.1.2`
<!-- skill-version: 2.1.2 -->

这是独立的九宫格黑白石墨分镜生产技能。
它读取导演主流程已经锁定的结构化镜头数据。
它不拆剧本、不改镜头、不回写主表，但在 2.1.2 中会在发现上游语义冲突时生成报告供人确认。

2.1.2 相对 2.1.1 的主要升级：

- **中文语义优化预检**：在派生前只读 `shot_data.json`，检测动作执行者不一致、空间起点/终点相同、单镜阶段超载、非现实层缺少视觉线索、`insert_priority` 与事实不匹配、互相矛盾的方位词等；发现冲突时返回 `F-SEMANTIC-CONFLICT`，不自动修改上游。
- **叙事驱动的派生角度**：候选池不再按固定八种轮转，而是根据 shot 覆盖的 dialogue/action/prop 事实、现实层标签和可见角色数量动态选择（说者近景、听者反应、动作起点/过程/终点、过肩、道具插入、主观提示等）。
- **受控的渲染差异（render_delta）**：derived panel 可以在 `story_delta=none` 的前提下因构图裁切减少可见人物/道具；`render_delta=allowed` 表示允许这种裁切，`none` 表示必须保留源镜可见集合。source panel 固定为 `render_delta=none`。
- **图像生产骨架**：新增 `generate_panels.py`（默认 stub 后端，输出占位 PNG）与 `visual_qa.py`（机器几何/灰度检查 + 人工复核清单）。真实模型接入作为后续任务，不在 2.1.2 范围内。

## 何时触发

以下任务使用本 Skill：

- 从合规 `shot_data.json` 生成 3x3 九格提示词包。
- 为 Image2 / gpt-image-2 准备黑白石墨分镜页。
- 生成或复核 `panel_plan.json` 与 `page-map.json`。
- 对无字九格 PNG 添加外围页眉和格号图例。
- 检查九格页是否忠实继承源镜事实与连续性。
- 运行中文语义审计并报告上游不可画冲突（2.1.2）。
- 从单格 PNG 确定性拼版并标注（2.1.2）。

以下任务不使用本 Skill：

- 剧本拆 Beat、拆镜或修改导演镜头设计。
- 修改 `su-fenjingskill-zh` 主表、Prompt、关键帧或 Excel。
- 彩色概念图、写实剧照、漫画页或其他视觉风格。
- text-only 交付。
- 真实图像模型调用（2.1.2 仅完成骨架，模型接入为后续任务）。

非黑白石墨请求直接报告超出技能范围。
不要进入“确认后改风格”的分支。

## 权威优先级

冲突时依次执行：

1. 用户当前明确指令，但不得改写已锁定剧情事实。
2. `shot_data.json` 的源镜、Beat、事实和连续性。
3. `panel_plan.json` 的当前批次机器事实。
4. `references/canon-locks.md` 的视觉与几何锁。
5. 已绑定参考资产中未被用户修改的身份或几何信息。

`panel_plan.json` 是本 Skill 唯一机器事实源。
Prompt、page-map、分析摘要和标注 manifest 都从它派生。
禁止分别手改多个交付物以追求表面一致。

## 输入门禁

正式入口接受任意上游版本，但不接受缺少必要门禁或结构损坏的物料：

- `metadata.skill_name == "su-fenjingskill-zh"`。
- `metadata.version` 与 `metadata.rule_revision` 必须为非空字符串；不与任何固定上游版本比较，并原样写入 `panel_plan.source` 与分析记录。
- `script_lock.status == "locked"`。
- 上游 Gate A、Gate B、Gate C 均已有 `approved` 记录，其中 Gate C 是进入图像阶段的最终签发。
- 上游 `validation_report.status` 为 `PASS`。
- `validation_report.source_json_hash` 按已支持的上游哈希合同与当前源文件一致。

上游 `WARN` 必须逐条存在 `warn_resolutions`。
非白名单 WARN 只能由 `human` 处置。
处置摘要写入 `panel_plan.source.warning_digest`。
源文件或 WARN 集合变化后，旧批准立即失效。

`FAIL`、`NOT_RUN`、缺 Gate、缺哈希、缺处置、缺版本字符串或缺规则修订字符串均停止。

源锁哈希与内容哈希必须匹配 su-image9 已实现的上游哈希合同；版本号本身不构成拒绝理由，哈希合同不明时应报告 `F-SOURCE-HASH` 并停止，禁止人工绕过。

语义审计在输入门禁之后、分页与派生之前运行。语义冲突不阻塞输入合同，但会在产物中生成 `F-SEMANTIC-CONFLICT` 审查项；人在上游确认前不进入 release-ready 状态。

不提供 SC 自查替代正式机器门禁。

## 正式流程

### 1. 锁定来源

读取 `shot_data.json`，记录：

- 文件 SHA-256。
- 规范化内容哈希。
- 上游 Skill 版本。
- 上游校验状态。
- WARN 摘要。

任何后续产物必须引用同一来源摘要。

### 2. 绑定参考资产

参考资产状态只有：

- `none`：未提供参考资产。
- `bound`：已绑定到明确角色、道具、空间或 Panel。

提供了参考图却无法明确绑定时，返回 `F-ASSET`。
资产只约束身份、形状、归属和固定几何。
资产不得覆盖源镜动作、人物可见性、现实层或导演构图。

详见 `references/asset-reference-contract.md`。

### 3. 严格分页

一页只允许：

- 一个 `scene_id`。
- 一个 `reality_layer`。
- 最多九个源镜头。

场景或现实层变化必须换页。
不支持 cross-scene bridge。
不支持 cross-layer bridge。

黑场或纯声音 transition 只能结束已有页面。

它不能成为派生角度的来源。

无法合法归属时返回 `F-PAGE-ANCHOR`。

### 4. 保留源镜

每个源镜头先生成一个 `panel_kind=source` 的格子。

Panel 1 永远对应本页第一个源镜头。
Panel 1 保留该源镜原始 camera tag 和导演构图。
禁止为了建立空间而自动改宽、换角度或借用后序镜头。

页面另设 `spatial_anchor_panel`。
它指向第一个具有可靠空间依据的 source Panel。
该 Panel 可以不是 Panel 1。

空间锚点判定只依赖结构化空间信息。

不得用“回忆、手术、黑场”等关键词代替结构判断。

### 5. 中文语义审计（2.1.2）

在分页与派生前，只读 `shot_data.json`，检查以下冲突：

- `continuity_updates` 中 `position` 的 `from` 与 `to` 相同。
- `source_paragraph` 主语与 `continuity_updates` 实体不一致。
- 单镜覆盖多个 Beat，但动作/对白时长不足以支撑。
- `insert_priority=must_have` 时未覆盖 prop fact 或 `visible_props` 为空。
- 非现实层缺少可视化线索（主观、回忆、留白、虚化等）。
- `camera_main_image` 中同时出现互相矛盾的方位词。

审计只报告、不修改。所有冲突写入 `分析与锁定.md` 的“语义风险”章节；存在冲突时产物状态为 `REVIEW_REQUIRED`，失败码 `F-SEMANTIC-CONFLICT`。

### 6. 补足九格

不足九格时只可生成 `panel_kind=derived_angle`。

派生格必须紧邻其 source Panel。

镜号序列必须非递减。

候选角度按 shot 的叙事功能动态选择，不再固定轮转：

| 触发条件 | 优先候选 |
|---|---|
| 覆盖 dialogue fact 或 `shot_type=dialogue` | 说者近景、听者反应、过肩（说→听）、过肩（听→说） |
| 覆盖 action/position fact 或 `shot_type=action` | 动作起点、动作过程、动作终点、同侧跟随 |
| 有 prop fact 且 `visible_props` 非空 | 道具状态特写、持手特写、道具与人物关系 |
| 双人可见 | 过肩、双人关系、单人反应 |
| 单人可见 | 更紧/更松、高/低机位、主观提示（现实层允许时） |
| `reality_layer != 现实` | 主观、留白、边缘弱化等受控视觉提示 |

过肩只用于至少两名可见角色。

道具插入只用于已登记的可见道具且有覆盖的 prop fact。

每个派生格携带中文 `camera_rationale`，解释为何选择该角度。

派生格只能改变机位角度、景别和构图重心；`story_delta` 固定为 `none`。

渲染可见集合可以收缩：`render_delta=allowed` 时 derived panel 的 `visible_characters` / `visible_props` 可以是 source panel 可见集合的子集；`must_show` 中的实体必须仍出现在 derived 可见集合中；`must_not_show` 中的实体不得出现。source panel 的 `render_delta` 固定为 `none`，`must_show` 必须等于 `visible_characters + visible_props`。

以下内容必须与来源格完全相同：

- `scene_id` 与 `reality_layer`。
- Beat 与事实 ID。
- 画外角色。
- 动作阶段与情绪结果。
- 连续性状态哈希。

派生格 `fact_delta` 必须为 `none`。
显示标签使用 `C005-A`、`C005-B`。
机器来源仍保存 `source_shot: 5`。

无法获得足够合法角度时返回 `F-SPARSE-COVERAGE`。

不得重复末镜、补写动作或虚构剧情来凑满九格。

分页与派生细节见 `references/spatial-continuity-contract.md`。

### 7. 建立 panel_plan

顶层必须包含：

- `skill`、`version`、`schema_version`。
- `source`、`canon`、`reference_bindings`。
- `pages` 与 `release_ready`。

Page 必须包含：

- `page`、`scene_id`、`reality_layer`。
- `page_mode`、`spatial_anchor_panel`。
- `source_shot_nos`、`completion_mode`、`panels`。

Panel 必须包含：

- `panel`、`panel_kind`、`source_shot`。
- `variant_suffix`、`display_label`。
- `source_camera_tag`、`drawn_camera_tag`。
- `beat_ids`、`covered_fact_ids`。
- `visible_characters`、`offscreen_characters`、`visible_props`。
- `continuity_state_hash`、`composition_task`。
- `distance_stage_lock`、`fact_delta`。
- `primary_focus`、`must_show`、`may_show`、`must_not_show`（2.1.2）。
- `render_delta`、`story_delta`、`camera_rationale`（2.1.2）。

source Panel 使用：

- `variant_suffix: null`。
- `fact_delta: source`。
- `render_delta: none`。
- `must_show` 等于 `visible_characters + visible_props`。

derived Panel 使用：

- 非空 `variant_suffix`。
- `fact_delta: none`。
- `story_delta: none`。
- `render_delta: allowed` 或 `none`。
- `must_show` 为 source 可见集合的子集且必须出现在 derived 可见集合中。

完整结构见 `references/output-templates.md`。

### 7. 渲染 Prompt

最终层顺序固定为：

1. `DELIVERABLE`
2. `SYSTEM_STYLE_LAYER`
3. `SOURCE_BINDING_LAYER`
4. `SCENE_LAYER`
5. `CAMERA_RULE_LAYER`
6. `CONTINUITY_LAYER`
7. `PAGE_SPATIAL_ANCHOR`
8. `FIXED_GEOMETRY_LOCK`
9. `VEHICLE_AND_AXIS_LOCKS`
10. `OBJECT_VISIBILITY_AND_BOUNDARIES`
11. `PANEL_LAYER`
12. `NEGATIVE_CONSTRAINTS`

四个固定锁只从 `references/canon-locks.md` 编译。
PANEL 文本由 `panel_plan.json` 确定性渲染。
validator 必须从同一源数据重建并逐格比较。

任意手改或新增剧情事实均失败。

画内禁止文字、格号、字幕、水印和箭头。

### 9. 校验与授权

退出码固定：

- `0`：PASS。
- `1`：REVIEW_REQUIRED。
- `2`：CONTRACT_FAIL。
- `3`：TOOL_ERROR。

只有 `0` 可以对应 `release_ready=true`。

自然语言中的明确同意、修改或终止均有效。

用户已明确授权生图时，不重复要求固定字面回复。

单页最多重试两次。

重试耗尽后报告具体失败项和最后产物。

不得自行接受缺陷。

### 10. 图像生产骨架（2.1.2）

`generate_panels.py` 读取 `panel_plan.json` 与 `final_image_prompts.compiled.md`，为每页每格生成单张 16:9 PNG。v2.1.2 默认使用 stub 后端输出占位灰度图；真实模型接入为后续任务。

```text
python scripts/generate_panels.py --panel-plan <json> --out-dir <dir> [--max-retries 2]
```

输出结构：

```text
<out-dir>/
  PAGE-01/
    PANEL-1.png
    ...
    attempt_log.json
```

`visual_qa.py` 对生成结果做机器检查并生成人工复核清单：

```text
python scripts/visual_qa.py --panel-plan <json> --pages-dir <dir> --report <json>
```

机器检查项包括文件存在、可解码、16:9 比例、灰度。语义与连续性检查以 `review_checklist` 形式交给人复核，不自动判定。

`annotate_storyboard_pages.py` 支持两种输入模式：

- `auto`：--pages 指向完整 3x3 PNG。
- `per-panel`：--pages 指向 `generate_panels.py` 输出目录，脚本先确定性拼版再加外围标签。

验证合同见 `references/validation-checklists.md`。

## 固定交付

Prompt 包固定包含六项：

1. `分析与锁定.md`
2. `panel_plan.json`
3. `page-map.json`
4. `final_image_prompts.md`
5. `final_image_prompts.compiled.md`
6. `validation_report.json`

正式图像阶段增加：

- 原始无字九格 PNG（可由单格 PNG 拼版）。
- 外围标注 PNG。
- `annotation_manifest.json`。
- 单格生成目录 `PAGE-XX/PANEL-N.png` 与 `attempt_log.json`（2.1.2）。
- 可选 `visual_qa_report.json`（2.1.2）。

不生成 text-only 或固定成果之外的打包文件。

## PNG 外围标注

调用：

```text
python scripts/annotate_storyboard_pages.py --data <shot_data.json> --page-map <page-map.json> --pages <pages_dir> --output <output_dir> [--font-path <font>]
```

标签只读取 `page-map.json` 的 `display_label`；标注前必须核对 page-map 为 2.1、`release_ready=true`，且其 source file SHA-256 与当前 `shot_data.json` 文件一致。

优先检测真实 3x3 边框。

检测失败时使用 canonical boxes，并在 manifest 写 warning。

无可靠中文字体时返回 TOOL_ERROR。

原始九格作为完整像素块一次性粘贴。

只允许在画布顶部和底部外围增加标签区。

禁止缩放、裁切、覆盖或在宫格行间插入标签带。

## Reference 路由

- 固定锁文本：`references/canon-locks.md`
- 分页、锚点和连续性：`references/spatial-continuity-contract.md`
- 参考资产绑定：`references/asset-reference-contract.md`
- Schema、交付和 CLI：`references/output-templates.md`
- 状态、失败和验收：`references/validation-checklists.md`
- 中文语义审计规则：本文件“中文语义审计”章节与 `scripts/semantic_audit.py`

只读取当前步骤需要的 reference。

禁止把 reference 全文重新复制回本文件。

## 不可变边界

- 不修改 `su-fenjingskill-zh`。
- 不回写导演主表。
- 不让摄影术语反向改变源镜事实。
- 不让参考图改变剧情。
- 不让 derived Panel 产生事实增量。
- 不让 Prompt 成为新的机器事实源。
- 不以人工确认放行结构错误或事实篡改。
- 不在依赖缺失时伪装成正式可发布结果。
