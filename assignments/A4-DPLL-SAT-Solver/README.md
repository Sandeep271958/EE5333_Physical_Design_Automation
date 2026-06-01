# A4 — DPLL SAT Solver

**File:** `EE22B045_A4.py`
**Task:** Complete a **DPLL** (Davis–Putnam–Logemann–Loveland) implementation that
decides Boolean satisfiability and returns a satisfying assignment.

SAT is the canonical NP-complete problem and a workhorse inside EDA — equivalence
checking, ATPG, timing/constraint solving, and more all reduce to it. DPLL is the
backtracking-search backbone that every modern CDCL SAT solver extends.

---

## Input format (DIMACS CNF)

A CNF formula in conjunctive normal form: an AND of clauses, each clause an OR of
literals. A literal is a variable (`3`) or its negation (`-3`). `loadCNFFile`
parses the standard DIMACS `.cnf`:

```
p cnf <num_vars> <num_clauses>
1 -3 4 0      ← clause (x1 OR ¬x3 OR x4), 0 terminates the line
...
```

Assignments are stored in a list `m` indexed by variable number (1-based);
`m[i]` is `True`, `False`, or `None` (undecided).

---

## The `Clause` class — three-valued evaluation

Each clause caches which of its literals are still "active" and what the clause
currently evaluates to:

- **`eval(m)`** → `True` if any literal is already satisfied, `False` if all
  literals are assigned and none satisfies it (a conflict), `None` if it is still
  undecided (has unassigned literals). This three-valued logic is what lets DPLL
  detect a unit clause, a satisfied clause, and a conflict uniformly.
- **`propagate(m)`** recomputes the active-literal mask `_vact`, the active count
  `_nact`, and the cached value `_val` under the current assignment.
- **`getUnitVal()`** returns the single remaining literal when `_nact == 1` (the
  literal that *must* be true for the clause to be satisfiable).

---

## The two inference rules

**Unit propagation** (`unitClauses`): a clause with exactly one active literal
forces that literal's value. The code finds unit clauses, assigns the forced
literal, re-propagates every clause, and repeats until no unit clauses remain.
This is the single most powerful and cheap inference in DPLL.

**Pure-literal elimination** (`pureLiterals`): a variable that appears with only
one polarity across all still-unsatisfied clauses can be assigned that polarity
with no risk — it can only help. The code assigns pures, re-propagates, and
repeats.

---

## `dpll(f, m)` — the recursive search

1. Propagate all clauses under the current assignment `mc`.
2. **Unit-propagation loop** until no unit clauses remain.
3. **Pure-literal loop** until no pures remain.
4. **Terminate?**
   - any clause `False` → return `(False, None)` (conflict, backtrack);
   - all clauses `True` → return `(True, mc)` (solution found).
5. **Branch.** Pick an unassigned variable (`pickBranchingLiteral` takes the
   first one), try it `True` and recurse; if that fails, try it `False` and
   recurse. This is the depth-first backtracking that gives DPLL its
   completeness.

Each branch works on a *copy* of the assignment list, so a failed branch leaves
the caller's state intact.

---

## Running it

```bash
python EE22B045_A4.py -c uf20-01.cnf
```

- **Satisfiable** → prints the assignment as signed literals, e.g.
  `[1, -2, 3, 4, ...]` (positive = true, negative = false).
- **Unsatisfiable** → prints `UNSATISFIABLE`.

Test instances live in the course tutorials repo:
<https://github.com/srini229/EE5333_tutorials/tree/master/misc>

---

## Complexity & design notes

- **Worst case is exponential** — that's inherent to SAT. Unit propagation and
  pure-literal elimination prune enormous swaths of the tree in practice, which
  is why even this basic DPLL solves the sample 20–50 variable instances quickly.
- **Branching heuristic.** `pickBranchingLiteral` just takes the first
  unassigned variable. Smarter heuristics (e.g. most-frequent literal, Jeroslow–
  Wang, or the activity-based **VSIDS** that CDCL solvers use) cut the search
  dramatically — a natural extension.
- **What this DPLL omits vs. modern solvers.** No clause learning, no
  non-chronological backjumping, no watched-literals. Adding conflict-driven
  clause learning (CDCL) is the standard next step.
- **Parser assumption.** `loadCNFFile` asserts each clause has three literals
  (3-SAT). Generalize the assertion if you feed it arbitrary CNF.
- **Output guard.** The CLI wraps the print in a satisfiability check so it never
  crashes on an UNSAT instance when run under an autograder.
