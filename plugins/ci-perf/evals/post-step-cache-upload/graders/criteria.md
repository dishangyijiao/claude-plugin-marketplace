---
type: llm
weight: 2
---

You are grading a diagnosis and fix for a CI slowdown. In the data, a "Post Set up pnpm" step takes about 1222s only when the lockfile changed (cache miss) and about 15s otherwise; the runners are self-hosted, on a network where GitHub's hosted cache service is slow, and three runner instances share one home directory (a shared package-manager directory was once corrupted by concurrent jobs).

PASS only if ALL of the following hold:
1. It identifies the Post step as the cache SAVE (uploading the package store to GitHub's hosted cache service) that only happens on a cache miss, and that this upload is what is slow from this network. Blaming the tests, the install step or CPU is a FAIL.
2. It proposes keeping the package-manager store on the runner's own local disk, persistent across jobs (for example under the runner tool cache), instead of the hosted cache service.
3. It makes the local store private to each runner instance (for example keyed by the runner name), explicitly because the instances share a home directory and a shared store was already corrupted by concurrent jobs.
4. It mentions a size limit or cleanup rule so a persistent store cannot fill the shared disk.

FAIL if it only suggests adding CPU or runners, only disables caching altogether with no local persistent store, or proposes one shared directory for all instances.
