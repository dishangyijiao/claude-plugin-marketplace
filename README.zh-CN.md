# claude-plugin-marketplace

[English](README.md) | 简体中文

个人的 Claude Code 插件市场，里面的插件都来自真实的工程实践，并且**只保留通用的方法和只读工具**。

## 插件：`ci-perf`

自建 GitHub Actions runner 上的 CI 性能与可靠性手册。核心原则：**先测量，再优化；先只读审计，再动手；没有证据不下结论。**

| 技能 | 什么时候用 |
|---|---|
| `ci-perf-investigation` | CI 慢、排队久、要做性能优化：怎么取数据、看哪四张表、症状对应哪些原因、常见误判 |
| `self-hosted-runner-health` | 自建 runner 随机失败、磁盘写满、容器卷泄漏、缓存慢、想知道哪些任务消耗 GitHub 托管分钟 |
| `flaky-test-hunt` | 测试偶发失败、"测试全过但整体失败"、需要证明偶发问题已修复 |

> 技能正文（`SKILL.md`）是中文写的；每个 `description` 是中英双语，用哪种语言提问都能触发。无论你用什么语言和 Claude 对话，它都会照着执行。

附带的工具（只用标准库，只读）：

```bash
# 取数据并出报告：排队与运行、最慢步骤、到必过检查的时间（从该次运行的第一个 job 创建，到检查完成）、
# 按并发数分桶的耗时。--steps 和 --heavy 可以填多个 job 名，用逗号分隔。
python3 plugins/ci-perf/scripts/ci_timing.py collect --repo OWNER/NAME --workflow ci.yml --since 2026-09-01 --out runs.json
python3 plugins/ci-perf/scripts/ci_timing.py report runs.json --check "<必过检查 job>" --steps "<最慢 job>" \
    --overlap-target "<最重 job>" --heavy "<其他重 job,逗号分隔>"

# 哪些 job 跑在 GitHub 托管 runner 上（会消耗托管分钟）
python3 plugins/ci-perf/scripts/audit_runs_on.py <仓库目录>
```

模板（用 `on: push` 的临时分支运行，用完删除分支）：
- `plugins/ci-perf/skills/self-hosted-runner-health/templates/runner-readonly-audit.yml`：只读审计 runner 主机（磁盘、容器、卷）
- `plugins/ci-perf/skills/flaky-test-hunt/templates/repeat-tests.yml`：重复运行 N 次并保留每一轮完整日志

## 插件：`source-of-truth`

让仓库成为系统"预期状态"的唯一事实来源的手册，覆盖九层工程：PRD、需求、ADR、架构、规格、代码、测试、部署、观测。核心原则：**每个事实只有一个权威来源；能用可执行的就不用文字；不编造缺失的决策；不适用的层写明原因，而不是塞占位文档。**

| 技能 | 什么时候用 |
|---|---|
| `source-of-truth:scaffold` | 新项目：先访谈，再只建适用的层，加上 `AGENTS.md` 和"事实在哪里"的对照表 |
| `source-of-truth:review` | 已有项目：只读地按九层审查，找出缺失、重复或冲突的来源，并给出一个小的第一步 |
| `source-of-truth:improve` | 审查之后：一次只补一个缺口（架构概览、ADR、需求、规格、契约、代理指令），一步可独立评审，不改变行为 |

自带文件：`reference/layers.md`（九层、三种适用状态、证据标签）、`reference/rules.md`（迁移规则、工作顺序、完成标准）、`templates/` 里的七份文档模板，以及一个只读、仅用标准库的链接检查脚本：

```bash
python3 plugins/source-of-truth/scripts/check_markdown_links.py <仓库目录>   # 退出码 0 正常，1 有失效链接，2 用法错误
```

**评测（6 个用例；最近一次完整运行每组 2 次，约 2.4 美元；追溯用例另外单独运行过，每组 4 次）：**

| 用例 | 装插件 | 不装 | 解读 |
|---|---|---|---|
| improve-accepted-adr-immutable | 1.00 | 1.00 | 模型本来就不会改写已接受的 ADR：没有测到收益 |
| improve-unknown-rationale | 1.00 | 1.00 | 模型本来就不会编造缺失的原因：没有测到收益 |
| scaffold-local-tool-not-applicable | 1.00 | 1.00 | 模型本来就会反对占位文档：没有测到收益 |
| unrelated-control | 1.00 | 1.00 | 没有干扰（之前的 0.50 来自评分标准里有歧义的一条，澄清后重跑） |
| review-readonly-report | 1.00 | 0.50 | 基线在第一次运行里是 1.00，所以在 n=2 时属于噪声 |
| improve-durable-traceability | 1.00 | 0.00 到 0.25 | 唯一有明显差距的用例，见下 |

