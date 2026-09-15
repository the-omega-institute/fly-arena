# 参考依据与核查边界

日期：2026-09-15。本项目的接口、游戏规则、实验矩阵和阈值是设计选择，不是从论文测得的数值。资料不证明本仓库实现已经可运行。

| ID | 原始来源 | 支持什么/限制 |
|---|---|---|
| S1 | https://github.com/NeLy-EPFL/flygym/blob/v2.1.0/pyproject.toml | 已有实施包核对Python>=3.12,<3.15与MuJoCo>=3.9,<3.10；运行时须解析并锁定真实依赖。 |
| S2 | https://neuromechfly.org/api_reference/flygym/compose/world/base_world/ ; https://neuromechfly.org/api_reference/flygym/simulation/ | 同一world可包含多fly；CPU Simulation、分段姿态、毫米和wxyz接口。本次重新读取。不能据此推断格斗已实现。 |
| S3 | https://neuromechfly.org/tutorials/4d_turning_controller/ | 公共低层转向控制的接口起点，本次读取。冲撞与死亡需本项目实现。 |
| S4 | https://mujoco.readthedocs.io/en/stable/computation/index.html#reproducibility | 积分状态、warmstart及复现条件，本次读取。不承诺跨CPU/GPU位级复现。 |
| S5 | https://fastapi.tiangolo.com/advanced/websockets/ | 已有实施包核对WebSocket支持。 |
| S6 | https://caddyserver.com/docs/caddyfile/directives/reverse_proxy ; https://caddyserver.com/docs/automatic-https | 已有实施包核对反向代理、WebSocket和HTTPS。 |
| S7 | https://www.postgresql.org/docs/current/sql-select.html | 已有实施包核对SKIP LOCKED可用于queue-like读取，需另做lease/fencing。 |
| S8 | https://docs.docker.com/compose/ | 部署工具参考；本PR没有已运行的Compose服务。 |
| S9 | https://docs.docker.com/compose/how-tos/gpu-support/ ; https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html | Compose GPU reservation文档本次读取；具体驱动/容器兼容性需E00实测。 |
| S10 | https://neuromechfly.org/tutorials/3_gpu_accelerated_simulation/ | 本次读取：同batch要求相同模型；示例显示noslip_iterations从5调整为0。不能把批量吞吐当单场延迟，不能跳过后端兼容验证。 |
| S11 | https://github.com/getheca/heca-artifacts/blob/fa39e6dfdb5c4c40cfa16baca0528b61dc9f7435/README.md | 已有实施包核对固定提交：二进制下载镜像、源在私库、host与NyxID。仅可选开发入口，未安装/审计/运行。 |

版本可变的在线文档仅是阅读入口。运行报告必须保存固定源码commit、依赖锁、资产版本和有效模型选项，不把文档显示的latest当作实验版本。

此前会话提供了Fly_Arena_Implementation_Plan.md与fly-arena-agent-handoff.zip。本PR基于其产品边界整理，并新增具体对照、样本矩阵、阈值、失效条件和排程验证；未复制其先前静态验证结果作为本PR运行证据。
