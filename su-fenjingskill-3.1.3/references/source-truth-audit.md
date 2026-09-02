# Source Truth & Internal Audit｜剧本事实与来源义务

本文件只拥有来源事实、反向覆盖、来源缺口和来源歧义边界。它不得决定镜头数量、切点、景别或导演方法。

## 1. 锁定来源

保留完整 locked text、输入类型、批准修正、来源哈希和语言权威。多语言来源必须明确 performance authority、reference languages 与 literal/adapted/independent 关系；未决时硬失败。

逐场及 GLOBAL scope 识别：

- 场景头、时间、地点和现实层；
- 人物、关系和在场状态；
- 逐字逐语言对白、说话者及来源声音身份；
- 动作、动作结果、因果、关键道具和不可逆状态；
- 场景进入状态、离开状态及跨场继承；
- 来源没有提供、但镜头设计必须暂定的空间或执行信息。

来源未明确的内容不得冒充事实。导演可以提出可逆选择，但必须属于 approved director inference 或由 source gap 持有的 assumption。

## 2. 不可省略的 source ledger

`source_units[]` 对 locked text 的每个非空行恰好登记一次。默认规则：**非空行属于叙事完整性范围，除非它可被机械证明是文档元信息。**

可自动排除的项目仅限窄范围，例如：

- 独立页码；
- “片名／作者／版本／日期”等键值元信息；
- 纯分隔线。

场景标题和转场必须匹配明确格式。疑似对白或动作的行，即使被填写成 metadata/non_narrative，也必须硬失败，不能靠重新计算 hash 洗白。

确需人工排除时，建立 `classification_reviews[]`，记录 unit、decision、status、reason、source text hash、reviewer 与 review hash，并通过 `approve-classification` 形成审批事件。分类审批不能覆盖“疑似叙事内容不得降级”的机械保护。

## 3. passages 与 facts

`source_passages[]` 把连续权威 units 组成语义完整、可显示的来源段落。passage 与 shots 是 many-to-many；它回答“原文去了哪里”，不决定切点。不得把“另一处。”“抬头。”“高空。”等上下文碎片单独当第三列。

`source_facts[]` 通过 passage、unit IDs、逐字 source span 和 anchors 保存不可丢失语义。

- 每个权威叙事 unit 至少有一个 required fact owner；supporting 不能独占 unit。
- entity attribute、action result、negation、causal link、source sound、reality change 和 world rule 等受保护类型不得降级。
- `source_span` 不能缩成单字或无意义碎片；必须逐字存在并足以承载当前命题。
- anchors 必须逐字存在于对应 source units。
- 后端从 locked unit 独立派生否定、动作结果、因果、声音、身份／技术等级、世界规则、现实层和不可逆结局义务；同时删除 fact、realization、topology 和 execution 仍不能清除来源责任。

## 4. source gaps 与 assumptions

概念材料、缺失平面、未提供参考文件或其他必要空白进入 `source_gaps[]`。每个 gap 必须由 `assumption_obligations[]` 关闭：

```text
source gap
→ one obligation
→ one formal assumption
  或 one approved supplemental source fact
```

删除 formal assumption、清空 assumptions 或删除 gap ledger 会使来源模型与审批哈希失效。未解决 gap 不得伪装为 READY。

## 5. 对白与声音

- 一个完整来源发言只登记一次。
- 画面可在发言期间切换；片段按镜头顺序拼接后必须逐字等于来源。
- stage direction 不计入口播文字，但必须进入动作、表演或停顿设计。
- source voice type 与当前镜头 delivery 分开；来源 V.O. 不得因摄影选择变成现场对白。
- 无法判断 V.O./O.S./mediated 时使用 unresolved，并形成真实待确认项。

## 6. shot binding 与 inference

每个正式 shot 至少绑定一个权威 passage。required fact 必须有 realization，保存：实现方式、execution span、精确主体 owner、结果 span 和 polarity。

主体匹配只允许精确实体或明确所有格身体／声音部位；不使用 substring。director inference 只能引用存在且 approved/hash-valid 的 source/reference facts，自身也必须 `status=approved`，并与 shot refs 双向一致。

## 7. 反向审计

交付前从 locked text 反查：

1. 每个非空行是否恰好进入一个 unit；
2. kind、scope、language、authority role、行范围和 exact text 是否真实；
3. 非叙事分类是否机械合法或有有效审批；
4. 每个权威 unit 是否进入完整 passage；
5. 每个叙事 unit 是否有 required fact owner；
6. 每个 protected fact 是否有充分 source span、anchors、正确主体、结果和 polarity；
7. 每个 required fact 是否进入 realization 和 topology；
8. 每条对白是否逐字、连续、不重复、不倒序；
9. 每个 source gap 是否被一条有效义务关闭；
10. supplemental/reference/inference 是否已批准且双向绑定；
11. source model、execution 与 Alignment hashes 是否对应当前内容。

## 8. 硬失败

包括来源哈希不匹配、unit 漏失／重复、叙事行降级、passage 片段化、fact inventory 自我删除、主体／结果／否定／因果反转、错误场景或错误 topology、未批准推断、未关闭 gap、对白改写、审批事件与当前 hash 不匹配。

来源审计只存在于 workspace 与内部报告；不得增加正式第五文件或把内部审计文本塞进六列。
