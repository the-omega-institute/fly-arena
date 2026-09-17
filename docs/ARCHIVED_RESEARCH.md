# 旧 PR 与研究结论归档

2026-09-17：平台已通过 PR #2、#12、#14 合入 main。旧实验、未接入能力和过期设计从 PR 队列移出。GitHub 已关闭 PR 仍保留讨论、提交和差异；本地实际实验数据没有删除。关闭不等于实验成功，也不抹掉负结果。

| PR | 结论 / 后续用途 |
| --- | --- |
| [#1](https://github.com/the-omega-institute/fly-arena/pull/1) docs: 果蝇竞技平台具体实验设计、双机部署与 agents 执行方案 | 最初设计已被真实connectome MVP取代，4090和远程任意controller假设不再适用。 |
| [#3](https://github.com/the-omega-institute/fly-arena/pull/3) Add optional ordered CUDA neural backend and differential verifier | 可复用的可选CUDA内核保留在历史中；不以未接入产品的后端草稿占据主线。 |
| [#4](https://github.com/the-omega-institute/fly-arena/pull/4) Add frozen DN observability diagnostics and independent verification | DN观测和读出候选未达到目标，保留负结果和数据。 |
| [#5](https://github.com/the-omega-institute/fly-arena/pull/5) Add stopped anatomical contact-to-motor research candidate | 解剖触觉到运动候选未通过神经前提，停止该候选。 |
| [#7](https://github.com/the-omega-institute/fly-arena/pull/7) Record real knee transduction and failed closed-loop contact causality | 膝关节神经驱动部分成立，触觉闭环因果效果未成立。 |
| [#8](https://github.com/the-omega-institute/fly-arena/pull/8) Record real RTX 4060 tiny CUDA differential validation | 实际4060微型神经测试有价值，但不能外推全图性能；合并进研究总结。 |
| [#9](https://github.com/the-omega-institute/fly-arena/pull/9) Research: tethered contact-presence responses and matched fly comparisons | 系留触觉实验保留为研究记录，不作为自由竞争产品实现。 |
| [#13](https://github.com/the-omega-institute/fly-arena/pull/13) Record gait commissioning and fail-stop evidence retention | 早期步态试验和停止记录归档。 |
| [#15](https://github.com/the-omega-institute/fly-arena/pull/15) Diagnose distal-foot scuffing from retained physics evidence | 足部拖地诊断结论保留，不继续独立诊断PR。 |
| [#16](https://github.com/the-omega-institute/fly-arena/pull/16) Measure v16 unloading gains and unresolved support regressions | v16改善卸载却损害支撑/滑移，候选未通过；保留负结果。 |
| [#17](https://github.com/the-omega-institute/fly-arena/pull/17) Document verified Mac Studio and RTX 4060 node access | 节点访问信息已确认，过时的堆叠文档分支归档。 |
| [#18](https://github.com/the-omega-institute/fly-arena/pull/18) Add guarded fullgraph CUDA runner and independent verification | 全图运行/验证框架尚无全图实际结果，不继续扩展基础设施。 |
| [#19](https://github.com/the-omega-institute/fly-arena/pull/19) Add research contracts for richer sensory and motor channels | 更丰富的感觉/运动接口尚无实际闭环效果；未来按产品需要重用。 |
| [#20](https://github.com/the-omega-institute/fly-arena/pull/20) Add experimental contact-aware gait realization controller | 接触控制候选未完成有效步态验证，停止堆叠。 |
| [#21](https://github.com/the-omega-institute/fly-arena/pull/21) Add registered native mechanics trials for contact controller | 预检通过，8.4秒物理前缀因耗时预测停止，没有候选主动步态结果。 |

后续科研围绕竞争与演化：记录每个个体的神经表现、行为、适应度、亲缘和变异；以真实比赛结果产生下一代。旧候选可在需要时从闭合 PR 取回，不重新打开整条依赖链。
