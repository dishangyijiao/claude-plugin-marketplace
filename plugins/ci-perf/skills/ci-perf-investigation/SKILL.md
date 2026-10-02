---
name: ci-perf-investigation
description: Use when CI is slow, queues long, or needs performance optimization on GitHub Actions - measure-first method (queue vs run, slow steps, time-to-check, contention). CI 慢、排队久、要优化 CI 性能时使用。
---

# CI 性能调查：先量，再改

开发者感受到的指标 = **PR 事件到"必过检查"完成**（含排队）。通知类 job 排在必过检查之后，它排队不影响这个指标。一次只改一件事，在真实 CI 上用对照验证，并标清每个数字是**实测**还是**推断**。

## 取数据（只读，需要 gh 已登录）

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ci_timing.py collect --repo OWNER/NAME --workflow ci.yml --since YYYY-MM-DD --out runs.json
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ci_timing.py report runs.json \
    --check "<必过检查的 job>" --steps "<最慢的 job>" \
    --overlap-target "<最重的 job>" --heavy "<其他重 job，逗号分隔>"
```

报告四块：**Jobs**（排队 vs 运行）、**Slowest steps**（一定看 `Post ...` 步骤）、**Time to required check**（看 p90 和最慢）、**按并发邻居数分桶的耗时**。

## 症状 → 原因 → 处理

| 症状 | 原因 | 处理 |
|---|---|---|
| 有邻居时同一 job 慢 2 到 3 倍；3 个并发的总耗时约等于串行 | 共享主机 CPU/IO 饱和 | **加 vCPU，不要加 runner 实例**；加之前先确认宿主机确有余量 |
| `Post <action>` 步骤几分钟，只在锁文件变化时 | 缓存**保存**（上传托管缓存）在自建/国内 runner 上极慢 | 见 `self-hosted-runner-health` 第 3 节 |
| `No space left on device` | 磁盘写满（常见：容器卷泄漏） | `self-hosted-runner-health`，先只读审计 |
| 测试全过但整体失败，约几分之一概率 | 偶发（常见：销毁后才触发的定时器） | `flaky-test-hunt` |
| 依赖审计突然红，且无修复版本 | 新漏洞 | 核对是否只在开发工具链、是否进运行时，再登记忽略，写明理由和复查日期 |

## 容易误判（真踩过的）

- 空闲时的收益 ≠ 并发下的收益：worker 从 4 调到 8，空闲快约 30%，并发下可能更慢。
- 迁移只跑一次、给数据库挂 tmpfs、关 fsync：空闲时都没有可测提速（tmpfs 的价值是阻止匿名卷泄漏，是另一回事）。
- 把轻量任务挪到 GitHub 托管 runner 会烧托管分钟：先用 `${CLAUDE_PLUGIN_ROOT}/scripts/audit_runs_on.py` 看哪些 job 在耗、多频繁。
- 对照组恰好是最坏情况（如缓存未命中那次）会夸大收益：写明它是否典型。

## 工具局限

- 并发分桶只看得到**你采集的** job；同机的其他 workflow、仓库没采集会少数邻居，请一起传给 `report`（接受多个文件）。分桶是相关不是因果。
- 时间戳不总可信：时钟偏差的 job 会被丢弃并在报告开头说明数量。
- 只统计 `pull_request` 和 `push`（`--events` 可改）；重跑的 job 以最后一次为准，"到必过检查"会偏短。
- `audit_runs_on.py` 是逐行读取不是 YAML 解析器，只支持块风格的 `jobs:`；读不出 job 时会明说。
