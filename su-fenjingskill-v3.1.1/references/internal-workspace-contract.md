# Internal Workspace Contract｜director-workspace/3.1.0

director-workspace/3.1.0 是导演工作与审计载体，不是正式交付文件。

## 顶层

    workspace_contract
    source
    director_method
    gate_1
    scene_strategies[]
    review_lock

## source

保存 locked_text、source_hash 和 source_units[]。每个非空来源行必须进入至少一个 source unit。covered 单元必须引用正式镜头；有意隐藏或省略必须有理由。

## director_method

保存当前主方法的可执行合同。它必须包含时间模型、基本编辑单元、边界优先级、不切规则、蒙太奇／交叉规则、视点、空间、表演、摄影机、声音、连续性、题材适配和误用边界。

## gate_1

- mode：user_specified | confirmed | required | invalidated；
- status：passed | pending | invalidated；
- method_hash：绑定当前 director_method；
- note：记录用户指定依据或确认说明。

required 或 invalidated 不得进入正式 Gate 2。

## scene_strategies

每个正式 scene_id 对应一个策略。包含 primary/secondary mechanism、信息路径、场面调度、时间／剪辑结构、节奏、表演、声音、方法应用、冲突解决、风险和 topology[]。

topology 单元引用正式 shot refs，但不进入正式 director-shot-data。每个非末尾边界说明：

- source_change；
- mechanism_need；
- method_basis；
- alternative_rejected。

## review_lock

保存 source_hash、method_hash、strategy_hash、topology_hash 和 Gate 状态。哈希只用于判断确认材料是否变化，不进入导演认知或正式交付。

## 正式交付边界

工作区验证通过后，再把 director-shot-data/3.1.0 交给正式构建器。工作区不得产生第三张 XLSX 工作表，不得成为第五个正式文件。
