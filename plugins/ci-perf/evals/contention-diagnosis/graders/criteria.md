---
type: llm
weight: 2
---

You are grading an engineering recommendation. The user asked whether adding more CI runner instances (all on the same 4-vCPU VM) will speed up CI, and gave a table: the same job takes about 522s alone, about 1017s with 1 concurrent neighbour, about 1377s with 2 and about 1160 to 1439s with 3.

PASS only if ALL of the following hold:
1. It concludes that adding more runner instances on the same VM will NOT help (or will likely make things worse), and bases that on the table, i.e. the same job gets much slower when other heavy jobs run at the same time.
2. It attributes the slowdown to contention for shared resources on the one host (CPU, and possibly disk or memory), not to the tests themselves being slow.
3. It recommends giving the VM more CPU (vCPUs) or otherwise increasing the host's capacity, or reducing per-job CPU demand, as the lever. Recommending more runner instances on the same VM as the fix is a FAIL.
4. It says to check that the host actually has spare CPU before adding vCPUs (the user said it does, so confirming this is a quick check, not a blocker).

FAIL if it recommends adding runner instances, if it ignores the table, or if its main advice is unrelated to host capacity (for example only caching, only parallelizing tests further, or only upgrading the test framework).
