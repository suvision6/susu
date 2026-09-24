# 正文、素材范围与文件交付

单条无文件要求直接交Prompt，不运行文件流水线。批量从同一个prompt_text交付：四列Markdown与Excel（Prompt段号、来源镜号、总时长、Prompt）、prompt-plan.json、prompt-validation.json和prompts/G01.txt等独立正文。TXT不含组号、日志、参数与外层围栏。

## 原工作稿与命令

Python3.10+，核心与XLSX使用包内标准库，无网络或账号必需依赖。Agent使用[主稿](../templates/master.md)写好正文，导出器去解析外壳，不重新编译中文。旧“单元／对应来源／内容预计时长／### Prompt”仍可读取。

```text
python3 <skill-root>/scripts/export_prompt.py --input <工作稿.md> --source <采用稿.json> --context <context.json> --check
python3 <skill-root>/scripts/export_prompt.py --input <工作稿.md> --source <采用稿.json> --context <context.json> --output-dir <新目录> --prefix <项目名>
python3 <skill-root>/scripts/export_prompt.py --validate <交付目录> --source <采用稿.json> --input <工作稿.md>
```

使用实际选择的Skill目录，不照抄无版本旧路径。context无需要时可省；不传source仅保存和格式检查，不认证来源覆盖。来源支持导演MD、shots/source_shots JSON与文字源段，其他复杂材料由Agent读取。工具不自动生成Prompt、导演或视频。

## 现有context的局部补充

保留scope、operation_scopes、scene_keys、boundaries、assets、inventory_complete及units。范围必须为原序选择，场次补充不能覆盖源场次；已声明边界的用途与证据按[来源与合镜](source-and-grouping.md)处理。

2.2.2在units[Gxx]可选支持accessible_asset_tags。未提供保留旧库存规则；[]明确表示本次无可访问素材；非空数组须唯一、原样、库存存在且可用，包含本单元采用集合。只有此次可访问而不采用的编号进入“未采用素材”。无实际范围证据不默认填[]。

报告units[].asset_access区分explicit_declaration、legacy_inventory、unknown、invalid_declaration；provider_access始终是not_verified_by_script。文件存在检查不等于观察身份或上传成功。配置仍随原Plan保存，不新增上游合同或交付文件。

执行设置沿units[Gxx].request记录；required_literals只供少量明确硬文字核对，非必填。共用执行依据归档，不整段注入每组；当前锚由Agent写入实际正文。

## 检查与返回值

核对显式原序、覆盖、相邻、场次、已声明边界，Decimal预算及本项目30秒／更低服务限制；核对可识别的实际对白字面、声位、次数与Cut映射；素材作用范围、正文参数泄漏及占位符。未知自然表达和语义仍须回查。

0为本次机械步骤完成，待核时为checked_with_review；1为内容／输入问题；2为文字与JSON已存但Excel未完成。已知问题仍可保存完整最佳稿及报告，不标完成执行验收。单元缺口应定位受影响镜号、条件与所需决定，无关内容继续。

四种载体来自同一正文，<音效>与竖线只在表格转义。长内容精确续行，不删字、不重复时长或新增Cut；直接复制优先TXT。--json-only仍交TXT／MD／JSON。新目录保护旧文件和批注，来源只读。

保留su-prompt-plan/2.2与su-prompt-validation/2.2。旧--validate只验证当时文件一致性，不追认新素材规则或语义；使用新版本--check重新读取实际来源与context才执行本轮检查。hash不是签名，不防止同时伪造全部证据。未调用模型、未看视频，不报视频效果通过。
