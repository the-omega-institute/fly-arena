# Fly Arena

An open evolutionary playground built on real fruit fly connectomes. Humans and AI agents mutate neural parameters, design digital flies, and compete in standardized embodied environments.

用真实果蝇神经图谱，让人和 AI 修改神经网络参数设计数字果蝇，然后在多种竞技环境下 PK。

Current status: architecture and research specification, **not an implemented simulator or deployed arena**.

- [完整架构与产品机制](docs/ARCHITECTURE.md)：FlySpec、权重预算、具身闭环、比赛 harness、接口、存储、渲染和 C++ 决策。
- [调研依据与资源核查](docs/RESEARCH.md)：MaleCNS、Eon、FlyGym、trureturing、NyxID / Heca / Ornn；已确认事实与未验证事项。
- [实施路线与验收关卡](docs/ROADMAP.md)：从真实数据和单蝇闭环到网页设计、AI 提交、多地图竞技与工程化。

Design date: 2026-09-16 (Asia/Singapore). [PR #1](https://github.com/the-omega-institute/fly-arena/pull/1) is historical reference. Its remote arbitrary-controller model is superseded here by platform-executed, connectome-constrained submissions for ranked competition.
