# 正文与文件交付

## 主交付

单条需求：直接输出完整可用Prompt，不以文件或检验流程阻止正文交付。批量文件：每组有独立纯TXT，同时保留历史四文件；不要求操作者从审核报告中找正文。

- `<prefix>-prompt-table.md`：四列，段号/来源镜号/总时长/Prompt。
- `<prefix>-prompt-table.xlsx`：同四列，一个Prompt Table工作表，无插入的审核说明行。
- `<prefix>-prompt-plan.json`：原始来源快照、主稿、实际prompt_text与可选提交设置。
- `<prefix>-prompt-validation.json`：本次确实完成的机械/文件检查。
- `prompts/G01.txt`等：只含该组最终正文，不含组号、参数、代码围栏和日志。

TXT是直接复制入口。表格渲染层将<音效>和竖线转义，不改变Plan或TXT。Excel通常一组一行；极长文本受文件显示容量影响时，精确续行保留全部文字，不删Prompt、不缩字、不增加Cut或重复时长。此时完整复制优先用TXT，报告列出续行，不冒称所有客户端显示已经验收。

## 内部工作稿不是最终输出

Agent使用templates/master.md保存已经写好的结构化正文。围栏与来源字段只是内部文件解析边界；导出器去外壳后逐字派生，不重新写中文。也支持0.4.8的“单元/对应来源/内容预计时长/### Prompt”既有形式，但旧内容若不符合新正文规范会具体提示。

`共用执行依据`被保存到Plan，不被脚本整段注入Prompt，避免未来状态或参数污染。Agent应把当前单元需要的具体锚写入主体/关系与场景及保持一致；脚本不能替代这一专业转换。可在context.units中用required_literals检查少量显式硬文字锚，非必填。

## 命令

运行时Python3.10+，包内核心与Excel工具均可用标准库执行，没有artifact_tool、openpyxl或网络必需依赖。旧XLSX序列化、模板读取和字体测量帮助器从完整0.4.8继承；新布局只保留四列成品正文。

```bash
python3 su-promptskill/scripts/export_prompt.py --input work/master.md --source adopted.json --context work/context.json --check
python3 su-promptskill/scripts/export_prompt.py --input work/master.md --source adopted.json --context work/context.json --output-dir outputs/r01 --prefix ep19
python3 su-promptskill/scripts/export_prompt.py --validate outputs/r01 --source adopted.json --input work/master.md
```

无参考/无需额外场次补充可不传context；不传source时只保存与格式检查，不认证来源覆盖。source支持现行导演MD、含shots/source_shots的JSON，以及未分镜文字源段。复杂表格/附件识别由宿主Agent先完成。工具不为用户自动导演或自动生成Prompt。

context由Agent按实际需要写，用户不填写：可有scope、operation_scopes、scene_keys、boundaries、assets、inventory_complete和units。scope及每个操作范围先验证为原序中的有序选择；scene_keys只补没有明确场次号的项，不能覆盖来源场次。boundaries按[合镜参考](source-and-grouping.md)区分真实结束、明确提交分段和历史位置，不填N−1份多维表。历史边界不自动成为禁合证明；旧式未分类记录报告用途待复核，拟跨越时先明确。素材availability是实际观察/用户说明，文件存在不等于身份认对。示例见templates/context.json。

## 检查范围和返回码

- 来源：按原序展开范围、唯一覆盖、相邻性、场次ID与已声明结束。
- 时间：Decimal精确累计与30秒项目限制、较低已知服务限制、请求不足。
- 声音：只校对body/明确对白字段中可识别的播放片段，检测漏/改/重；未知自然说法仍需Agent回查。原文栏不参与重复播放。
- 正文：主要区块、Cut映射、明显参数/元信息外泄、占位符与实际素材职责。
- 交付：TXT/JSON/MD/Excel相同正文，来源只读，新目录保护旧批注。

0：本次机械步骤完成，不等于语义或视频通过；有待复核项时mechanical_status为checked_with_review。1：已知内容问题或输入错误；2：文字/JSON已保存但Excel失败。已知内容问题仍可保存完整最佳稿与报告，不能将错误稿标为完成验收。--json-only显式跳过Excel而仍交TXT/MD/JSON。

--validate比较原文件摘要与保存内容，不重编译中文来自证。摘要用于一致性，不是数字签名；它无法防止人为同时重写所有证据。脚本不联网、不装包、不读取凭证、不提交视频，不改变已有采用稿。

2.2.1保持su-prompt-plan/2.2与su-prompt-validation/2.2文件系列兼容；新增grouping_metadata记录边界用途与检查依据。--validate仍只核对旧交付文件是否一致，不追认旧语义通过；要按2.2.1重新检查，应加载工作稿、实际来源与本轮context运行--check。
