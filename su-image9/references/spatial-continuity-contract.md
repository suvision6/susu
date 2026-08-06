# 分页、空间锚点与派生角度合同

<!-- ref-version: 2.1.1 -->

## 分页键

正式分页键为：

```text
(scene_id, reality_layer)
```

任一值变化立即结束当前页。

每页最多九个 source Panel。

不允许 cross-scene 或 cross-layer bridge。

现实层必须读取结构化字段或当前场景连续性台账，不使用关键词猜测。

## Panel 1

Panel 1 必须是本页第一个源镜头：

- `panel_kind=source`。
- `source_camera_tag` 等于源镜 camera tag。
- `drawn_camera_tag` 保留源镜构图。
- 不改宽、不换角度、不借后序镜头。

回忆、手术或其他现实层可以合法开页，只要它拥有完整结构化空间依据。

## spatial_anchor_panel

Page 必须显式保存 `spatial_anchor_panel`。

它指向本页第一个满足以下条件的 source Panel：

- 明确地面或承托面。
- 至少一个固定物或可靠空间边界。
- 摄影机侧和主要关系轴可判定。
- 不属于纯黑场或纯声音 transition。

它可以不是 Panel 1，但不得改变 source Panel 顺序。

全页没有合法锚点时返回 `F-PAGE-ANCHOR`。

## 派生角度

先为每个源镜头保留且仅保留一个 source Panel；输出顺序中，每个 derived Panel 必须紧邻自己的 source Panel。

derived Panel 紧邻来源 Panel，候选依次为：

1. 同轴更宽或更紧。
2. 同侧三分之四。
3. 同侧侧面。
4. 已知空间内高低机位。
5. 双人过肩。
6. 已登记可见道具插入。

过肩要求至少两名可见角色。

道具插入要求该道具存在于来源镜 `visible_props`。

派生角度不得跨轴，不得创造来源未证明的反面空间。

## 零事实增量

derived Panel 必须继承：

- scene、现实层、Beat 和事实 ID。
- 可见/画外角色与可见道具。
- 动作阶段、情绪结果和声音状态。
- 连续性状态哈希与距离阶段。

只允许变化：

- 机位角度。
- 景别。
- 构图重心。

`fact_delta` 必须为 `none`。

显示标签按来源镜生成：`C005-A`、`C005-B`。

无法组成九个互不重复的合法角度时返回 `F-SPARSE-COVERAGE`。

不得重复末镜或推测动作阶段。

## 轴线与距离

轴线来自 `continuity_logs` 与源镜机位逻辑。

角色位置或朝向只能依据 `continuity_updates` 更新。

出现 `【站位位移】` 时，派生格必须继承对应迁移阶段。

后序镜头定义靠近、停步或退后终点时，前序格必须保留终点前距离。

不得用关键词自动生成新的位置事实。
