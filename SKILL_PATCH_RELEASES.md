# 三项Skill维护小版本

本批基于 `868d795ee7a43d8ae41bdb465fc36d489b2cb77a`，按三份已讨论的独立优化方案实施。三个目录均为完整独立版本，历史目录、无版本旧入口及其他文件保持原样。

| Skill | 本批目录 | 内部版本 | 基线 |
|---|---|---|---|
| 导演分镜 | [su-fenjingskill-v4.0.1](su-fenjingskill-v4.0.1/) | 4.0.1-candidate | su-fenjingskill-v4.0.0 |
| 视频Prompt | [su-promptskill-v2.2.2](su-promptskill-v2.2.2/) | 2.2.2-candidate | su-promptskill-v2.2.1 |
| 九宫格预演 | [su-image9-v2.4.2](su-image9-v2.4.2/) | 2.4.2-candidate | su-image9-v2.4.1 |

## 实施重点

分镜区分初次设计与局部修改，突出整场观看，将项目反应节奏与通用计时分开；六列主稿及原后端保留。

Prompt保持原序相邻、一源镜一Cut与语义合镜，恢复每组当前初态；新增可选的本次可访问素材范围，避免把全项目无关库存写进正文。

image9保持完整九格和可选参考，隔离全场状态存档与当前绘图输入；单格不默认附另八格全文。准备后的Prompt与参考摘要绑定审阅依据，新策略或参考不继承旧批准。

## 验证边界

离线回归共44项：分镜9、Prompt17、image9 18，全部通过。各包包含CHANGELOG.md、VALIDATION.md、tests/acceptance-cases.md、测试源码和test-result.json。

测试证明明确的结构、作用范围、字面保存和图像修订机制，不认证完整创作质量、实际模型传输或真实视频效果。图像测试使用临时合成PNG，模拟批准明确为TEST ONLY，不代表用户批准实际作品。

未调用付费生图/视频，未在用户Mac/Codex/CodeBuddy运行完整创作，未完成Excel/PDF客户端显示验收。因此内部保留candidate，真实专业与媒体效果仍待验收。

## 使用实际版本目录

命令中的 `<skill-root>` 指向本次选择的完整目录。无版本su-fenjingskill/、su-promptskill/、su-image9/仍是历史入口，不在本批覆盖。每个宿主选择一个实际版本，不应同时安装全部同名历史Skill。

本批只同步GitHub，不自动改变本机全局Skill目录，不静默安装依赖，不修改已有用户作品或批准。
