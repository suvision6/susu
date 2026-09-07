# 输出与验收

原始来源是事实权威；Markdown 是本次正文唯一可编辑主稿；JSON 和 Excel 是派生视图，验证报告说明证据范围。

## Markdown

使用 prompt-master/2.1.0；每单元只有段号、来源数组、已知时长、操作 ID 和独立 prompt 围栏。参照 templates/master.md。
正文存在反引号时，围栏须长于正文里任何连续反引号；正文外的元信息不进入 Prompt。
解析器保留正文空格、空行和特殊字符。不要手动 HTML 转义正文，不用超长 pipe 表格。

来源 SHA256 从实际输入字节计算；scope 默认为全部来源。明确部分生成时，在 context.scope 列出同序源 ID，并与主稿范围一致。
程序不接受孤立的多镜正文而没有 Cut 对应；单镜或单源段可以直接使用自然段。

## 复核记录

review-template 只建立 pending 记录，不会批准内容。Agent 重新读取原文后写 reviewer、每个单元的 status、notes 和 unresolved。method 使用 source-to-prompt-and-back；记录绑定 source_sha256 和完整主稿 master_sha256。
status=reviewed 是 Agent 的实际复核声明，不是自动程序已证明自然语言语义。尚未回读、未知事实未解决或有关键错误时，不标 reviewed。
改主稿后旧记录失效。只修受影响内容，但保存新记录前确认其余结论仍适用；不把旧 hash 改个字符串冒充复核。

## 四文件

- `<前缀>-prompt-table.md`：冻结的原样主稿。
- `<前缀>-prompt-plan.json`：原始输入全文、来源快照、当前 Prompt、上下文、Profile 和复核依据。
- `<前缀>-prompt-table.xlsx`：四列阅读视图，必要时同单元续行。
- `<前缀>-prompt-validation.json`：内容、提交、文件及阅读状态。

名称沿用旧基础，内部合同已升级。旧版交付继续使用旧验证器；不承诺新旧私有 Python 函数或旧表格解析器兼容。

Excel 列宽／行高按内容估算。正文过长采用精确片段续行，不截断、不缩字号、不新增 Cut、不重复时长；重新拼接时不插入额外换行。
含续行时不加普通行筛选，避免把单元拆散。字号 11pt；物理显示预算用于切阅读片段，不作为创作长度上限。实际客户端字体可能不同，估算不冒称像素级排版验证。

Excel 导出失败时保全主稿、JSON 和报告，明确缺失文件；不能用空 XLSX 冒充成功。输出必须为新目录，禁止覆盖既有文件。正常写入后重新读取四文件再报告完成。

## 状态分开

mechanical_status 只说明可确定的源序、字面、事件和格式检查。
content_fidelity 为 review_required、agent_reviewed 或 blocked，不是语义可靠率。
submission_ready 还要求实际平台条件、素材和操作依赖满足。默认未核实配置不会自报可提交，但不妨碍主稿交付。
file_integrity 说明保存和内容一致；readability 默认 not_rendered。真实渲染证据另存维护记录，不自动把文件通过改写为视觉已验收。

PASS 表示本次声明的检查与条件满足；WARN 表示有正文／完整文件但仍待语义或提交条件；PARTIAL 表示局部内容或文件未完成；FAIL 表示全部单元存在已知关键错误或整体无法读取。任何状态都不能代替各维度说明。

validate 对照原始输入及冻结主稿检查 JSON、Excel 和报告，不重编译中文来自证。修改 Excel 内容会报错；仅改变布局时返回 layout_changed_only，仍不宣称新布局已视觉检查。
hash 用于一致性和意外篡改检测，不是防攻击者同时重写全部文件的数字签名。
