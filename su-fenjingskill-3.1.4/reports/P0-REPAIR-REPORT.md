# su-fenjingskill 3.1.2｜P0 修复报告

## 修复边界

- 语义版本保持 `3.1.2`。
- 固定六列、四文件和两张 XLSX 工作表保持不变。
- 构建修订标识为 `p0-repair-01`，只用于区分同版本修复包。
- 当前规则、Schema、运行时和正式输出不再建立现场筹备管理子系统；迁移器只负责从历史输入中清除废弃字段，且不把旧内容自动搬入备注。

## 七项 P0 修复

### P0-01｜叙事行改标后静默删除

来源台账改为“非空行默认叙事”。只有页码、项目元信息和分隔线等机械可识别内容可自动排除；其他非叙事分类必须写入独立 `classification_review`，明确动作／对白信号仍禁止降级。每个权威叙事 unit 必须由 required fact 持有。

### P0-02｜Schema 与运行时漂移

正式 CLI 先执行 Draft 2020-12 JSON Schema。两套 Schema 均使用 `additionalProperties: false`；手写 validator 只负责跨字段语义。对有效示例实际触达的 required 路径进行逐项删除 mutation：

- formal shot-data：202 / 202 被运行时阻断；
- director-workspace：327 / 327 被运行时阻断；
- 漏检：0。

### P0-03｜摄影、剪辑、连续性未进入执行锁

新增 `execution_hash`，Alignment 覆盖 camera、staging、sound、edit、continuity、duration、motivation、assumptions、notes、scene execution、passage/fact/inference binding 与 canonical execution text。第五列由结构化模型确定性渲染，不允许双写分叉。

### P0-04｜删除假设可伪装 READY

workspace 增加独立 `source_gaps[]` 与 `assumption_obligations[]`。每个来源缺口必须由正式 assumption 或已批准补充来源关闭；删除 `assumptions[]` 不会删除义务，仍有缺口时必须 FAIL 或保持 `READY_WITH_ASSUMPTIONS`。

### P0-05｜Topology 只验证引用存在

每个 topology unit 现在必须满足：shot 属于当前 scene、每镜恰好出现一次、passage refs 与 shot binding 完全一致、fact refs 与 realization 完全一致，并执行双向校验。

### P0-06｜四文件非原子事务

正式入口统一为 `build-all`：在 sibling staging 中生成 JSON、Markdown、XLSX，验证 parity 并计算哈希，最后写 validation，再原子提交整个目录。任一 writer 或 parity 失败均删除 staging，正式目录不留下半成品。

### P0-07｜Gate 失效规则与代码相反

唯一依赖矩阵已写入规则和运行时：

| 变化 | Gate 1 | Gate 2 | Alignment |
| --- | --- | --- | --- |
| 来源、语言权威、分类、passage、fact、gap、补充事实或方法 | 失效 | 失效 | 失效 |
| 场景机制、strategy 或 topology | 保持 | 失效 | 失效 |
| camera、staging、sound、edit、continuity、duration、motivation、assumption、notes 或第五列 | 保持 | 保持 | 失效 |

新增 `approve-gate1`、`confirm-gate2`、`approve-alignment`、`approve-classification` 和 `status` CLI。审批事件以内容哈希链追加，直接编辑状态字段不能恢复当前内容的正式通过。

## 同步修复

- 正式镜头只能引用 `approved` inference，且 inference/shot refs 双向一致。
- 行中否定纳入来源义务；实体归属使用精确 owner，不再用泛化 substring。
- 补充来源 approval hash 覆盖审批状态与说明。
- FAIL 报告不能同时把全部维度显示为 PASS。
- `READY_WITH_ASSUMPTIONS` 默认退出码为 0；`--fail-on-warn` 返回 1。
- Python 文件路径调用与 `python -m` 模块调用均通过。
- XLSX 统一为 openpyxl 单一 writer。
- XLSX 元数据与归档时间已规范化；相同输入重复构建的四个正式文件字节级一致。

## 验证结果

```text
pytest -q
75 passed, 10 subtests passed
```

- 厨房告别示例：`READY`，原子四文件已重建。
- 未知房间概念板示例：`READY_WITH_ASSUMPTIONS`，2 个开放假设，原子四文件已重建。
- 七类 P0 对抗测试：全部 PASS。
- 废弃子系统移除验证：Schema 拒绝历史未知字段；备注不再触发关键字路由；Markdown/XLSX 不生成独立区块。

机器可读结果见 `P0-REGRESSION-REPORT.json`，对抗证据见 `P0-ADVERSARIAL-TESTS.md`。

## 已知边界

审批事件链提供包内一致性和篡改线索，不等同于外部数字签名。任意自然语言命题是否与来源语义完全等价，仍必须由导演或审阅者确认；后端只对可确定的来源 span、主体、否定、结果、引用、哈希和播放关系负责。
