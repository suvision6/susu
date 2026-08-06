# 15 位导演风格路由

本文件只负责 Gate 1 候选检索与归因边界；最终候选结构、profile、选择与确认规则由 [director-profile.md](director-profile.md) 独占。路由不使用数字评分，也不把导演姓名当作“模仿”指令。

## 检索方法

1. 从场景需求中识别任务、时间、观看、摄影机、空间、表演、类型变化与受保护过程。
2. 用下表的匹配标签排除明显不适配项。
3. 在剩余项中选主选、替代、对照；三项都须适配来源，并在四个核心维度中形成真实差异。
4. 同等匹配时按下表文件顺序决胜。不得用分数、权重或隐含配额改变稳定顺序。
5. 默认只读取三个入选导演卡；用户要求更多时先用本索引列出所有剩余合格项，选中后才再读取一张卡。

读取导演卡后，按 [director-profile.md](director-profile.md) 把卡内“Profile 默认建议”编译为本场专属 `director_profile`，并结合“典型入口”与“对白调度偏好”生成 `directing_plan.entry_strategy` 与 `dialogue_design`。

## 稳定索引

| 稳定顺序 | 策略名 | 参考导演与别名 | 文件 | 语义匹配标签 |
| --- | --- | --- | --- | --- |
| A | 类型转向中的社会空间 | 奉俊昊 / Bong Joon-ho / 봉준호 | [director-bong-joon-ho.md](director-bong-joon-ho.md) | 类型转向、阶层、群体、空间高低差、黑色幽默 |
| B | 物理任务的交叉压力 | 克里斯托弗·诺兰 / Christopher Nolan / Nolan | [director-christopher-nolan.md](director-christopher-nolan.md) | 倒计时、多线并行、任务、因果、空间清晰 |
| C | 冷面荒诞的反高潮 | 科恩兄弟 / Coen Brothers / Joel Coen / Ethan Coen | [director-coen-brothers.md](director-coen-brothers.md) | 荒诞、犯罪、误会、反高潮、尴尬停顿 |
| D | 行为控制下的心理压迫 | 大卫·芬奇 / David Fincher / Fincher | [director-david-fincher.md](director-david-fincher.md) | 心理控制、审讯、程序、精密对白、信息操纵 |
| E | 日常裂缝中的梦境恐惧 | 大卫·林奇 / David Lynch / Lynch | [director-david-lynch.md](director-david-lynch.md) | 梦境、不明恐惧、身份裂缝、诡异日常、延迟解释 |
| F | 宏大空间中的静默压力 | 丹尼斯·维伦纽瓦 / Denis Villeneuve / Villeneuve | [director-denis-villeneuve.md](director-denis-villeneuve.md) | 威胁、未知、科幻、尺度、静默、环境压力 |
| G | 仪式与权力的平行推进 | 弗朗西斯·福特·科波拉 / Francis Ford Coppola / Coppola | [director-francis-ford-coppola.md](director-francis-ford-coppola.md) | 家族、权力、仪式、背叛、平行蒙太奇 |
| H | 家庭日常中的反应余波 | 是枝裕和 / Hirokazu Kore-eda / Koreeda / Kore-eda | [director-hirokazu-koreeda.md](director-hirokazu-koreeda.md) | 家庭、日常、儿童、失落、隐忍、生活细节 |
| I | 巴洛克巡游与情绪蒙太奇 | 保罗·索伦蒂诺 / Paolo Sorrentino / Sorrentino | [director-paolo-sorrentino.md](director-paolo-sorrentino.md) | 仪式、音乐、奢华、宗教、孤独、群像巡游 |
| J | 欲望空间的概念切割 | 朴赞郁 / Park Chan-wook / Park | [director-park-chan-wook.md](director-park-chan-wook.md) | 欲望、复仇、秘密、精密视觉、越界、物件 |
| K | 对话蓄压后的类型爆发 | 昆汀·塔伦蒂诺 / Quentin Tarantino / Tarantino | [director-quentin-tarantino.md](director-quentin-tarantino.md) | 长对白、威胁、类型游戏、延迟暴力、章节感 |
| L | 制度空间的中心秩序 | 斯坦利·库布里克 / Stanley Kubrick / Kubrick | [director-stanley-kubrick.md](director-stanley-kubrick.md) | 制度、控制、对称、仪式、冷峻、几何空间 |
| M | 镜头内部的冒险发现 | 史蒂文·斯皮尔伯格 / Steven Spielberg / Spielberg | [director-steven-spielberg.md](director-steven-spielberg.md) | 冒险、家庭、奇观、镜头内发现、清晰群体调度 |
| N | 图形舞台上的秩序喜剧 | 韦斯·安德森 / Wes Anderson | [director-wes-anderson.md](director-wes-anderson.md) | 对称、喜剧、童话、物件陈列、章节、正面舞台 |
| O | 记忆时间里的亲密错位 | 王家卫 / Wong Kar-wai / Wong | [director-wong-kar-wai.md](director-wong-kar-wai.md) | 爱情、记忆、错过、主观时间、遮挡、城市孤独 |

## 典型任务回归锚点

下表用于回归测试“主选、替代、对照”三种不同解法，不是实际来源的固定套餐。正式运行仍须重新检查三项都适配锁定来源；若替代或对照不适配，按稳定索引重选。

| 场景核心任务 | 主选 | 替代 | 对照 |
| --- | --- | --- | --- |
| 倒计时、多线任务与物理因果并行 | 物理任务的交叉压力（参考克里斯托弗·诺兰） | 镜头内部的冒险发现（参考史蒂文·斯皮尔伯格） | 宏大空间中的静默压力（参考丹尼斯·维伦纽瓦） |
| 精密对话、审讯或心理控制 | 行为控制下的心理压迫（参考大卫·芬奇） | 制度空间的中心秩序（参考斯坦利·库布里克） | 欲望空间的概念切割（参考朴赞郁） |
| 家庭日常、隐忍反应与生活余波 | 家庭日常中的反应余波（参考是枝裕和） | 镜头内部的冒险发现（参考史蒂文·斯皮尔伯格） | 记忆时间里的亲密错位（参考王家卫） |
| 梦境、身份裂缝与无法解释的恐惧 | 日常裂缝中的梦境恐惧（参考大卫·林奇） | 宏大空间中的静默压力（参考丹尼斯·维伦纽瓦） | 记忆时间里的亲密错位（参考王家卫） |
| 冒险、奇观与镜头内部逐步发现 | 镜头内部的冒险发现（参考史蒂文·斯皮尔伯格） | 物理任务的交叉压力（参考克里斯托弗·诺兰） | 类型转向中的社会空间（参考奉俊昊） |

## 归因边界

- 只把导演卡中已经记录的公开风格倾向作为参考，最终输出必须改写为场景专属策略。
- 不复刻具体电影镜头、台词、人物、场面或标志性构图。
- 不能由导演卡推出的做法，标记为本场导演推断，不冒充该导演的固定规律。
- 不因知名度自动入选，也不把多位导演混成一个标签。
