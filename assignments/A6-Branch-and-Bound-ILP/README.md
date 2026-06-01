# A6 — Branch-and-Bound ILP Solver (Simplex + B&B)

**File:** `EE22B045_A6.py`
**Task:** Using the provided template **simplex** routine, implement
**branch-and-bound** to find the optimal solution and objective of an Integer
Linear Program. All variables are integers; constraints are inequalities; slack
variables introduced to reach standard form need not be integers.

This is the "be the solver" companion to **A1**: there you handed an ILP to `mip`;
here you build the engine — LP relaxation by simplex, then branch-and-bound to
force integrality.

---

## How an ILP is solved by branch and bound

1. **Relax** the integrality requirement and solve the resulting LP with simplex.
   The LP optimum is an **upper bound** on the (maximization) ILP optimum.
2. If the relaxed solution is already integer, it is optimal for the ILP — done.
3. Otherwise pick a variable $x_k$ with a fractional value $v$ and **branch** into
   two sub-problems:
   - $x_k \le \lfloor v \rfloor$
   - $x_k \ge \lceil v \rceil$
   This carves the fractional point out of the feasible region without losing any
   integer point.
4. **Bound / prune.** Keep the best integer solution found so far (the
   *incumbent*). Any sub-problem whose LP bound is no better than the incumbent
   can be discarded unexplored.
5. Recurse until the tree is exhausted; the incumbent is the ILP optimum.

---

## The simplex routine (template)

`simplex(m, obj)` solves a standard-form LP:

- Builds the tableau `A`, right-hand side `b`, and cost row `c` from a `mip`
  model's variables and constraints, adding one **slack variable** per inequality
  so every constraint becomes an equality.
- Iterates while any reduced cost `c > 0`: choose an entering column
  (`argmax c > 0`), choose the leaving row by the **min-ratio test**
  (`b[i]/A[i][pivot]` over rows with positive pivot entry), pivot, and update the
  basic solution.
- Returns `(sol, -f)` — the variable values and the optimized objective.

`print_tableau` dumps the tableau each iteration for debugging.

---

## The branch-and-bound layer (the assignment)

The interesting design choice here is that each B&B node is rebuilt as a fresh
`mip` model so the **same** `simplex` routine can solve it unchanged:

- **`_make_node(extra_constrs)`** clones the original model's variables, objective,
  and constraints, then appends the branch constraints (`x_k <= floor` or
  `x_k >= ceil`) collected along the current path. It returns a model + objective
  that `simplex` understands.
- **`is_sol_integer(sol, Nvar)`** checks whether the first `Nvar` (original)
  variables are within `eps` of an integer. **Slack variables are not checked** —
  per the assignment, they may be fractional.
- **`_check_feasibility(sol, m_node, Nvar)`** rejects solutions with negative
  variables or any violated constraint (a guard, since re-solved nodes can return
  edge-case points).
- **`_bnb(extra_constrs)`** is the recursion:
  1. solve the node LP with `simplex`;
  2. drop it if infeasible;
  3. **prune** if its objective `f <= best_f + eps` (cannot beat the incumbent);
  4. if integer, **update the incumbent** (`best_sol`, `best_f`) and return;
  5. else pick the first fractional variable, branch into `floor` and `ceil`
     children, and recurse.
- **`solve_ilp(m, obj)`** kicks off `_bnb([])` and returns the best integer
  solution and its objective. The incumbent is held in single-element lists
  (`best_sol`, `best_f`) so the nested function can mutate them — a Python
  closure idiom that stands in for a mutable reference.

---

## Running it

```bash
python EE22B045_A6.py
```

The file contains two test ILPs and, for each, prints **both** the
branch-and-bound result and `mip`'s own optimizer result so you can confirm they
agree:

```
# Test 1
maximize x0 + x1
  x0 + 3·x1 ≤ 9.2
  2·x0 + x1 ≤ 8.4

# Test 2
maximize 6·x0 + x1
  9·x0 +   x1 +  x2 ≤ 18.4
  24·x0 +  x1 + 4·x2 ≤ 42.3
  12·x0 + 3·x1 + 4·x2 ≤ 96.5
```

The B&B `sol` and objective should match `m.optimize()`'s `[v.x for v in m.vars]`
and `m.objective.x`.

---

## Design notes & caveats

- **Maximization, depth-first.** The search is DFS with incumbent-based pruning.
  A best-first (priority-queue on LP bound) order can find a good incumbent sooner
  and prune more, at the cost of more bookkeeping.
- **Rebuilding nodes is clean but not the fastest.** Reconstructing a `mip` model
  per node keeps `simplex` untouched and the logic readable. Production solvers
  instead **warm-start** the dual simplex from the parent's basis. For the
  assignment's tiny problems, the clarity is worth more than the speed.
- **`eps = 1e-6`** is used consistently for "is this an integer?" and
  bound/feasibility comparisons — the right way to handle floating-point output
  from a numerical LP solver.
- **Ties the course together.** Simplex + branch-and-bound is exactly the engine
  CBC runs underneath `mip` in **A1**. Having built it here, the A1 black box is
  no longer a black box.
