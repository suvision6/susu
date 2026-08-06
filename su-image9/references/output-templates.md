# 数据与交付合同

<!-- ref-version: 2.1.2 -->

## 固定成果

Prompt 包必须同时产生：

1. `分析与锁定.md`
2. `panel_plan.json`
3. `page-map.json`
4. `final_image_prompts.md`
5. `final_image_prompts.compiled.md`
6. `validation_report.json`

图像阶段增加：

- 单格生成目录 `PAGE-XX/PANEL-N.png` 与 `attempt_log.json`（由 `generate_panels.py` 产出）。
- 可选 `visual_qa_report.json`（由 `visual_qa.py` 产出）。
- 拼版后的原始无字九格 PNG、外围标注 PNG 与 `annotation_manifest.json`（由 `annotate_storyboard_pages.py` 产出）。

不支持 text-only，也不生成固定成果之外的打包文件。

## panel_plan.json

```json
{
  "skill": "su-image9",
  "version": "2.1.2",
  "schema_version": "2.1",
  "source": {
    "file_sha256": "",
    "content_hash": "",
    "skill_version": "上游 metadata.version 原值",
    "validation_status": "PASS | WARN_ACCEPTED",
    "warning_digest": ""
  },
  "canon": {
    "version": "2.1.2",
    "sha256": ""
  },
  "reference_bindings": [],
  "pages": [],
  "release_ready": true
}
```

Page 固定字段：

```json
{
  "page": "PAGE-01",
  "scene_id": "S01",
  "reality_layer": "现实",
  "page_mode": "single_scene_single_reality_layer",
  "spatial_anchor_panel": "PANEL-2",
  "source_shot_nos": [1, 2, 3],
  "completion_mode": "source_only | derived_angle",
  "panels": []
}
```

Panel 固定字段：

```json
{
  "panel": "PANEL-1",
  "panel_kind": "source | derived_angle",
  "source_shot": 5,
  "variant_suffix": null,
  "display_label": "C005",
  "source_camera_tag": "平视, 中景, 固定镜头",
  "drawn_camera_tag": "平视, 中景, 固定镜头",
  "beat_ids": ["B005"],
  "covered_fact_ids": ["B005-F01"],
  "visible_characters": ["角色"],
  "offscreen_characters": [],
  "visible_props": [],
  "continuity_state_hash": "sha256",
  "composition_task": "忠实来源构图任务",
  "distance_stage_lock": "none",
  "fact_delta": "source",
  "primary_focus": ["角色"],
  "must_show": ["角色"],
  "may_show": [],
  "must_not_show": [],
  "render_delta": "none",
  "story_delta": "none",
  "camera_rationale": "源镜头，保留导演原始构图与可见集合。"
}
```

2.1.2 新增字段语义：

- `primary_focus`：本格视觉焦点实体列表。
- `must_show`：必须完整或清晰可辨的实体。
- `may_show`：可因构图需要局部出现或省略的实体。
- `must_not_show`：明确不能入画的实体。
- `render_delta`：`allowed` 表示允许因特写/遮挡/前景裁切改变可见集合；`none` 表示必须保留 source 的可见集合。
- `story_delta`：固定为 `none`，表示不增加、删除、改写剧情事实。
- `camera_rationale`：中文，解释为什么选这个角度。

source Panel：

- `variant_suffix=null`。
- `fact_delta=source`。
- `render_delta=none`。
- `must_show` 必须等于 `visible_characters + visible_props`。
- `must_not_show` 通常等于 `offscreen_characters`。

derived Panel：

- `variant_suffix=A | B | ...`。
- `display_label=C005-A`。
- `fact_delta=none`。
- `story_delta=none`。
- `render_delta=allowed`（允许裁切）或 `none`（必须保留源可见集合）。
- `visible_characters` / `visible_props` 必须是 source panel 对应集合的子集。
- `must_show` 必须是 source 可见集合的子集，且必须出现在 derived 可见集合中。
## page-map.json

page-map 只能从 panel_plan 派生，不重新计算标签：

```json
{
  "skill": "su-image9",
  "version": "2.1.2",
  "schema_version": "2.1",
  "source_file_sha256": "",
  "pages": [
    {
      "page_no": 1,
      "page": "PAGE-01",
      "source": "PAGE-01.png",
      "header": "场景｜镜头001-005",
      "panels": [
        {
          "panel_no": 1,
          "panel": "PANEL-1",
          "source_shot": 5,
          "variant_suffix": "A",
          "display_label": "C005-A"
        }
      ]
    }
  ],
  "release_ready": true
}
```

标注器只接受 `release_ready=true` 且 `source_file_sha256` 与当前 `shot_data.json` 原始文件字节一致的 page-map。

## Prompt 层顺序

固定顺序：

```text
DELIVERABLE
SYSTEM_STYLE_LAYER
SOURCE_BINDING_LAYER
SCENE_LAYER
CAMERA_RULE_LAYER
CONTINUITY_LAYER
PAGE_SPATIAL_ANCHOR
FIXED_GEOMETRY_LOCK
VEHICLE_AND_AXIS_LOCKS
OBJECT_VISIBILITY_AND_BOUNDARIES
PANEL_LAYER
NEGATIVE_CONSTRAINTS
```

四个 `@CANON(NAME)` 只能引用 `canon-locks.md` 的白名单块。

## CLI

```text
derive_su_image9_prompt_package.py --shot-data <json> --out-dir <dir> [--canon <md>]
validate_su_image9_prompt.py --canon <md> --panel-plan <json> --final-prompts <md> --shot-data <json> --report <json> --out <compiled.md>
annotate_storyboard_pages.py --data <json> --page-map <json> --pages <dir> --output <dir> [--font-path <font>] [--mode auto|per-panel]
generate_panels.py --panel-plan <json> --out-dir <dir> [--max-retries <n>]
visual_qa.py --panel-plan <json> --pages-dir <dir> --report <json>
semantic_audit.py <shot_data.json>
```

derive 不提供 `--mode text-only` 或 `--page-size`。

标注器只输出标注 PNG 与 `annotation_manifest.json`；`--mode per-panel` 会先读取 `PAGE-XX/PANEL-N.png` 并确定性拼成 3x3。

generate_panels 默认使用 stub 后端；真实模型接入为后续任务。

## annotation_manifest.json

manifest 必须记录：

- `status` 与 `code`。
- 实际中文字体路径。
- 每页源文件与输出路径。
- 源文件 SHA-256、尺寸和输出中的原像素区域。
- `detected_image_grid | canonical_fallback`。
- fallback warning。
- 每格 `display_label`。
