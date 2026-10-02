---
max_turns: 6
allowed_tools: [Skill]
---

我们的后端 CI 太慢。团队提了两个方案，想请你判断哪个更好，或者两个都不好：

- 方案 A：再开 3 个 runner 实例，让更多任务并行。
- 方案 B：把每个 pytest 的 xdist worker 从 4 个调到 8 个。

请给出你的判断、理由和你建议的做法。只回答，不要修改任何文件。

我们从 GitHub Actions 采集的数据（pytest 步骤的耗时，按"同一时刻还有几个其他重任务在别的 runner 上运行"分组）：

```
== 'pytest' run time by number of other heavy jobs running at the same time
  0 neighbours: n= 10  median    522s  min    517s  max    857s
  1 neighbours: n=  5  median   1017s  min    649s  max   1076s
  2 neighbours: n=  5  median   1377s  min   1120s  max   1488s
  3 neighbours: n=  4  median   1160s  min   1059s  max   1439s
```

背景：目前有 3 个 runner 实例，全部在同一台虚拟机上（4 个 vCPU）。每个 pytest 任务用 4 个 worker 进程并行。同一台虚拟机上还有另外几个仓库的 runner，上面的"邻居"也把它们的重任务算进去了。
