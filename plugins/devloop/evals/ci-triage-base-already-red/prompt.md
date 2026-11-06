---
max_turns: 6
allowed_tools: [Skill]
---

后端 CI 报错了，看看原因。你不能运行命令，只根据下面的信息回答。

我的分支 `feat/export-csv` 改了 `reports/export.py`。失败的是 `lint` 这个 job：

```
reports/legacy.py:12:1: F401 'os' imported but unused
reports/legacy.py:57:5: E722 do not use bare 'except'
Found 2 errors.
```

补充信息：
- `reports/legacy.py` 不在我的 diff 里，我没碰过它。
- `main` 最近一次运行（昨天合并 #310 之后）的 `lint` job 也是红的，报同样两条错误。
- 另外还有两个同事的分支也在报同样的错。

请告诉我原因和怎么处理。
