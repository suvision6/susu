# 镜号、批量审阅与确认版PDF

本参考只处理实际图片、排版和选用。取帧主稿仍是唯一创作输入，不增加新的导演表或逐格审批。

## 1. 一个来源身份，三种显示关系

默认在每格有效画框上方增加白色标签带，黑字左对齐，不挤占画面。正文中的九格仍不让模型画编号。顶部显示“镜号 | 类型”，下一行显示修图版本和待审／需改／已确认；需要时在底部加时点短注。净图另存，PDF不作为视频参考图片。

| 来源关系 | 显示方式 | 解释 |
|---|---|---|
| 源镜只有一个时点 | `12 | 基准` | 保留原编号和前导零 |
| 同镜多个时点 | `19a | 过程`、`19b | 过程`、`19c | 基准` | 字母按已写明的镜内时间；基准不必是a |
| 同刻备选 | `19c-E1 | 同刻延展` | 不推进时间、不自动变成新Cut |
| 修改上述某幅图 | `r01`改为`r02` | 修图版本不是E2 |

原镜号已带字母时保留，例如`07A.a`。遇到合成标签与既有原镜号碰撞时用分隔符，不更名源镜。项目/集/场身份在页头与清单中保留；同号来自不同来源须在输入里给出不含糊的完整身份，程序不会猜它们是不是同一镜。

内部画格ID由项目、来源和明确时点派生，不用P03-C08作为身份。重新分页只移动位置；改取帧顺序/时点或采用内容时重新核对。旧评论不静默套给重命名或新含义画面。同刻延展的观察内容改变会成为新的候选身份，旧文件仍在旧清单里。

标签正确不意味着图片正确。必须先核对实际哪一格是什么内容；不能给重复画面分别贴号，冒充覆盖完成。

## 2. 初始化与登记：沿用全页Prompt清单

先按[交付说明](delivery.md)保存全页Prompt集合。下面命令由Agent执行，导演只需要正常说“19b修改”“其余确认”。

```bash
python3 scripts/review_assets.py init \
  --manifest /工作/prompt-set-v1/prompt-set-manifest.json --project "项目-集场"
python3 scripts/review_assets.py status \
  --manifest /工作/prompt-set-v1/prompt-set-manifest.json
```

该操作在现有清单中增加`review`，派生标签、时点和待审记录，不代表已出图。原有Prompt文件和检查器仍可用；修订历史保存到`review-history/`，这不是第二份人工剧情数据。

**逐格结果：**

```bash
python3 scripts/review_assets.py register \
  --manifest /工作/prompt-set-v1/prompt-set-manifest.json \
  --labels 19b --image /实际结果/19b.png
```

只有宿主确实给出工具名、模型和调用载荷时，才附`--tool`、`--model`及`--call-record`。文件中的模型字符串是操作者记录，不是程序验证；不能把“提示词要求2.5”当成实际型号。载荷含revised_prompt时保留原文件，不能用它静默重写采用稿。

登记会保留原始字节，并创建解码后的无损PNG净图供排版；按EXIF方向归正，透明区域合到白纸背景，不改变姿态或构图。每次新结果形成r01、r02等版本，自动回到待审；原版本不覆盖。

**整页结果：**先实际检查九格有效区域，排除页边距、格缝、边框、已有标签；不要默认把宽高直接除以三。准备下列`boxes.json`形式的真实像素位置：

```json
{"1": [12, 30, 192, 350], "2": [208, 30, 388, 350], "3": [404, 30, 584, 350],
 "4": [12, 370, 192, 690], "5": [208, 370, 388, 690], "6": [404, 370, 584, 690],
 "7": [12, 710, 192, 1030], "8": [208, 710, 388, 1030], "9": [404, 710, 584, 1030]}
```

这些数字仅演示格式，不能套在其他图片上。坐标以经EXIF归正后的图片左上为原点，右/下为不包含边界。

