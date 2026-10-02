---
max_turns: 6
allowed_tools: [Skill]
---

每次依赖更新（锁文件变化）之后的那一次 CI，每个前端 job 都要多花十几分钟，其他时候一切正常。请解释原因并给出修复方案。只回答，不要修改任何文件。

背景：
- runner 是我们自建的，在国内网络环境，访问 GitHub 的缓存服务很慢。
- workflow 里用的是 `pnpm/action-setup`，配置了 `cache: true`。
- web、mobile、extension 三个 job 同时跑，每个占一个 runner 实例。
- **3 个 runner 实例共用同一台机器的同一个 home 目录。**
- 之前有过一次事故：共享的包管理器目录被并发的 job 互相删除，报 `ENOTEMPTY`。

下面是同一个 job 的步骤耗时（秒）：

锁文件没变（缓存命中）的运行：
```
Web unit tests            300
Install dependencies       24
Set up pnpm                 8
Post Set up pnpm           15
```

锁文件变化（缓存未命中）的运行：
```
Post Set up pnpm         1222
Web unit tests            302
Install dependencies       24
Set up pnpm                 8
```
