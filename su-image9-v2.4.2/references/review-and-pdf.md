# 真实图片、选用与确认版PDF

只处理实际图片与导演决定，不增加导演表、逐格审批或生成接口。完整净图不画生产标签；程序在每格有效框上方加白色标签带，不挤压构图。

## 编号与身份

单时点12，多时点19a／19b／19c按镜内先后，其中任一可为基准；同刻备选19c-E1不推进时间；修改同一格使用r01→r02而非E2。原编号和前导零保留，原编号带字母时用分隔符避免碰撞。内部ID依项目、来源、时点与关系，不用页格位置冒充身份。

标签正确不证明内容覆盖，不能给两幅重复图贴不同号冒充动作过程。重新分页只移位置，实质时点／摄影／身份更改要重核。

## 登记与有限修订

命令中的<skill-root>必须是本次真实选择的完整目录。

```text
python3 <skill-root>/scripts/review_assets.py init --manifest <prompt-set-manifest.json> --project <项目集场>
python3 <skill-root>/scripts/review_assets.py status --manifest <prompt-set-manifest.json>
python3 <skill-root>/scripts/review_assets.py register --manifest <清单> --labels 19b --image <真实图片.png>
```

init不代表已出图。register保留原始字节并解码成无损PNG，按EXIF归正，透明底合白；每次新增r版本且待审，不覆盖原版。--tool、--model、--call-record只填真实宿主返回数据，不以提示词型号冒充实际后端。载荷/revised_prompt有则原样记录，无则标未暴露。

整页先实际找九格有效边界，再用register-sheet --page <页号> --image <真实页图> --boxes <坐标JSON>。坐标为归正后像素left/top/right/bottom，右下不含边界；需完整、无重叠、按阅读顺序，不默认宽高三等分。程序只验证数值，不认内容。

共同输入错先修共同条件，输入正确而某格画错时提取真实目标格编辑，再拼回其余原图。手物接触要整体成立，不能生硬粘贴遮掩。装饰少但任务正确不反复重画；同策略失败不无限尝试，预算按授权。

## 看图不是一条空PASS

用agent-check记录具体观察与缺口，例如谁持物、谁未接触、前景肩归谁、反应是否可见。先看实际画面再回来源，跨页按同一身份锚与源时点比较。头尾成立不认证中间路线，没看图不填passed。此记录不改变导演批准。

```text
python3 <skill-root>/scripts/review_assets.py agent-check --manifest <清单> --labels 19b --status needs_changes --note <实际观察>
python3 <skill-root>/scripts/export_review.py --manifest <清单> --stage review --format png --output-dir <新审阅目录>
```

真实用户按镜号反馈后才用decide --status approved/needs_changes --evidence <原话>。--all仅对应明确批次；批准Skill升级不是批准尚未看过的图。脚本保存证据不鉴别人，不得由Agent编造确认。

## 输入改变与旧批准

新图r02不继承r01。采用描述、页面有效状态、画幅或标签变更沿原规则使相应记录待核。2.4.2额外将准备后的页Prompt、作用域策略与参考绑定摘要纳入派生execution_basis，并在spec摘要绑定；即使原主稿未变，换输入策略或参考也不能把旧批准挪给新任务。

旧清单无execution_basis时保持旧读取及原摘要算法，不追认已符合新策略。新集合可用init --previous-manifest携带未变图与决定；依据改变的旧图标旧计划／待审，不能只换hash使其有效。保守失效可能扩大到整页或较大范围，本版不绕过，不开发自动依赖图。未改图原文件保留。

select --labels 19b --revision r01只改选用指针，不覆盖r02；r01若未确认或旧依据已失效仍不允许正式导出。

## PDF只排有效选用图

```text
python3 <skill-root>/scripts/export_review.py --manifest <清单> --stage final --format pdf --paper A4 --output-dir <新最终目录>
```

正式范围每格须有真实、当前、已确认图片。待审打包用--stage review并明确标识；缺图不造占位，不复制邻格。--pages可导完整页子集，保留原页号和部分范围说明。

保持有效画幅，等比完整放置，不拉伸、镜像或裁关键前景。A4／A3和横竖纸张按源画幅选择；可加时点短注，不默认复制全部Prompt。export-report记录清单、字节hash、选中版本与有效框，不是视觉合格证。导出后实际渲染检查文字、标签对图、比例、浅阴影和关键手势。

## 可选媒体依赖与真实工具边界

文字准备使用标准库；图片解码、PNG与PDF需要Pillow／ReportLab。export_review.py --doctor检查；有安装授权才运行setup_review_env.py --install或在自有虚拟环境pip install -r requirements-review.txt，不偷偷改系统Python。

字体从本机读取，以--font或SU_IMAGE9_FONT指定可嵌入且覆盖中文的TrueType文件，TTC必要时--font-index；无可用字库如实报告，不交乱码，不单独分发字体。没有本机实际验收不冒称支持所有阅读器。

模型／quality只按宿主真实暴露参数选择，不固定动态型号或旧规格，不声称本Skill能够切换隐藏后端。维护测试可用合成几何图验证文件／版本机制，不能将这种夹具称为真实预演或导演已确认作品。
