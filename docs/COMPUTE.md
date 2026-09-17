# 计算资源与排队

优先使用 4060 节点执行离线实验，Mac Studio 承担网页、API 和现有比赛服务。同一节点一次运行一个重型实验；按任务实测选择 CPU 或 GPU。网页预览与回放由浏览器 Three.js 渲染，不占服务端 GPU。

## 已有节点

- NyxID SSH 服务：`deepevo-4060-ssh`，principal `root`。
- GPU：RTX 4060 Laptop，8188 MiB；完整 MaleCNS 数据保存在 `/tmp/fly-arena-data`。
- 现有 Python：`/tmp/fly-arena-cuda-device-v1/venv/bin/python`。
- 共享锁：`/tmp/fly-arena-gpu.lock`。所有本项目重型任务共用此锁，包括 CPU/GPU 对照任务，避免彼此影响。
- 当前任务目录：`/tmp/fly-arena-jobs/`。状态、日志和结果保存在各自目录；目录位于 `/tmp`，重要结果应及时取回长期保存。

提交命令使用 `flock /tmp/fly-arena-gpu.lock timeout 900 <command>`。锁被占用时等待；取得锁后才启动超时计时。用独立进程运行，使 SSH 断开不终止任务。排队记录只表示已提交；完成状态以实际进程结果和实验的 `status.json` 为准。

## 2026-09-17 实测

完整 MaleCNS 网络：165,122 个神经元、25,563,197 条连接。比较已有实验性 ordered CUDA 实现与 CPU，固定输入、800 个神经时间步（0.08 秒模拟时间），16 个检查点。

| 测量 | CPU | CUDA |
| --- | ---: | ---: |
| 累计 advance 用时，排除构建和预热 | 0.8522 s | 2.1554 s |

这次短测的脉冲计数和检查点状态一致，最大浮点绝对差为 0。当前 CUDA 实现比 CPU 慢约 2.53 倍；因此同类离线神经任务先使用 4060 节点的 CPU。这个结果只说明该实现与该短时输入，不能外推所有任务，也不说明具身比赛或步态效果。

原始结果：节点 `/tmp/fly-arena-jobs/fullgraph-20260917/status.json`。此处复用了已有实验性 CUDA 模块，没有把它接入默认比赛后端。

## 有预算的权重实验

`scripts/run_neural_sweep.py` 复用应用的 FlySpec、Compiler 和 Brain，先编译全部设计并检查预算，然后串行运行相同感官输入。默认比较嗅觉回路 ×1、×0.9、×1.1。记录每个设计的参数、预算、每 10 ms 的回路平均发放率、每个神经元累计脉冲以及最终神经状态。

```sh
PYTHONPATH=src OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMBA_NUM_THREADS=1 \
  flock /tmp/fly-arena-gpu.lock timeout 900 .venv/bin/python \
  scripts/run_neural_sweep.py --data data --output var/sweeps/olfactory-01 --duration 3
```

这是同条件神经响应实验。它不包含身体、食物得分或胜负，也不自动把发放率更高的设计选成下一代。竞争与演化的选择应使用明确场景下的实际比赛结果。

实际完成的首组实验使用 3 秒输入、每只 300 个采样点，三只串行共约 127 秒（包括编译和保存）：

| 嗅觉连接倍数 | 变异预算 / 100 | 全网络累计脉冲 | 仿真执行时间 |
| --- | ---: | ---: | ---: |
| 1.0 | 0 | 4,348,365 | 36.28 s |
| 0.9 | 1.309089 | 4,260,841 | 36.20 s |
| 1.1 | 1.184215 | 4,427,972 | 36.14 s |

发放数量变化说明这些有预算的连接干预影响了此模型的神经响应；它不能用作适应度排名。原始记录在节点 `neural-sweep-20260917/results`，每个 subject 包含完整 FlySpec 和实际数组。

## Route the app's match queue to a NyxID compute node

The optional executor uses the existing application queue and a single shared file lock on the node. NyxID handles the SSH connection; it is not imported into neural dynamics, physics or scoring. Research Lab jobs retain their existing executor. Legacy matches and training evaluations can use the remote node; other profiles retain their local path.

Install the same released source and locked Python environment on the node, with the canonical graph and the same readout. Create a configuration file on the app host (no credentials go in this file):

```json
{
  "service": "deepevo-4060-ssh",
  "principal": "root",
  "root": "/tmp/fly-arena-embodied-v020",
  "data": "/tmp/fly-arena-data",
  "nyxid": "/absolute/path/to/nyxid"
}
```

Start the app with `ARENA_NODE_CONFIG=/absolute/path/to/node.json`. The app host must already have an authorized NyxID CLI session. Omit the variable to keep local execution; configuring a node does not install credentials or activate NyxID end-user login.

Admission checks that scientific sources, dependency lock, graph, readout and rules agree, then records the **node's actual runtime**, including its platform and Python/MuJoCo versions. The node recompiles each submitted FlySpec and checks the artifact identity. Results return to the originating app for ordinary evidence verification and replay. An unavailable configured node returns 503 at admission rather than silently changing the execution environment. Already admitted jobs keep observing the same remote job during a temporary transport outage.

Each remote match uses its existing match ID as the node job ID. Repeated submission attaches to the same process/result. A retry never restarts a simulation just because an SSH response was lost. Heavy runs acquire `/tmp/fly-arena-gpu.lock`, shared with operator experiments; queued jobs wait for it. Current execution uses CPU/Numba because the measured ordered CUDA implementation is slower for this workload. The node records progress, errors and retained evidence under `var/node-jobs/JOB_ID/`.

Keep the node source and data in place while jobs are active. Update or disable routing after queues drain; changing execution configuration is an operator action, not a player's setting. Completed jobs retain their evidence for reconnects. As in the existing queue, a process that actually disappears without a result is reported as failed.
