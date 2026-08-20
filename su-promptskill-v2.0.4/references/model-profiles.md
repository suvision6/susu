# Model Profile

本文件是运行时模型能力与硬限制的唯一规则源。Profile 只约束适配与提交条件，不改变来源事实或合镜语义。

## 默认 Profile

`seedance-2.5-default`：

- `model_id`: `doubao-seedance-2-5-260628`
- `prompt_adapter_id`: `seedance-2.5-structured-zh-v1`
- `reference_tag_convention`: `preserve-explicit-v1`
- 每 Prompt 单元最多 30 秒、10 Cut
- 单个源镜没有额外 15 秒合镜门槛；多 Cut 单元只受 30 秒、10 Cut 与语义边界约束
- 图片最多 30 张；宽高比 0.4–2.5，宽高各 300–6000 px，总像素
  409600–8295044
- 视频最多 10 段，总时长最多 30 秒
- 音频最多 10 段，总时长最多 30 秒
- 图片、视频、音频合计最多 50 份
- 参考视频和音频单段 2–30 秒；输出只支持 480p、720p

请求超限时保留必要素材与最佳 Prompt，写入 `prompt_advisories`，并设置
`submission_ready=false`；不得把参数说明写进 Prompt。

## 兼容 Profile

`seedance-2.0-default` 保留原行为：最多 15 秒、5 Cut，使用
`seedance-2.0-structured-zh-v1` 与旧标签约束。它必须显式选择，不能成为新构建默认值。

`generic-video` 提供模型中立的 15 秒、5 Cut 适配。自定义 Profile 必须完整声明合同字段并通过脚本校验。

## 请求配置

`request_configuration` 保存用户原始参数快照与规范化结果，至少检查：

- `model_id` 是否与 Profile 一致；
- `ratio` 是否为受支持的宽高比表达；
- `duration` 是否为正数且不超出 Profile 上限；
- `output_format` 是否为已声明的输出格式。
- `resolution` 是否为 `480p | 720p`，`generate_audio` 是否为布尔值。

视频编辑必须 `ratio=adaptive` 且 `duration=-1`；视频延长与严格首帧／首尾帧
必须 `ratio=adaptive`，`duration` 可为 `4–30` 或 `-1`。编辑与延长使用 mov
是官方建议而非硬限制，只产生非阻断 advisory。

该对象不是 API 调用器。API 目标时长只约束请求，不能生成 Prompt 时间戳或“总时长”行。

## 稳定性边界

- 官方教程/API 决定硬参数。
- 官方 Prompt 指南决定模型表达能力。
- `sd25-pe` 只提供优化流程，不作为运行时依赖。
- 编辑阈值 `0.3/0.4 秒`的证据差异不进入编译规则；未来做结果验证时可把 0.4 秒作为兼容阈值。
