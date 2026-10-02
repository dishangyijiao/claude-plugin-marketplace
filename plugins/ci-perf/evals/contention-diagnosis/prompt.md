---
max_turns: 6
allowed_tools: [Skill]
---

我们的后端 CI 太慢了，想再多开几个 runner 实例让任务并行。请先判断这样做是否有用，给出你的建议和理由。只回答，不要修改任何文件。

下面是我们从 GitHub Actions 采集的数据（pytest 步骤的耗时，按"同一时刻还有几个其他重任务在别的 runner 上运行"分组）：

```
== 'pytest' run time by number of other heavy jobs running at the same time
  0 neighbours: n= 10  median    522s  min    517s  max    857s
  1 neighbours: n=  5  median   1017s  min    649s  max   1076s
  2 neighbours: n=  5  median   1377s  min   1120s  max   1488s
  3 neighbours: n=  4  median   1160s  min   1059s  max   1439s
```

背景：目前有 3 个 runner 实例，全部在同一台虚拟机上（4 个 vCPU，宿主机还有很多空闲 CPU）。每个 pytest 任务用 4 个 worker 进程并行。
