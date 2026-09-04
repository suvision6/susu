# Graceful Degradation｜草案继续与正式构建边界

本文件处理信息缺失、歧义、格式问题和工具失败。核心原则是：创作草案可以继续，正式交付必须 fail-closed。

## 1. 两种状态不可混用

### 内部草案

workspace 与 shot-data 可以保持 `draft`、Gate invalidated 或 Alignment pending，用于继续导演判断。草案不得标记为正式 `READY`，也不得使用正式四文件命名冒充已交付结果。

### 正式构建

正式 `build-all` 必须通过 Schema、来源、Gate、Alignment 和跨载体校验。任何失败都回滚 staging，不生成部分 JSON、Markdown、XLSX 或提前写出的 READY validation。

## 2. 假设清单

必要时建立：

```json
{
  "assumption_id": "A001",
  "scope": "scene",
  "statement": "暂定门位于房间南侧，便于保持人物进出方向。",
  "reason": "来源只写人物从门外进入，未提供平面位置。",
  "impact": "只影响机位与银幕方向，不改变剧情事实。",
  "status": "open"
}
```

每个 assumption 必须由 workspace 中的 source gap obligation 持有。规则：

- 只记录会影响镜头、声音、连续性或交付的未确认项；
- 只使用可逆且不制造新剧情事实的选择；
- 不得假设新人物动机、台词、伤势、道具结果、关系或现实层；
- 用户修正后更新状态，但不追溯性声称旧方案来自剧本；
- 有开放假设时状态是 `READY_WITH_ASSUMPTIONS`，默认 CLI 退出码仍为 0；需要严格 CI 时使用 `--fail-on-warn`。

## 3. 常见缺失信息

- 缺场号／镜号：生成稳定 `SC001`、`SH001`，不中断草案。
- 缺 slug：使用稳定 ASCII 临时值，记录为待确认。
- 空间不完整：建立最小拓扑并登记 source gap/assumption。
- VO／O.S.／介质声身份不清：保留原文并使用 `unresolved`，不得静默改变声音身份。
- 多语言权威不清：保留全部候选并请求确认；不能凭模型熟悉度选择。
- 只有梗概：使用 `concept_board`，明确来源缺口与假设，不声称逐字剧本完整。
- 用户要求的参考文件缺失：不得声称已读取；对应缺口进入 source gap，并在需要时阻断相关事实确认。

## 4. 工具失败

- Schema 或语义校验器异常：保留内部草案和错误日志，但不产生正式 READY。
- XLSX、Markdown 或 JSON 写入失败：`build-all` 删除 staging，正式目录保持不存在或为空。
- parity 校验失败：validation 状态为构建失败并仅通过 CLI/日志返回；不得留下看似完整的正式目录。
- 文件命名失败：草案可使用临时 slug；正式构建前必须满足 Schema。

工具失败不要求重新设计镜头，但必须修复工具或另行人工交付，不能由后端谎报四文件已完成。

## 5. 状态

- `READY`：来源、审批、Alignment、结构和四文件 parity 无已知确定性问题；不等于审美被机器认证。
- `READY_WITH_ASSUMPTIONS`：仍有明确、可追踪的开放假设或非阻断 warning。
- `FAIL`：结构、来源、语义、审批、执行锁或正式构建存在阻断。

## 6. 需要提问的门槛

只在两种解释会改变说话者、台词、人物身份、剧情结果、现实层、关键物理方向或用户指定方法时提问。一次只问最影响结果的一项，并给出可逆的当前草案假设。

## 7. 不得作为艺术停止理由

不能仅因缺外部场号、缺最终 slug、镜头角度／运动比例统一、单镜过短／过长、用户未指定导演名、固定镜头较多或构图正面而判艺术失败。Schema required 字段缺失、来源遗漏或正式事务失败则不是“优雅降级”，必须阻断正式构建。
