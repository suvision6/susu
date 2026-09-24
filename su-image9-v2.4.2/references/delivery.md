# 主稿、有效生成输入与完整页交付

Python3.10+。主稿解析、Prompt准备和明确覆盖核对使用标准库；真实图片登记与PNG／PDF排版才需要可选Pillow／ReportLab。没有生图工具与没有参考图是不同问题。

## 同一主稿与原语法

使用[image-plan.md](../templates/image-plan.md)，保留一级标题及本轮来源、本轮范围、本次任务、画幅与媒介；共用视觉依据下四个明确三级小节；取帧表三列；每页本页范围／页面说明；每格对应来源／画面关系／所取时点／text围栏。不要用加粗列表或新顶层状态字段替代解析语法。

原导出器只做保存：

```text
python3 <skill-root>/scripts/export_image_plan.py --input <视觉主稿.md> --check
python3 <skill-root>/scripts/export_image_plan.py --input <视觉主稿.md> --output-dir <新目录> --prefix <项目名>
```

完整全范围输入：

```text
python3 <skill-root>/scripts/prepare_prompt_set.py --input <视觉主稿.md> --director <采用分镜.md> --require-coverage --output-dir <新Prompt目录>
python3 <skill-root>/scripts/prepare_prompt_set.py --verify-dir <已保存Prompt目录>
```

只选部分源镜可用--source-shots，必须属于独立导演稿原序。没有导演稿只核对视觉主稿声明，不能冒称原片完整覆盖。取帧表验证已选时点映射，不证明过程选足；结构检查不认证身份、轴线或画面。

局部输入：

```text
python3 <skill-root>/scripts/prepare_image_request.py --input <视觉主稿.md> --page 1 --output <新目录/Page-01-input.json>
python3 <skill-root>/scripts/prepare_image_request.py --input <视觉主稿.md> --page 1 --panel 2 --output <新目录/Panel-02-input.json>
```

有真实参考时每个--reference配一个--reference-use；无图两者省略，不造占位。显式缺失文件只定位该依赖，不说明无参考任务不可执行。

## 完整意味着当前任务的有效输入完整

明确四小节的新稿启用explicit_sections_scoped：只从执行prompt隔离全场状态档案；单格还不带其余八格与全页后续说明。稳定身份／空间／画法、目标格完整时点与正文仍保留。Agent负责写全当下，不使用“同上”代替内容。

旧稿栏目不明使用legacy_full_context保留原文字，报告未隔离。单格旧输入会保留同页上下文；局部整理原视觉主稿后再启用新行为，不改上游导演稿。

shared_context、page_context、image-plan.json与原master是回查存档，不是第二份运行Prompt。宿主只传prompt字段与真实附件，不能又把全JSON粘入。全页TXT、对应JSON.prompt、all-page-prompts.md逐字一致，packet hash只证明准备文件一致，不证明真实模型收到。

全页清单保存当前策略、实际页Prompt及参考绑定摘要作为execution_basis；审阅以此连同原采用描述绑定选用。新策略／参考变更不会沿用旧批准；旧清单没有此字段仍按旧证据读取，不追认为已隔离或已附图。

## 文件与结果边界

输出全页TXT／请求JSON／完整阅读稿、coverage-report.json、image-plan.json、prompt-set-manifest.json。不只交第一页或JSON路径冒充完整输入。真实图与审阅记录由后续宿主和[审阅工具](review-and-pdf.md)加入。

写入前检查全部目标，保护原主稿、采用稿、参考及不同内容旧文件。只回滚本次创建字节，不删除历史。范围或Prompt变更输出新目录，旧批注与版本保留。返回0只表示这次机械操作完成；任何未生成、未看图、未确认项目如实记录。
