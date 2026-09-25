# 产品路线与当前进度

更新：2026-09-24。当前部署版本见 `/api/v1/health` 和 GitHub Releases。本文按已上线功能和剩余工作组织；历史实现与研究结果分别见 Git 历史和对应实验记录。

## 当前已交付：rounds 1–2

Round 1 ships the 3D Phenotype Lab scene view, the map registry with explicit observation-only maze status, a unified Arena setup, and the science guide. Round 2 ships the life lineage tree, receipt-backed replay inspection, the `arena-geometry-v1` geometry contract, and the issue-82 phase-1 diagnosis with its preregistered phase-2 study runner. The complete five-seed 180-second phase-2 study is complete with a **negative** preregistered verdict: seeds 42, 45 and 46 were negative, seeds 43 and 44 improved, and the candidate is not promoted. The round-5 analysis and read-only evidence audit are retained in [MAZE_LOCOMOTION](MAZE_LOCOMOTION.md) and `docs/evidence/`. These surfaces keep modeled behavior, recorded observations and unavailable evidence labeled separately.

## 已上线的用户闭环

用户可以在网页设计果蝇、选择有限预算的训练策略、观察真实结果、保存后代，再把后代送入竞技场。人和 AI 使用同一套 FlySpec 与评测 API。

| 环节 | 当前能力 |
| --- | --- |
| 入门与 AI | 首页复制 WT、编辑保存与训练指引；可展开图谱/神经/身体解释；AI 任务提示可复制，公开 `/api/v1/agent-guide` 提供独立接入说明 |
| 设计 | 回路权重、高级连接选择和神经参数编辑；服务端检查变异预算；保留不可变基础连接组与个体亲缘关系 |
| 保存 | 保存后进入训练，选中刚保存的果蝇；用户选择预算后才启动评测；受控 Lab 对比可另行发起 |
| 训练 | 进化、随机搜索、CEM 及用户自己的优化程序；种群、代数、最多四组地图/种子、目标和评测次数有界；完整条件均值作为适应度；可暂停、继续、停止 |
| 策略扩展 | 优化代码运行在用户自己的设备上，通过训练候选 API 提交完整 FlySpec；示例见 scripts/custom_strategy.py |
| 观察 | 逐代与初代成绩、个体参数、父代关系、真实比赛回放与神经活动；最多三个会话的策略比较、条件差异、逐代曲线与评测成本；失败和未完成状态保留 |
| 延续 | 保存后代、以其为起点创建训练分支、导出会话与谱系；训练会话属于提交者 |
| 竞争 | 单只觅食、双只抢食、接触擂台、交换出生位置的系列赛；训练评测不进入公开比赛排行 |
| 环境 | 果园、障碍花园、最后的绿洲、擂台和腐果林地；腐果林地增加真实低坡、抬高通道和椭球障碍，两侧保留地面路线；最后的绿洲只有一个共享的2单位食物点，耗尽后不补充 |
| 计算 | 可选 NyxID 远端执行；当前GPU worker主机使用CPU/Numba，节点重任务串行排队；重连附着原任务 |
| 发布 | 有效 CI、增量 PR、及时合并和版本部署；本地与 configured deployment host 保留已有数据 |

使用方法见 [README](../README.md)、[TRAINING](TRAINING.md) 和 [COMPUTE](COMPUTE.md)。NyxID 用户登录接口与同源 Pages 入口见 [NYXID_LOGIN](NYXID_LOGIN.md)；部署的 `/auth/config` 报告当前是否启用。

## 已有真实运行记录

- 基础进化完成两代、四次评测，验证暂停/继续、重启后状态保留、后代保存与参赛。
- 外部优化程序通过同一 API 在GPU worker主机完成四次评测，记录候选、亲缘关系和完整回放；之后保存并分叉后代。
- 保存的后代与基线在最后的绿洲完成两场各2秒的换边比赛。后代摄食量分别为1.0544、1.1996，基线分别为0.9456、0.6684；场景、轨迹、事件与神经活动均保留。

这些是有限场景和种子的运行记录。参数优化效果、跨环境表现和真实动物行为对应关系需要各自的实验，不能从一次演示直接推出。

## 下一步按用户价值推进

验收目标：第一次进入的人能设计自己的果蝇，选择其学习方式，看懂进化，在丰富三维环境中挑战 WT 或社区设计；用户的 AI 能独立读取说明、设计、训练和分析。

1. **已加入新手引导与 AI 贡献入口。** 复制 WT、编辑保存、进入训练和对照；解释公开连接组如何变成模拟神经与身体；AI 页面先展示任务与接入说明，再展示 JSON 编辑器。WT 挑战预设展示计算量。CI 增加真实 React 控件的 DOM 操作测试，主分支仍要求前后端检查全部通过。
2. **已加入首张立体地形：腐果林地。** 低坡连接抬高叶片通道，果壳/石块形成路线选择；尺寸与四元数共用于物理和网页，回放增加身体高度。地面食物、双侧解析气味和现有步态保持明确，尚未实现障碍阻挡气味、视觉输入、自由飞行或可学习攀爬。下一步继续改善环境复杂度与感觉反馈，不把一张地图视为完成所有自然场景。
3. **用户可选大脑运行方式与学习算法。** 已提供进化/随机搜索/CEM/自定义优化器、外部模型插件和三组真实演化示例；神经运行时现可选 LIF 或实验性连续发放率模型，并提供全图反向传播 + Adam 神经响应训练器（见 [RATE_MODEL](RATE_MODEL.md)）。教学响应损失和真实竞技场得分分开记录。后续根据接口与算力实测接入环境奖励驱动的强化学习。比赛内可塑性和脉冲替代梯度明确列为后续能力，不放未实现按钮。
4. **社区竞争和演化。** 生命档案现已串起出生、算法、亲缘、实际经历、回放和追加研究笔记，可从公开后代继续分叉或准备对战。见 [LIFE_LEDGER](LIFE_LEDGER.md)。继续完善社区发现、挑战赛和赛后差异说明。开放比赛允许不同模型，科学比较明确显示模型和训练条件差异。
5. **计算与登录。** 复用 Python/FastAPI、SQLite 和当前串行 worker；优先GPU worker可用资源，按实际瓶颈选择内核。NyxID OIDC 登录已提供服务端会话与独立 Arena agent token；平台身份服务仍独立于神经、物理和评分过程，是否启用由部署配置决定。

当前浏览器控制工具认证报错只限制本机自动视觉/点击检查。独立 DOM 交互、API、构建、CI 与部署照常推进，不把浏览器工具问题变成项目阻塞。

## 每次增量怎样交付

围绕一个用户可见的改进修改代码，运行与改动相关的检查，通过必要 CI 后合并并部署。影响仿真或资源机制时，增加明确预算的真实运行，保留结果、失败原因和可查看的回放。界面、文档和版本信息描述实际能力。

连接组、参数、环境和运行条件需要记录，以便解释结果。工程流程保持简洁，保护已有账户和实验数据，优先让用户完成设计、训练、竞争和观察。
