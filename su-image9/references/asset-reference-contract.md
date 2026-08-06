# 参考资产绑定合同

<!-- ref-version: 2.1.1 -->

## 状态

参考资产状态只有：

- `none`：当前批次没有参考资产。
- `bound`：每个资产都绑定到明确实体或 Panel。

禁止 `prompt_only`、`not_bound`、`partial` 等模糊状态。

用户提供了资产但无法绑定时返回 `F-ASSET`，不得忽略后继续。

## reference_bindings

每项固定包含：

```json
{
  "asset_id": "REF-001",
  "asset_sha256": "...",
  "binding_type": "character | prop | space | panel",
  "target_id": "角色名 | 道具名 | scene_id | PAGE-01/PANEL-1",
  "locked_attributes": ["identity", "shape", "ownership", "fixed_geometry"],
  "status": "bound"
}
```

资产文件变化后，旧绑定立即失效。

## 权威关系

剧情权威依次为：

1. 当前用户明确修改。
2. 已锁定 `shot_data.json`。
3. 未被前两项修改的参考资产属性。

参考资产可以约束：

- 角色身份轮廓、发型和服装剪影。
- 道具形状、归属和已知状态。
- 场景固定结构、门窗家具和道路关系。
- 已明确的车辆位置或机位关系。

参考资产不得改变：

- 源镜顺序和 camera tag。
- 动作阶段、情绪结果或现实层。
- 可见角色、画外角色或可见道具集合。
- Beat、事实 ID 或连续性迁移。
- 黑白石墨风格与无字画面合同。

## 冲突处理

身份或固定几何出现无法裁决的实质冲突时返回 `F-ASSET`。

纯色彩、光效、照片质感或精修风格差异不构成剧情冲突；这些属性直接舍弃。

可由 `shot_data` 明确裁决的差异不要求额外人工确认。

禁止因为参考图“更好看”而反向修改导演构图。