`improve-durable-traceability` 是在源项目上真实运行 `improve` 之后写的：skill 自己的建议（"最小的一步"）让它把"防止需求 ID 腐烂的自动检查"推到了以后。用第一版 skill 时，这个用例装插件得 0.00、不装得 0.75（每组 4 次）：插件让回答变差了。给 `improve` 加上"追溯链接"一步之后，同一用例是 1.00 对 0.25（每组 4 次），完整运行里是 1.00 对 0.00。需要注意：评分标准是根据 skill 现在教的这条经验写的，所以它奖励的正是这一点；基线在三次运行里是 0.75、0.25、0.00，n=4 只是提示而不是测量；其他用例都没有显示收益。

**第一次真实使用：** 在这个插件所源自的仓库上只读运行了 `review`。它发现了两个真实问题（其中一个是当天早些时候自己误提交了编译产物，另一个是需求到测试完全没有 ID 追溯），其余多是复述一份已经存在的状态页，所以在一个已经走过这套流程的仓库上看不出多少价值；还没有在没走过这套流程的仓库上试过。**`review` 的对照实验（每组 1 次，同样的只读工具，2 个仓库）：** 不装插件的一组只被告知九层的名字，别的什么都没说。两组都没有明显胜出。装插件的一组对适用性判断更好（在个人 dotfiles 仓库上，它把 PRD 和需求判为可选、可观测判为不适用，并建议补 `AGENTS.md`；基线则要求新建带编号需求的范围文档），列出了读过的内容并标注了未知项。基线找到了更多具体的跨文档冲突，我核实后确认属实（远程仓库仍指向旧项目名、文件数量过期、架构页缺两个门禁、两份文档给出不同的应用顺序），因为它读的文件更多；装插件的一组读得少，漏掉了这些。装插件的一组发现了被误提交的一对 `.pyc`，基线没发现。所以测到的效果是更合适的分寸和对证据的诚实，而不是更多发现。插件带来的是一致性：每次都用同样的模板、适用状态和检查，这些用例没有测量这一点。

## 安装

```bash
claude plugin marketplace add dishangyijiao/claude-plugin-marketplace
claude plugin install ci-perf@dishangyijiao-plugins
claude plugin install source-of-truth@dishangyijiao-plugins
```

本地试用（不安装）：`claude --plugin-dir plugins/ci-perf` 或 `claude --plugin-dir plugins/source-of-truth`

## 开发

```bash
python3 -m unittest discover -s tests     # 脚本逻辑 + 清单 + 隐私检查 + 模板只读检查
python3 tools/mutate.py plugins/ci-perf/scripts/audit_runs_on.py --tests tests.test_audit_runs_on tests.test_properties   # 变异测试
claude plugin validate .                  # 市场清单
claude plugin validate plugins/ci-perf    # 插件清单
claude plugin validate plugins/ci-perf/skills
claude plugin validate plugins/source-of-truth
claude plugin validate plugins/source-of-truth/skills
```

`tests/test_repo_hygiene.py` 会拦截：内网 IP、令牌、密钥、个人邮箱、项目/主机名，以及审计模板里的任何删除类命令。**往这个仓库加内容之前先想：它是否通用、是否只读。**

## 评测（`claude plugin eval`）

`plugins/ci-perf/evals/` 里有 6 个用例，每个都自带数据（只允许 `Skill` 工具，不读文件、不联网），由 LLM 评分细则打分，并自动跑一个**不装插件的基线臂**做对照。

```bash
claude plugin eval plugins/ci-perf --runs 2 -j 2 --trust-plugin --no-publish --max-cost-usd 4
```

- 会用你自己的凭据起子进程；约 24 次运行、5 到 6 分钟、约 2.4 美元。`--no-publish` 让报告只留在本地，不发布到 claude.ai。
- `--trust-plugin` 只对你自己写的插件用。结果在 `evals*/results/`（已被 `.gitignore` 排除）。

**脚本用例单独放在 `evals-extra/`**：`run-timing-script` 要让代理真的运行插件里的脚本，需要授权 `Bash` 和 `Write`，所以不放进默认评测，避免没有授权时拉低成绩。它是**功能冒烟测试**（验证安装后脚本路径能被找到），**不是和基线比优劣**，基线没有这个脚本，预期就是 0 分：

```bash
claude plugin eval plugins/ci-perf --eval-dir evals-extra --allow-tools Bash Write --trust-plugin --no-publish --max-cost-usd 2
```

> 在我的机器上它**跑不起来**：授权 `Bash` 会触发沙箱安全检查，而 `~/.docker`（Docker 凭据存储）里有符号链接，评测框架会整体拒绝。所以我改用一次受限的非交互调用单独验证了两段：技能被触发后 `${CLAUDE_PLUGIN_ROOT}` 展开成真实路径；脚本在代理写出的数据上输出的报告与标准答案一致。**完整链路没有一次性跑通过。**

