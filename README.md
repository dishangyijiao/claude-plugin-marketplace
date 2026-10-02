# claude-plugin-marketplace

个人的 Claude Code 插件市场，里面的插件都来自真实的工程实践，并且**只保留通用的方法和只读工具**。

## 插件：`ci-perf`

自建 GitHub Actions runner 上的 CI 性能与可靠性手册。核心原则：**先测量，再优化；先只读审计，再动手；没有证据不下结论。**

| 技能 | 什么时候用 |
|---|---|
| `ci-perf-investigation` | CI 慢、排队久、要做性能优化：怎么取数据、看哪四张表、症状对应哪些原因、常见误判 |
| `self-hosted-runner-health` | 自建 runner 随机失败、磁盘写满、容器卷泄漏、缓存慢、想知道哪些任务消耗 GitHub 托管分钟 |
| `flaky-test-hunt` | 测试偶发失败、"测试全过但整体失败"、需要证明偶发问题已修复 |

附带的工具（只用标准库，只读）：

```bash
# 取数据并出报告：排队与运行、最慢步骤、PR 到必过检查的时间、按并发数分桶的耗时
python3 plugins/ci-perf/scripts/ci_timing.py collect --repo OWNER/NAME --workflow ci.yml --since 2026-09-01 --out runs.json
python3 plugins/ci-perf/scripts/ci_timing.py report runs.json --check "<必过检查 job>" --steps "<最慢 job>" \
    --overlap-target "<最重 job>" --heavy "<其他重 job,逗号分隔>"

# 哪些 job 跑在 GitHub 托管 runner 上（会消耗托管分钟）
python3 plugins/ci-perf/scripts/audit_runs_on.py <仓库目录>
```

模板（用 `on: push` 的临时分支运行，用完删除分支）：
- `skills/self-hosted-runner-health/templates/runner-readonly-audit.yml`：只读审计 runner 主机（磁盘、容器、卷）
- `skills/flaky-test-hunt/templates/repeat-tests.yml`：重复运行 N 次并保留每一轮完整日志

## 安装

```bash
claude plugin marketplace add <你的 GitHub 用户名>/claude-plugin-marketplace
claude plugin install ci-perf@dishangyijiao-plugins
```

本地试用（不安装）：`claude --plugin-dir plugins/ci-perf`

## 开发

```bash
python3 -m unittest discover -s tests     # 脚本逻辑 + 清单 + 隐私检查 + 模板只读检查
claude plugin validate .                  # 市场清单
claude plugin validate plugins/ci-perf    # 插件清单
claude plugin validate plugins/ci-perf/skills
```

`tests/test_repo_hygiene.py` 会拦截：内网 IP、令牌、密钥、个人邮箱、项目/主机名，以及审计模板里的任何删除类命令。**往这个仓库加内容之前先想：它是否通用、是否只读。**

## 发布

1. 在 GitHub 上建仓库 `claude-plugin-marketplace` 并推送。
2. 升版本：同时改 `plugins/ci-perf/.claude-plugin/plugin.json` 的 `version` 和（如有）市场条目。
3. `claude plugin tag plugins/ci-perf` 打 `ci-perf--vX.Y.Z` 标签（会校验两处版本一致），再推送标签。

## 还没做 / 已知局限

- 没有 `evals/`：可以用 `claude plugin eval` 对比"有插件 vs 无插件"来验证技能是否真的让排查更快，建议补上。
- 没有选择 LICENSE，发布前请自己定。
- `ci_timing.py` 通过 `gh api` 取数据：大仓库、大时间范围会比较慢，并受 API 限流影响。
- 经验来自自建 runner + Docker + pnpm + pytest xdist 这类组合；其他环境请把它当作清单而不是结论。
