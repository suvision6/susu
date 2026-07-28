# Cut Chain

本文件是一源镜一 Cut、Cut 标签、累计时间线和 Cut 映射校验的唯一规则源。

## 1. 核心不变量

```text
一个来源镜头 = 一个 Cut
Cut 顺序 = shots[] 来源顺序
Cut 数量 = source_shot_ids 数量
```

合镜只让多个 Cut 共处一个 Prompt 单元。不得把两镜揉成一个 Cut，不得把一镜拆成多个 Cut，也不得插入无来源 Cut。

## 2. 时间线

对时长完整的单元：

```text
cut[0].start = 0
cut[i].start = sum(source_duration[0:i])
cut[i].end = cut[i].start + source_duration[i]
unit.total_duration = sum(all source durations)
```

必须满足：

- 已知时长首 Cut 的机器起点和正文标签都从 `0S` 开始，不得写成“来源未提供-NS”。
- 前一 Cut 的 `end_seconds` 等于后一 Cut 的 `start_seconds`。
- 无间隙、重叠、负数或暗中并行。
- 最后一 Cut 的结束时间等于单元总时长。
- 每个 Cut 时长逐字值等于对应来源 `duration_seconds`。

缺时长的镜头只能形成单镜单元。该 Cut 的 start、end、duration 与单元总时长均保持 `null`，Prompt 写“时间未提供”，不得生成伪时间。

## 3. 标签

人类可读标签按单元内顺序生成：

```text
Cut 1、Cut 2、Cut 3、Cut 4、Cut 5
```

机器身份始终使用 `cut_index` 和 `source_shot_id`。标签不替代来源镜号。

## 4. Cut 结构

```json
{
  "cut_index": 1,
  "cut_label": "Cut 1",
  "source_shot_id": "SH001",
  "source_order": 1,
  "start_seconds": 0,
  "end_seconds": 4,
  "duration_seconds": 4,
  "source_shot_hash": "sha256",
  "compiler_provenance": {
    "camera_hash": "sha256",
    "blocking_hash": "sha256",
    "performance_hash": "sha256",
    "dialogue_hash": "sha256",
    "continuity_hash": "sha256",
    "rendered_shot_description_hash": "sha256"
  },
  "emotion_visualization": []
}
```

provenance hash 证明编译读取了哪个来源字段，但不复制和改写来源所有权。

## 5. 内容边界

每个 Cut 只能使用其 `source_shot_id` 对应镜头的：

- camera；
- rendered shot description；
- blocking；
- performance 与 visible behavior；
- dialogue；
- 按 scene_id 只读关联的 scene context；
- visible props 与 end state；
- 来源 lighting/style、audio 与 constraints；
- continuity、continuity updates 与来源转场；
- 合法登记的 emotion visualization。

不得把后镜对白提前、把前镜动作延后、跨 Cut 搬运表演，或为了语言流畅隐藏 Cut 边界。

## 6. 校验错误

| code | 条件 |
| --- | --- |
| `CUT_COUNT_MISMATCH` | Cut 数量与源镜数量不等 |
| `CUT_SOURCE_MISMATCH` | Cut ID 或顺序不一致 |
| `CUT_TIMELINE_INVALID` | 时间起点、累计值、间隙、重叠或终点错误 |
| `CUT_SOURCE_HASH_MISMATCH` | Cut provenance 与实际来源镜头不一致 |

错误限定到对应单元；不阻断其他有效单元的复验。
