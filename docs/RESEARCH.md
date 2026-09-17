# 调研依据与核查记录

调研日期：2026-09-16，Asia/Singapore（节点回执为 2026-09-15 UTC）。本记录区分源码/文档事实、只读运行观测与设计建议；未执行神经仿真、物理仿真、GPU benchmark 或部署。

## 1. 参考 PR 与需求变化

[Fly Arena PR #1](https://github.com/the-omega-institute/fly-arena/pull/1)，head `9b809978322e62ae08ac90fb2c18eb8b18004e3a`。

实际阅读了 PR 描述、`docs/IMPLEMENTATION.md` 和 `docs/SOURCES.md`。PR 提供实验与实施规格，未实现网站、物理仿真或完整 SDK。其边界是玩家自行运行任意 controller，平台提供身体、场景和网络比赛协议；真实 connectome 和脑图编辑不在首版范围。

本轮用户需求明确改为：真实图谱是核心，网页和 AI 都修改神经网络，平台执行可验证参赛产物。因此保留 PR 中的同一物理世界、地图共同数据源、整数时钟、租约 fencing、失败分类和回放证据设计；替换远程 arbitrary controller 作为正式排名核心的选择。PR 的 4090 假设不沿用，按当前 Mac Studio 与 4060 资源设计。

PR 自报的旧测试结果不作为本轮实现证据；没有合并该 PR。

## 2. MaleCNS：最新数据目标

官方来源：

- [MaleCNS 项目主页](https://male-cns.janelia.org/)。
- [发布说明](https://male-cns.janelia.org/release/)。
- [数据下载](https://male-cns.janelia.org/download/)。
- [项目网站源码](https://github.com/janelia-flyem/male-cns/tree/bb60b22ebef51856f3118cd559d22d2a3ac74053)，实际读取 `docs/index.md`、`docs/release.md`、`docs/download.md`。
- [Cell 论文入口](https://www.cell.com/cell/fulltext/S0092-8674(26)00942-6)，由官方主页链接；本次未阅读全文。

官方主页确认 v1.0 于 **2026-06-08** 发布，论文于 **2026-09-03** 发表。数据覆盖成年雄性果蝇 CNS，包含脑与腹神经索，与 FlyWire 成年雌性脑不同。官方页面声明数据为 **CC BY 4.0**。

实际下载页的候选导入资源：

| 文件 | 内容 | 官方标称大小 |
|---|---|---|
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | cell type / class / side 等注释，不含递质 | 13 MB |
| `body-neurotransmitters-male-cns-v1.0.feather` | 每 neuron 的递质预测 | 42 MB |
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | 包含有突触 segment 的完整 segment-to-segment 图 | 1.1 GB |
| `syn-points-male-cns-v1.0-minconf-0.5.feather` | 每个突触点的位置、body ID、ROI | 12.7 GB |
| `syn-partners-male-cns-v1.0-minconf-0.5.feather` | 突触配对、位置、置信度与 body ID | 6.8 GB |

起步只需注释、递质预测和连接权重表；不要先下载完整 EM 和所有形态资产。官方使用 segment 范围，平台须定义保留哪些 neuron 和 fragment。网络上常见“约 165k neurons / 25.5M edges”不能不经导入计数就写成平台实测规模。本轮未下载数据文件，也未计算其 SHA-256。

公开图谱中的“连接强度”主要是结构统计。膜时间常数、有效突触电压、受体特异作用、感知编码、运动输出与学习规则仍需模型假设和校准。产品应展示真实数据来源和建模层。

## 3. Eon：神经动力学与多后端参考

官方仓库 [eonsystemspbc/fly-brain](https://github.com/eonsystemspbc/fly-brain/tree/a3db62f9436074e485c0278290c2164ed6150808)，检查时 main commit `a3db62f9436074e485c0278290c2164ed6150808`，提交时间 2026-08-29。

实际阅读：

- [README](https://github.com/eonsystemspbc/fly-brain/blob/a3db62f9436074e485c0278290c2164ed6150808/README.md)：FlyWire v783、LIF、脉冲导出和 backend benchmark。
- [Brian2 runner](https://github.com/eonsystemspbc/fly-brain/blob/a3db62f9436074e485c0278290c2164ed6150808/code/run_brian2_cuda.py)：参数、方程、权重装配和 standalone 运行。
- [PyTorch runner](https://github.com/eonsystemspbc/fly-brain/blob/a3db62f9436074e485c0278290c2164ed6150808/code/run_pytorch.py)：CSR/COO、状态、延迟缓冲、稀疏计算与参数。

源码确认参数包括：

| 参数 | Brian2 数值 | 意义 |
|---|---|---|
| `w_syn` | `0.275 mV` | 与结构计数相乘的有效突触尺度 |
| `t_mbr` | `20 ms` | 膜时间常数 |
| `tau` | `5 ms` | 突触衰减时间常数 |
| `t_rfc` | `2.2 ms` | 不应期 |
| `t_dly` | `1.8 ms` | 突触延迟 |
| `v_th` | `-45 mV` | 发放阈值 |
| `v_0 / v_rst` | `-52 mV` | 静息/重置电位 |

PyTorch 使用 `wScale=0.275` 和 `DT=0.1 ms`。源码同时有 reset、不应期门控和延迟处理，不能只复制这张参数表就声称不同后端相同。Brian2 C++ standalone 与 CUDA standalone、PyTorch、GeNN、NEST GPU 是可比较的候选；本次没有独立复现它们的速度与精度。

README 的 `~5M synapses` 口径不应用来替代 FlyWire 原始突触接触数量：其模型使用聚合稀疏连接表，必须明确 contact 与 neuron-pair edge。神经 benchmark 的多 trial 可共享同一 W，Arena 的不同玩家 W 则需要不同实现或显存分配。

主要缺口：公开 runner 以激活/抑制神经元和批量脉冲输出为中心，并非本项目已经可用的 `sense → neural step → body step` 适配层。`net.run / device.run` 路径还需验证在线注入、持久状态与 checkpoint。不能据“全脑仿真开源”推断完整具身数字果蝇已交付。

许可：该固定版本 README 声明仓库总体 **GPL-2.0-or-later**，部分上游 Shiu 材料为 MIT。未来复用时按具体文件保留来源与许可证，决定代码组合及发布方式；这也是不直接把整个 Eon 仓库粘入平台的工程原因。本轮未复制其实现。

## 4. 身体：FlyGym / MuJoCo 与 flybody

[FlyGym v2.1.0](https://github.com/NeLy-EPFL/flygym/releases/tag/v2.1.0)，GitHub release 时间为 2026-06-24。

实际读取 [pyproject.toml](https://github.com/NeLy-EPFL/flygym/blob/v2.1.0/pyproject.toml) 确认：Python `>=3.12,<3.15`、MuJoCo `>=3.9,<3.10`；可选 Warp 依赖 `warp-lang>=1.14,<1.15`、`mujoco_warp>=3.9,<3.10`。源码声明 Apache-2.0；实际模型/mesh/下载资产仍需单独列许可。

实际读取 [BaseWorld](https://github.com/NeLy-EPFL/flygym/blob/v2.1.0/src/flygym/compose/world/base_world.py)，明确支持多个 fly，并通过 `add_fly()` 将 MJCF 合并到同一个世界。这个 API 支持项目方向，但不证明格斗接触已经调通。

阅读 Eon 的 [flybody README](https://github.com/eonsystemspbc/flybody)；它指向原始 [TuragaLab/flybody](https://github.com/TuragaLab/flybody) 及 [Nature 身体仿真论文](https://www.nature.com/articles/s41586-025-09029-4)。flybody 是身体/运动控制训练框架，不能与 connectome 自动等同。

首版选择 FlyGym / MuJoCo 作为统一身体世界适配层，以兼容参考 PR 和多身体组合。后续若采用其他身体，通过新的 EmbodimentProfile 接入，重新验收，不混入旧排行榜。

GPU 同模型批处理、solver 选项变更和复现限制在 PR #1 来源中已有记录；本轮只核对当前依赖与多蝇源码，未独立运行 GPU 教程。MuJoCo 重跑条件参考 [官方 reproducibility 文档](https://mujoco.readthedocs.io/en/stable/computation/index.html#reproducibility)，此链接为继续实验阅读入口。

## 5. trureturing：借鉴其权威与证据结构

用户指定 [trureturing](https://github.com/the-omega-institute/trureturing)。远端检查时 `dev` 为 `2a79bd8d9dc9c393b30fc0a6455513008ecbcb4c`，时间 2026-09-15 17:00 UTC。工作区已有本地 checkout `95bdccbb30197f8a6faa4aca2e2ecfb3816612a9`；它不是最新，因此另外读取远端固定提交核对核心架构。

远端读取：

- [tools/ARCHITECTURE.md](https://github.com/the-omega-institute/trureturing/blob/2a79bd8d9dc9c393b30fc0a6455513008ecbcb4c/tools/ARCHITECTURE.md)。
- [tools/TOWER.yaml](https://github.com/the-omega-institute/trureturing/blob/2a79bd8d9dc9c393b30fc0a6455513008ecbcb4c/tools/TOWER.yaml)。
- `tools/`、`StrataLint.Engine/` 与 `Admission/` 的目录结构。

本地 checkout 补充阅读 `README.md`、`Meta/FILEMAP.toml`、`tools/scripts/local-harness-gate.sh` 和 `.github/scripts/harness-gate.sh`。这些脚本的阅读依据为上述本地 commit，不把它们的细节误标为远端最新代码。

观察到的设计：

1. Harness 程序放 `tools/`，测试放 `tools/tests/`，`Meta/` 是数据与 registry/ledger 边界。
2. Lean inspector 在固定 Lean 环境生成源绑定 canonical JSON 与 SHA-256 sidecar；.NET admission 消费报告，职责分离。
3. 明确候选、protected base 和 admission judge 的权限关系；工程 build/test 不是 admission 本身。
4. FILEMAP 声明 artifact kind、produced_by、consumed_by、verified_by；与 registry schema 区分。
5. 生成网页是派生投影，不拥有源文件的权威。
6. `make help` 等统一入口减少多套脚本漂移；TOWER 把组件和验证依赖声明化。

Arena 应学其版本化裁决、artifact custody、可复现证据和分离的执行/验收，不必引入 Lean/C# 或照搬整个治理系统。尤其不能把物理结果包装为形式证明。

核查边界：未运行 trureturing harness，未检查 GitHub required checks 和管理员保护状态，未证明实际部署与架构声明完全一致。其架构文档包含 trusted bootstrap 与 caller-owned human authorization 的描述；这是被研究项目的治理要求，并非本轮架构文档编辑需要用户再批准的指令。

## 6. NyxID / Heca / Ornn

NyxID：读取本地 [官方仓库](https://github.com/ChronoAIProject/NyxID) checkout 的 `skills/nyxid/SKILL.md`、相关 node/service CLI 参考；使用已安装 CLI 做服务发现和只读 SSH 查询。确认可以提供节点代理和凭据注入；Arena 的业务权限、排名、quota 与仿真仍需自己的实现。

Heca：读取 [heca-artifacts README](https://github.com/getheca/heca-artifacts)，该公开仓库是 release mirror，源码在私库。文档声明 host 通过 desktop app/headless daemon 运行，可由 Web app 经 NyxID 登录访问。没有把它当 GPU 集群调度器，也没有安装/升级 daemon。

Ornn：读取 [ChronoAIProject/Ornn README](https://github.com/ChronoAIProject/Ornn)，确认 agent-facing skill lifecycle API，HTTP/MCP、model/runtime agnostic，以及 `search → pull → install → execute → build → upload → share`。NyxID 发现已有 `ornn-api` 服务，但本轮未调用其业务接口、安装 skill 或运行 agent。

Ornn 的合适位置是分发 `fruit-fly-designer` 能力；用户自带任意 agent 也能直接使用 Arena OpenAPI/SDK。Ornn 执行服务不能替代 Arena 的可信官方裁判。

## 7. 只读计算资源核查

通过 `nyxid node list` 和经过筛选的 `nyxid service list` 发现以下资源。下面只记录任务需要的节点名与状态，不保存原始账号、token、私钥或完整服务清单。

| 节点/服务 | 观察 | 尚未证明 |
|---|---|---|
| `macstudio` / `macstudio-ssh` | NyxID online，SSH principal `macstudio` 可执行只读命令 | 可用算力余量、FlyGym/Eon 依赖、长期负载 |
| `deepevo-4060-1-local` / local bridge | NyxID online/dispatchable | 显存、驱动、GPU 运算与渲染可用性 |
| `local-gpu-4060-wsl` | offline | 是否旧部署/同一物理机器 |
| `deepevo-4060-1` | offline | 是否旧部署/同一物理机器 |

Mac Studio 实际执行：

```text
uname -sm                              → Darwin arm64
sysctl -n machdep.cpu.brand_string      → Apple M3 Ultra
sysctl -n hw.memsize                    → 103079215104 bytes = 96 GiB
sysctl -n hw.ncpu                       → 28
```

远端非交互 PATH 找不到 `heca`；检查常见安装位置后，使用 `/Users/macstudio/.local/bin/heca --json daemon status` 确认 daemon 运行，版本 `0.1.0-nightly-20260914-1`、mode `standalone`、agent_count `0`。`daemon relay-status` 返回 enabled=true、state=connected。未据此推断 GPU 或 Arena worker 已部署。本机工作区的 Heca daemon 未运行，与远端 Mac Studio 区分。

4060 的 `deepevo-4060-ssh` 服务声明 online；分别用它允许的 `zwlexa`、`lexa`、`ubuntu` principal 尝试 `uname` 和 `nvidia-smi` 查询，均在执行前返回 `ssh_node_key_missing`（404，error code 1011）。没有成功运行 GPU 命令，没有修改 SSH 绑定，也没有把“节点在线”记为“GPU 已验证”。local HTTP bridge 存在，但本轮未获得其已声明的硬件查询 API，因此没有猜测并调用执行端点。

此问题不阻塞架构交付；GPU 实验前需使一个已有授权 principal 的 SSH node-key 绑定可用，或提供 bridge 的受支持只读状态接口。通过标准 NyxID 管理流程处理，不需要在聊天里粘贴密钥。

## 8. 本次交付的验证边界

已完成：用户指定仓库和 PR 阅读、最新来源定位、核心源码核对、节点发现、Mac Studio 硬件及 Heca 状态只读查询、架构/路线/来源文档编写。

尚未完成：真实 connectome 下载与导入、编译器实现、权重验证器、神经模型运行、身体闭环、双蝇碰撞、网页实现、API/worker 实现、GPU benchmark、自动 agent 设计、部署或上线。任何性能数字、预算范围和排期均是待验证设计，不能引用为运行结果。
