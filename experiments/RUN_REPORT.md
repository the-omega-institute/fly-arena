# 运行报告模板

状态：NOT_RUN

## 身份与冻结

- run_id / experiment_id / batch_id：
- code commit / plan SHA-256 / protocol_revision：
- 运行者与起止时间（含时区）：
- 实际命令与退出码：
- 环境manifest、依赖lock、镜像digest：
- map/body/asset/rules/sensor/action/backend/controller哈希：
- 设备、显存/内存、CPU线程、驱动、网络拓扑、实际solver选项：
- 是否fixture、排程生成、真实physics、真实网络或浏览器：

## 预先规定的比较

- 问题、处理组、对照、配对实体/seed关系：
- 计划样本数、实际attempt数、正常完成数、失败/重试/排除数：
- 主指标/阈值与实际指标（未测留null，不填0）：
- 样本单位和聚类方式：
- 与冻结计划的偏离、原因、发生时间和新revision：

## 结果

填写PASS/FAIL/BLOCKED及逐条依据；未执行保留NOT_RUN。

| case_id | attempt_id | status | reason | metric | evidence path | SHA-256 |
|---|---|---|---|---|---|---|

## 原始证据与解释边界

附environment、metrics、accepted actions、contact/damage events、replay manifest、错误日志与屏幕记录。原始文件存受控目录，提交清单与hash。禁止token/密码/私人SSH key。

分别报告游戏胜负、技术判负、基础设施中断与simulation_error。报告所有失败，不能只展示成功局。确认是否足以开放该能力，不把统计不显著或0/小样本失败当作无偏/无风险证明。
