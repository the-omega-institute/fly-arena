# 本次变更的验证边界

日期：2026-09-15。

## 已实际执行

执行环境：本会话工作容器，Python 3.13.5。排程工具只依赖标准库；此环境不是用户的4090主机。

```text
python3 -m unittest discover -s tests -v
Ran 15 tests ... OK

python3 scripts/experiment_plan.py validate
scope: DESIGN_VALIDATION_ONLY
runtime: NOT_RUN
```

覆盖：计划样本数、全排程case_id唯一与确定性、所有case保持NOT_RUN/metrics=null、E11阶段筛选、E05成对出生交换、重复ID、非法count、NaN/Infinity和非整数步时间、重复factor、pilot/confirmation seed不重叠、错误计数、非法筛选、JSON重复key、精确文件SHA-256、CLI生成和禁止覆盖已有文件。

plan.json 的精确字节 SHA-256：

`4ac3ff124a9cd01d1de3d6ce7f7af2a6f9eae9ec361e44e686168e0a69bc035b`

当前排程任务数：E00=2，E01=80，E02=100，E03=100，E04=102，E05=40，E06=40，E07=36，E08=60，E09=72，E10=27，E11=1440。不同实验的任务单位不同，这些不是已经完成的独立对局数。

## 尚未执行

FlyGym/MuJoCo安装与仿真、两只身体碰撞、真实controller、任何GPU运行、Docker/Compose启动、云端/本地联网、浏览器渲染、观众压测、安全故障注入及备份恢复。

没有证明身体冲撞可达性、CPU/GPU等价、任何4090容量或实时速度。experiments/status.json全部保留NOT_RUN。没有触发/等待GitHub CI，也没有访问用户服务器。

该PR可审查与合并的是设计和排程工具。应用实现和实验完成必须由本地agents提交真实证据后再确认。
