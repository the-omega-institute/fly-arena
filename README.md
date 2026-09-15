# Fly Arena

可编辑场景、共同物理世界、开放参赛接口和三维观战。平台提供地图与裁判，玩家自行设计并运行果蝇控制器。

**当前状态：实验与实施规格，以及可执行的实验排程检查工具。没有已完成的网站、SDK、仿真器或部署。所有实际运行实验均为 `NOT_RUN`。**

## 本地 agents 从这里开始

1. 阅读 [实施与部署](docs/IMPLEMENTATION.md)，固定责任边界与接口。
2. 阅读 [具体实验设计](docs/EXPERIMENTS.md)，按 E00 至 E08 建立正确性证据。
3. 按 [AGENTS.md](AGENTS.md) 分工；读取 [机器可读计划](experiments/plan.json)。
4. 将真实执行结果按 [报告模板](experiments/RUN_REPORT.md) 保存，禁止将 fixtures 当成物理实验结果。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/experiment_plan.py validate
python3 scripts/experiment_plan.py generate --experiment E05 --output /tmp/fly-arena-e05.jsonl
```

最后一条命令只生成待执行排程，不会运行仿真，也不会标记 PASS。输出中的每一行均为 `NOT_RUN`。

首个完整交付：网页发布地图，两个独立玩家进程接入，本地 worker 在同一世界运行双蝇，远端网页展示真实接触、游戏死亡和本局回放。

正式基础路径为 CPU 单世界、每场两只、同时一场。4090 GPU 后端是独立验收项。首版远程自带控制器赛道标记 `remote-open`，不保证算法身份、固定算力或无人工干预。

参考依据见 [SOURCES.md](docs/SOURCES.md)。本次规格检查与未执行边界见 [VALIDATION.md](docs/VALIDATION.md)。
