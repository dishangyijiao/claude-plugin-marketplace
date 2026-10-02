---
type: llm
weight: 2
---

You are grading an engineering recommendation. The team proposed (A) adding 3 more runner instances on the same 4-vCPU VM, or (B) raising each pytest's worker count from 4 to 8. The data: the same job takes about 522s alone, about 1017s with 1 concurrent neighbour, about 1377s with 2, and about 1160 to 1439s with 3.

PASS only if ALL of the following hold:
1. It concludes that NEITHER A nor B will help (they would increase demand on the same 4 vCPUs and likely make things worse).
2. It bases that on the table: the same job gets roughly 2 to 3 times slower when other heavy jobs run at the same time.
3. It notices that running jobs concurrently barely improves total throughput: three jobs at roughly 1100 to 1400s each in parallel is about the same as running three jobs one after another at about 522s each (about 1566s), so the host is already saturated.
4. It recommends increasing the host's capacity (more vCPUs) or reducing per-job CPU work as the lever, and it does NOT assume the host has spare capacity without evidence: it says to check actual host utilization (for example CPU load, steal, or whether the hypervisor has idle cores) before changing capacity.

FAIL if it recommends A or B, if it ignores the table, or if it asserts that spare capacity exists without any check.
