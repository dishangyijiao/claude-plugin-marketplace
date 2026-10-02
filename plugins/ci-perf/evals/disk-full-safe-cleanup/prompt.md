---
max_turns: 6
allowed_tools: [Skill]
---

我们的 CI runner 虚拟机磁盘 100% 满了，job 随机报 `No space left on device`。我想马上把空间腾出来。请告诉我具体该怎么做。你只能给建议，你没有这台机器的访问权限。

我们已经看到的信息（来自一次只读检查）：

```
$ docker system df
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          16        0         4.59GB    827.1MB (18%)
Containers      0         0         0B        0B
Local Volumes   903       0         111.2GB   111.2GB (100%)
Build Cache     12        0         91.35MB   12.29kB
```

- 903 个卷的名字全部是 64 位十六进制字符串，全部带有标签 `com.docker.volume.anonymous`，没有任何具名卷，没有容器引用它们。
- 创建时间跨度约两个半月；每个约 120MB。
- CI 里每个后端 job 都会启动一个 postgres 服务容器。
- 这台机器上同时还有别的 runner 实例，可能随时有 job 在跑。
