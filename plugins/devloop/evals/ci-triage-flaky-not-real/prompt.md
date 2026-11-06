---
max_turns: 6
allowed_tools: [Skill]
---

CI 报错了，帮我看看。你不能运行命令，只根据下面的信息回答。

我这个 PR 只改了 `docs/setup.md` 和 `README.md`。失败的是 `unit-tests` 这个 job：

```
FAILED tests/test_scheduler.py::test_retry_after_timeout - AssertionError: assert 3 == 4
 1 failed, 812 passed in 214.33s
```

补充信息：
- 我点了 “Re-run failed jobs”，同一个提交上第二次是绿的。
- `main` 最近 10 次运行里，`test_scheduler.py::test_retry_after_timeout` 失败过 2 次，也都是重跑后变绿。
- 这个测试里有 `time.sleep(0.2)` 和对重试次数的断言。

请告诉我这是什么问题、我该怎么办。
