# A1 — ILP Formulations for Graph Problems

**File:** `EE22B045_A1.py`
**Task:** Formulate two classic graph problems as Integer Linear Programs (ILPs)
and solve them with the `mip` library.
**Constraint:** only `mip` may be imported — no other third-party modules.

The two problems are **Minimum Dominating Set (MDS)** and **Maximum-Weight
Independent Set (MWIS)**.

---

## 1. Minimum Dominating Set — `mds(N, E)`

### Problem
Given an undirected graph $G=(V,E)$ with $|V| = N$, find the smallest set of
vertices $D \subseteq V$ such that every vertex is either in $D$ or adjacent to a
vertex in $D$. (Every vertex is "dominated.")

### ILP formulation
Binary variable $x_i = 1$ iff vertex $i$ is chosen.

$$\min \sum_{i\in V} x_i$$

subject to, for every vertex $i$:

$$x_i + \sum_{j \in N(i)} x_j \ge 1, \qquad x_i \in \{0,1\}$$

The constraint says: vertex $i$ is covered either by itself ($x_i$) or by at
least one neighbour. Minimizing the sum picks the fewest such vertices.

### How the code implements it
1. **Adjacency list.** `adj[u]` collects every neighbour of `u` from the edge
   list (each edge added in both directions).
2. **Variables.** One binary var `x_i` per vertex via `model.add_var(var_type=mip.BINARY)`.
3. **Objective.** `mip.minimize(mip.xsum(x))` — minimize the count of chosen vertices.
4. **Constraints.** For each `i`, `x[i] + xsum(x[neighbor] for neighbor in adj[i]) >= 1`.
5. **Solve & extract.** `model.optimize()`, then return every `i` with `x[i].x > 0.9`
   (the `0.9` threshold guards against floating-point fuzz around the integer 1).

`model.verbose = 0` silences CBC's console output (autograders dislike stray prints),
and `model.write('dominating_set.lp')` dumps the LP for inspection/debugging.

---

## 2. Maximum-Weight Independent Set — `mwis(N, E, W)`

### Problem
Given $G=(V,E)$ and a weight $w_i$ per vertex, find an **independent set** (no two
chosen vertices share an edge) of maximum total weight.

### ILP formulation
Binary $x_i = 1$ iff vertex $i$ is in the set.

$$\max \sum_{i \in V} w_i\, x_i$$

subject to, for every edge $(u,v) \in E$:

$$x_u + x_v \le 1, \qquad x_i \in \{0,1\}$$

The edge constraint forbids picking both endpoints of any edge, which is exactly
the independence requirement. Maximizing weight selects the best such set.

### How the code implements it
1. **Variables.** One binary var per vertex.
2. **Objective.** `mip.maximize(mip.xsum(x[i]*W[i] for i in range(N)))`.
3. **Constraints.** For each edge `(u, v)`: `x[u] + x[v] <= 1`.
4. **Solve & extract.** Collect `Selected_vertices = [i for i in range(N) if x[i].x > 0.9]`,
   compute `Total_weight`, and return the pair `(Selected_vertices, Total_weight)`.

---

## Running it

```python
from EE22B045_A1 import mds, mwis

# Example graph: path 0-1-2-3
N = 4
E = [(0,1), (1,2), (2,3)]

print(mds(N, E))                  # a minimum dominating set, e.g. [1, 2]
print(mwis(N, E, [3, 1, 1, 3]))   # ([0, 3], 6) — pick the two heavy endpoints
```

Both functions return `[]` / `[[], 0]` if the solver does not reach an optimal
status (e.g. an infeasible or unbounded model).

---

## Why this assignment matters

MDS and MWIS are both **NP-hard**. Writing them as ILPs is the standard way to
get *provably optimal* answers on instances small enough to solve, and it is the
modelling skill that underlies a lot of EDA: many placement, partitioning, and
routing sub-problems are first expressed as integer programs before a heuristic
is reached for. CBC (the engine behind `mip`) solves these with **branch and
bound over an LP relaxation** — which is exactly what assignment **A6** rebuilds
by hand. Treat A1 as "use the solver" and A6 as "be the solver."

---

## Notes & caveats

- **Function naming.** The course brief refers to the second function as
  `mdis`; this implementation names it `mwis` (Maximum-Weight Independent Set).
  If an autograder imports `mdis`, add an alias: `mdis = mwis`.
- **Return-type consistency (MWIS).** On success the function returns a tuple
  `(list, weight)`; on the non-optimal path it returns a list `[[], 0]`. A
  caller that unpacks `vertices, weight = mwis(...)` works in both cases, but the
  types differ slightly — worth tidying to always return a tuple.
- **The `0.9` rounding threshold** is the idiomatic way to read binary ILP
  results back out of a float solver; don't compare `== 1.0`.
- **`.lp` side files.** `dominating_set.lp` / `weight_independent_set.lp` are
  written on every call; harmless, but you can remove the `model.write(...)`
  lines for a clean submission.