```bash
python3 scripts/review_assets.py register-sheet \
  --manifest /工作/prompt-set-v1/prompt-set-manifest.json \
  --page 3 --image /实际结果/Page-03.png --boxes /工作/Page-03-boxes.json
```

边界须完整九格、无重叠、阅读顺序正确。程序核对边界数值，不识别九格内容；实际框内人物错位仍由Agent和导演检查。原整页保留，提取有效图像不插值放大。

## 3. 批量候选、有限修正与导演决定

在约定批次中先生成、自查和有限修正，再统一交带号审阅页。2.4.1增加跨页比较：核心人物对照同一身份锚与其有效参考，站坐／朝向／位置／持有对照当前源镜时点，结构对照本场骨架；整页内自洽不能替代跨页一致。检查记录由实际看图产生，工具不自动认证锚。批量不等于无依赖并行，也不要求每页问一次；首批明显共同错误先修共同输入，避免传播。

Agent记录实际观察：

```bash
python3 scripts/review_assets.py agent-check \
  --manifest /工作/prompt-set-v1/prompt-set-manifest.json \
  --labels 19a 19b 19c --status passed --note "已看原图：姿态先后可辨、茶盏接触案面；记录具体观察。"
```

这不会把任何图片标为已确认。不要复制该示例说明来假称已经看过图片。

默认输出供用户一次浏览的带号PNG：

```bash
python3 scripts/export_review.py \
  --manifest /工作/prompt-set-v1/prompt-set-manifest.json \
  --stage review --format png --output-dir /工作/review-r01
```

用户明确确认或提出修改以后才登记：

```bash
python3 scripts/review_assets.py decide \
  --manifest /工作/prompt-set-v1/prompt-set-manifest.json \
  --labels 19b --status needs_changes --evidence "这里记录用户针对19b的实际修改意见"
python3 scripts/review_assets.py decide \
  --manifest /工作/prompt-set-v1/prompt-set-manifest.json \
  --all --status approved --evidence "这里记录用户明确确认当前全部图像的实际原话和版本"
```

`--all`只能对应明确批次范围的用户指令。脚本无法鉴别说话者，保存证据不是身份认证；Agent不得编写或推定用户同意。用户批准Skill升级，不等于批准尚未看的图片。缺图、图片被外部替换、计划改变、有效画幅错误时不得登记为确认成功。

每个决定绑定实际净图字节、采用内容、显示标签和图像版本；2.4.1也将“页面说明”中的有效调度状态纳入依据，改动该页说明会保守地要求该页重新核对，不能只换页头却沿用旧确认；新的r02不会继承r01的确认。没有改图的其他格继续沿用原文件。看图者、确认者与自动检查各自声明，不将其混写。

明确恢复某个已有版本可用`review_assets.py select --manifest ... --labels 19b --revision r01`，只改变选用指针，不覆盖r02；原r01从未确认或所依据计划已变时仍不能正式导出。

仅局部修图时优先给真实单格目标和相关参考，明确“改什么、保留什么”；不把其余八格重新交给模型。相关手、人物与物件仍需整体成立，不能靠生硬粘贴掩盖接触断裂。修后复看该格与邻近过程；未解决内容作为待改项交导演，不无限尝试。

改稿需要重新生成Prompt集合，在新集合初始化时可用`--previous-manifest /旧目录/prompt-set-manifest.json`继承未变图片与决定。相关文字或标签已变的记录必须重新确认；旧图片若基于旧描述，需重新登记经检查的真实结果，不能只改hash放行。原始文件留在旧目录时不要删除它们。

## 4. PDF只排已选图，不重新创作

```bash
python3 scripts/export_review.py \
  --manifest /工作/prompt-set-v1/prompt-set-manifest.json \
  --stage final --format pdf --paper A4 \
  --output-dir /工作/final-r01
```

默认各页按有效画幅选择竖/横纸张；提供A4、A3，可显式指定`--orientation portrait`或`landscape`。标签占框外位置，不让人物缩进原画幅腾字。待审版允许真实但画幅不符或基于旧描述的候选用于诊断，清楚标为需重新确认并在报告列明，不拉伸“修正”；正式版仍拒绝这些错误。图像等比例完整放入，不拉伸、不镜像、不裁关键前景；相对画框原像素可以因输出阅读尺寸缩放，净图保留原尺寸。`--captions`可增加时点短注，不默认复制全套Prompt。

