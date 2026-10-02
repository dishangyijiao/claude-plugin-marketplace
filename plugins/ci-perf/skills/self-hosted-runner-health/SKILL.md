---
name: self-hosted-runner-health
description: Use when self-hosted GitHub Actions runners fail randomly, run out of disk (No space left on device), leak Docker volumes, have slow dependency caching, or you need to audit which jobs consume GitHub-hosted minutes. 自建 runner 磁盘写满、容器卷泄漏、缓存慢、想知道哪些任务消耗托管分钟时使用。
---

# 自建 runner 健康：先只读审计，再决定动不动手

**原则：先只读，所有删除都由人执行。** 在共享机器上做批量删除是高风险操作，自动安全检查会拦截，也不应该尝试绕过。本 skill 只产出只读审计和"请人执行的命令"。

## 1. 没有登录权限也能审计：push 触发的临时 workflow

SSH 连不上、没有密码、没有 guest agent 时，让 runner **自己报告**。用 `templates/runner-readonly-audit.yml`：

- 它必须是 `on: push`（限定到一个临时分支）：`workflow_dispatch` 要求文件已经在默认分支上，而 push 触发的 workflow 可以直接从任意分支运行。
- 命令全部只读（`df`、`du`、`docker system df`、卷计数）。
- 用完**删除临时分支**。
- 推送前确认没有别的任务在跑（`gh run list --status in_progress`），避免占用别人的 runner；条件判断要真的看输出，不要无条件打印"空闲"。

## 2. 磁盘写满的头号嫌疑：容器匿名卷泄漏

典型成因：数据库镜像（如 postgres）声明了数据卷（`VOLUME`），而 runner 在 job 结束后删除服务容器时**不带 `-v`**，于是每个 job 遗留一个匿名卷。几百个 job 之后就是上百 GB。

审计要回答的几个问题（模板里都有）：
- `docker system df` 里 Local Volumes 的数量、大小、是否 100% 可回收；
- 卷名是否都是 64 位十六进制（匿名卷）、有没有具名卷、有没有容器引用它们；
- 创建时间范围（判断是从什么时候开始漏的）。

**根治（不是清理）：** 给服务容器的数据目录挂 tmpfs，docker 就不会再为它创建匿名卷：

```yaml
services:
  db:
    image: postgres:17
    # 注意：下面的 # 注释必须写在 options 上方。options 常用折叠字符串（>-），
    # 里面以 # 开头的行不是注释，会被当成 docker 参数传下去，直接弄坏服务。
    options: >-
      --health-cmd pg_isready
      --tmpfs /var/lib/postgresql/data:rw,size=1g
```

先用真实镜像在本机验证："`docker rm --force` 后不挂 tmpfs 遗留 1 个卷，挂了遗留 0 个"。

**一次性清理（给人执行，不要自动化）：** 只删"未被引用 + 64 位十六进制名 + 带匿名标签"三者同时满足的卷，先预检：

```bash
docker ps -q | wc -l        # 必须是 0
docker volume ls -q -f dangling=true -f label=com.docker.volume.anonymous | grep -E '^[0-9a-f]{64}$' | wc -l
# 数量符合预期后，由人执行删除，docker 会拒绝删除仍在使用的卷
```

## 3. 缓存：自建 / 国内 runner 上别用托管缓存服务

`actions/cache`（以及包管理器 action 的 `cache: true`）在 job **结束时**把存储上传到托管缓存服务。从自建或国内网络访问时极慢，且**每次锁文件变化、缓存未命中**就会触发一次，多个 job 同时上传，占着 runner 十几分钟。

做法：把存储放在 runner 本机的持久目录（如 `RUNNER_TOOL_CACHE` 下），并且：
- **按 runner 实例隔离**（用 `RUNNER_NAME` 的哈希做目录）：多个 runner 实例共用一个 home 时，共享存储会被并发 job 互相删除；
- **设容量上限**，超限就清空重来，避免撑满共享磁盘；
- 先写测试（持久、按实例隔离、超限重置、路径校验）。

## 4. 哪些 job 在消耗 GitHub 托管分钟

```bash
python3 scripts/audit_runs_on.py <仓库目录>
```

只做静态分析，不猜测：`github-hosted` / `self-hosted` / `dynamic`（表达式，需人工看）/ `reusable`（由被调用方决定）。**频率比标签重要**：每个 PR 都跑的托管 job，远比只在发布时跑的耗费多；每个 job 至少按 1 分钟计，被 `if:` 跳过的不计费。

## 5. 其他坑

- 多个 runner 实例共用一个 home 目录时，**任何共享的可写目录**（包管理器的安装目录、存储）都要按实例隔离。
- 提交时若报 `GH007: push would publish a private email address`，说明账号开启了邮箱隐私保护：只对这次提交改用账号的 noreply 邮箱，不要去改账号设置。
- 一个 runner 实例同一时刻只跑一个 job，没有并发参数；吞吐靠多实例，但实例数受宿主机 CPU 限制（见 `ci-perf-investigation`）。