> 下面的结果是在评审修复**之前**测的（技能里加了示例、范围说明和安全提示；“到必过检查的时间”的标签和 contention 用例的题面也改了）。之后没有重新跑过评测。

**结果**（每臂 2 次，评分模型默认 haiku；样本很小，只能当线索。下面是瘦身之后的最新一次；括号里是瘦身之前）：

| 用例 | 有插件 | 无插件 | 解读 |
|---|---|---|---|
| contention-diagnosis | 1.00 | 1.00 | 基线已经会 → **没有价值证据**（改难后仍然如此） |
| disk-full-safe-cleanup | 1.00 | 1.00 | 基线已经安全 → **没有价值证据**（去掉引导后仍然如此） |
| unproven-fix-honesty | 1.00 | 1.00 | 基线顶住了"逼写已修复"的压力 → **没有价值证据** |
| unrelated-control（负向对照） | 1.00 | 1.00 | 插件没有干扰无关任务 |
| flaky-unhandled-after-teardown | 0.83（1.00） | 0.67 | 差在"验证方法"（确定性假定时器测试加重复运行统计）。**两次都没有调用技能**，差异很可能来自常驻的技能描述文字；瘦身时缩短了描述，差值从 +0.33 降到 +0.17，但 n=2，**分不清是瘦身还是噪声** |
| post-step-cache-upload | 1.00（1.00） | 0.67（0.50） | 基线各轮之间有波动（瘦身前 0.50，现在 0.67），n=2 时在噪声范围内；**有插件这一臂的提升部分是因为我把评分细则要的答案写进了技能，不算独立证据** |

总体：有插件 0.97、无插件约 0.89，平均差值 +0.08（瘦身前 +0.14）。**只有"方法类"的场景（偶发失败的验证、缓存保存与实例隔离）显示出差异；对模型本来就懂的常识（别在同一台机器上加 runner、删卷前先检查、不夸大未证实的修复），没有测出价值。**

**成本**：`claude plugin details` 报告常驻约 157 token，每个技能被触发时约 0.4 到 0.6k token（三个都触发约 1.5k）。之前瘦身那一轮记录的 312 / 425 / 5.7k / 3.9k 来自另一种测法，我复现不出来，所以只有同一工具测出的数字才能互相比较。评审修复之后技能略有变长（加了示例和安全提示）。

已知偏差与缺口：
- 评分细则是照技能内容写的（"出题人就是教材作者"）；多条件的 PASS 规则交给小模型判，最终跑分建议加 `--judge-model` 换更强的模型并抽样人工核对。
- 只有 2 次/臂，且结论只针对这一个模型；随着模型变强，基线分数会继续上升，这些"差值"可能缩小。
- 没有评分项检查"技能是否被触发"，所以技能的触发表现不计入分数。

## 安全说明

- job 名、步骤名和 workflow 文件都出自能改 workflow 的人，不可信。脚本在打印前会替换控制字符、双向覆盖字符、零宽字符和行分隔符，`ci_timing.py` 在调用 `gh api` 之前校验 `--repo` 和 `--workflow`，`audit_runs_on.py` 会跳过符号链接的 workflow 文件，技能也会提示代理把这类文字当数据。
- 两个 workflow 模板只用于**私有仓库**，且只在你愿意运行该代码的 runner 上跑。把它们推到自建 runner 之前需要用户确认；`repeat-tests.yml` 里的测试与准备命令必须来自项目负责人，不能取自 CI 日志。
- 模板里的 GitHub Actions 固定到了提交 SHA，`__RUNS__` 会按整数校验，把测试输出或目录名回显进日志时，会转义以 `::` 开头的行。
- 技能没有设置 `allowed-tools`：在 Claude Code 里这个字段是预先授权工具，不是限制工具。

## 发布

1. 升版本：同时改 `plugins/ci-perf/.claude-plugin/plugin.json` 的 `version` 和（如有）市场条目。
2. `claude plugin tag plugins/ci-perf` 打 `ci-perf--vX.Y.Z` 标签（会校验两处版本一致），再推送标签。

当前版本：`ci-perf--v0.1.4`。

## 还没做 / 已知局限

- 评测结果见上一节：只有部分场景显示出收益，且评分细则有已知偏差和缺口；脚本用例在部分机器上无法用评测框架运行。
- `ci_timing.py` 通过 `gh api` 取数据（每个 run 一次请求），按需翻页、够数就停；仍会受 API 限流影响。并发分析只看得到你采集的 job，详见 `ci-perf-investigation` 的“工具局限”一节。
- `audit_runs_on.py` 是逐行读取而不是 YAML 解析器，只支持块风格的 `jobs:`。
- 经验来自自建 runner + Docker + pnpm + pytest xdist 这类组合；其他环境请把它当作清单而不是结论。

## 许可

MIT，见 `LICENSE`。