正式PDF要求本次导出范围每格都有真实、当前且已确认的图；未确认默认拒绝正式版。用户明确要求打包待审图时用`--stage review --format pdf`，标题明确待审。缺图不生成占位，不复制邻格；可以用`--pages 1 2`明确导出完整页子集，PDF标明部分范围及原页号，不称全片完成。

输出还包含`export-report.json`，记录所用清单快照、每格实际图像hash、版本、有效画框和文件清单。它是排版记录，不是轴线或语义合格证；疑似逐字节相同图像仅提示，不自动删除源镜。

导出后在阅读器渲染检查中文、标签对图、比例、边界、浅阴影和关键手势。页脚与导出记录读取本包VERSION，不继续写死旧版本。PDF中文字可搜索并嵌入所用字体子集；不单独交付字体。导出器不调用模型、不同序、不自行选最新文件，也不把过程格重复计时。不汇总原稿未提供的秒数。

## 5. 可安装的媒体后端，不依赖内部模块

文字、JSON、全页Prompt、标签派生和状态管理仍使用Python标准库。**真实图片解码与审阅PNG/PDF**采用可选公开依赖：Pillow和ReportLab。

```bash
python3 scripts/export_review.py --doctor
# 已获安装授权时，显式创建虚拟环境并安装，不修改系统Python：
python3 scripts/setup_review_env.py --install
# 或在自有虚拟环境内：
python3 -m pip install -r requirements-review.txt
```

安装后应使用该虚拟环境的Python执行图片登记和排版。脚本不会偷偷安装，网络、代理、pip权限或字体限制可能导致安装未完成，必须说明；不能把它说成图像任务需要补参考图。声明支持Python 3.10+；当前候选只在记录所列环境实测，不冒称已经验证用户Mac。

中文字体只从用户本机读取。优先使用可嵌入、覆盖所用字符的TrueType `.ttf` 或TrueType `.ttc`；不保证所有同名TTC都能嵌入，CFF字库会明确失败。使用`--font /本机/中文字体.ttf`或环境变量`SU_IMAGE9_FONT`，TTC必要时加`--font-index`。无可用字库则提示真实原因，不以乱码、空白方块或未经嵌入的替代字体伪报成功。

## 6. Image 2.5的适用边界

2026-09-09重新核对的OpenAI官方模型索引与Sunburst模型页显示：GPT Image 2.5有Sunburst和Flare；Sunburst面向精确编辑、Flare面向快速生成。Sunburst模型页列出low、medium、high、xhigh、max、auto。这里不把旧版gpt-image-2的尺寸、透明底、input_fidelity或成本公式当成2.5规格。

执行时以真实宿主可用模型与接口为准。复杂交接/编辑可将Sunburst medium作为配对测试起点，Flare同档比较效率；这是待实测方案，不是准确率承诺或硬性门槛。低细节不是quality=low，质量参数也不能消除错误的动作与空间说明。

本版没有直连API的隐藏调用器或模型选择器。输入文件是可读生成说明，不是已执行调用。宿主返回实际载荷/revised_prompt时记录原内容；没有返回不编造。参考可选、小步编辑、只改目标并明确保留项，作为通用工作方法吸收，不宣称仅靠这些句子即可像素级保护构图。

官方核对入口（动态资料，后续接口参数需重新核对）：

- OpenAI模型索引：<https://developers.openai.com/api/docs/models>
- GPT Image 2.5 Sunburst：<https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst>
- 通用图像指南：<https://developers.openai.com/api/docs/guides/image-generation>

本次接受的专业标注与审阅方案保存在维护记录；没有原样迁入ClipShot的墨线/马克笔强制画法、箭头、重新拆镜权限或无限重绘硬门禁。
