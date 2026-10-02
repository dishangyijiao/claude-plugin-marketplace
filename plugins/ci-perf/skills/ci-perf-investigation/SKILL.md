---
name: ci-perf-investigation
description: Use when CI is slow, queues for a long time, or you are asked to optimize CI performance on GitHub Actions - a measure-first method (queue vs run, slow steps incl. Post steps, time-to-required-check, contention by concurrent jobs). 当用户说 CI 太慢、排队久、想优化 CI 性能、PR 等太久时使用。
---

# CI 性能调查：先量，再改

目标不是"让某个步骤变快"，而是**让开发者更快看到必过检查的结果**，并且知道每个改动各贡献了多少。

## 铁律

1. **先取数据，不凭感觉。** 用 `scripts/ci_timing.py` 取 job/step 级耗时，不要只看总时长。
2. **用开发者感受的指标：** PR 事件到"必过检查"完成（含排队）。通知类 job 排在必过检查之后，它排队**不影响**开发者等待。
3. **排队和运行分开看。** 排队长 ≠ 运行慢，处理办法完全不同。
4. **一次只改一件事，每个改动单独归因。** 否则无法回答"到底哪个有用"。
5. **在真实 CI 上验证，不在本机。** 自建 runner 的机器和本机没有可比性；用对照组和实验组、说明样本量。
6. **标清"实测"还是"推断"。** 没复现的猜测不要当成根因去提 PR。

## 步骤

```bash
# 1. 取数据（只读；需要 gh 已登录）
python3 scripts/ci_timing.py collect --repo OWNER/NAME --workflow ci.yml --since YYYY-MM-DD --out runs.json
# 2. 看四张表
python3 scripts/ci_timing.py report runs.json \
    --check "<必过检查的 job 名>" --steps "<最慢的 job 名>" \
    --overlap-target "<最重的 job 名>" --heavy "<其他重 job 名,逗号分隔>"
```

四张表各回答一个问题：

| 表 | 回答 |
|---|---|
| Jobs（queue / run） | 时间花在等 runner 还是真正执行 |
| Slowest steps | job 内部时间去哪了（**一定看 `Post ...` 步骤**） |
| Time to required check | 开发者实际等多久；看 p90 和最慢，不只看中位数 |
| 按并发数分桶 | 同一个 job，邻居越多是否越慢——共享主机争抢的特征 |

## 症状 → 可能原因 → 怎么验证

| 症状 | 可能原因 | 验证 / 处理 |
|---|---|---|
| 同一 job 有 2 个以上并发邻居时慢 2 到 3 倍；3 个并发的总耗时约等于串行 | **共享主机 CPU/IO 已饱和** | 看分桶表；**加 vCPU，不要加 runner 实例**（再多开只会更糟）。注意检查宿主机是否真的空闲再加 |
| 排队很长、运行正常 | runner 槽不够，或被轻量小任务占用 | 看 queue p90；先确认这个排队是否在开发者的关键路径上（通知类不在） |
| `Post <某 action>` 步骤耗时几分钟 | 缓存**保存**（上传到托管缓存服务）在自建/国内 runner 上极慢；只在锁文件变化、缓存未命中时发生 | 把包管理器存储放在 runner 本机持久目录，**按 runner 实例隔离**并设容量上限（见 `self-hosted-runner-health`） |
| 随机失败，报 `No space left on device` | 磁盘写满（常见：容器卷泄漏） | 转 `self-hosted-runner-health`，先只读审计 |
| 测试全过但整体失败；约几分之一概率 | 偶发（常见：测试环境销毁后才触发的定时器/异步） | 转 `flaky-test-hunt` |
| 依赖审计突然红 | 新公布的漏洞，且可能没有修复版本 | 核对路径是否只在开发工具链、是否进入运行时，再决定是否登记忽略并写明理由和复查日期 |

## 常见误判（都是真踩过的）

- **空闲时的收益 ≠ 并发下的收益。** 把测试 worker 从 4 调到 8，空闲时快约 30%，但并发下可能更慢或更不稳。
- **"迁移只跑一次再克隆模板库"：** 墙钟时间几乎不变（一个 worker 迁移，其余在等），收益只在并发时少占 CPU，需要对照证明。
- **给数据库挂 tmpfs / 关 fsync 当提速：** 空闲时没有可测收益；但 tmpfs 能阻止镜像声明的匿名卷泄漏，**理由不同，别混为一谈**。
- **把轻量任务挪到 GitHub 托管 runner** 看似减少排队，实际会消耗托管分钟（免费额度有限，每个 job 至少按 1 分钟计）。先用 `scripts/audit_runs_on.py` 看哪些 job 在耗分钟、跑得多频繁。
- **对照组如果恰好是最坏情况**（比如缓存未命中的那次），收益会被夸大；写明它是不是典型。

## 汇报格式

结论先行；用表格给"之前 / 之后"；标明每个数字是**实测**还是**推断**；写样本量和已知局限（并发、负载、样本过小）；列出还没验证的部分。
