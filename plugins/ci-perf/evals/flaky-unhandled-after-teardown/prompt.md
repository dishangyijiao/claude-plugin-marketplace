---
max_turns: 6
allowed_tools: [Skill]
---

我们的前端单元测试在 CI 里大约每 4 次运行就有 1 次整体失败，本机几乎不复现。团队打算：先把失败的 job 重跑，或者把测试超时调大。请告诉我最简单且正确的修法。只回答，不要修改任何文件。

失败运行的日志末尾（所有测试其实都通过了）：

```
 Test Files  755 passed (755)
      Tests  6464 passed (6464)
     Errors  1 error

⎯⎯⎯⎯⎯⎯ Unhandled Errors ⎯⎯⎯⎯⎯⎯
ReferenceError: window is not defined
 ❯ resolveUpdatePriority  react-dom-client.development.js:1308:7
 ❯ dispatchSetState       react-dom-client.development.js:9126:14
 ❯ Timeout._onTimeout     components/reactions/picker.tsx:74:43
     72|   // 鼠标离开区域后延迟关闭
     73|   const scheduleClose = () => {
     74|     closeTimer.current = setTimeout(() => setOpen(false), 200);
     75|   };
```

补充信息：这个组件的外层容器和里面的气泡**两个元素都绑定了 `onMouseLeave={scheduleClose}`**，鼠标从气泡移出到组件外时两个处理函数都会触发。组件里没有任何卸载时的清理逻辑。
