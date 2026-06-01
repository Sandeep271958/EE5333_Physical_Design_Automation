# A2 — Fiduccia–Mattheyses (FM) Partitioning

**File:** `EE22B045_A2.py`
**Task:** Complete `partitionFM(V, E, Amin, Amax)` — a 2-way netlist partitioner
that minimizes the **cut size** (number of nets crossing the boundary) while
keeping each side's total cell area within `[Amin, Amax]`.

Partitioning is the first step of physical design: split a large netlist into
two roughly balanced halves with as few connections between them as possible,
then recurse. FM is the classic linear-time-per-pass heuristic for this.

---

## Inputs and outputs

- `V` : dict `cell_name -> cell object` exposing `._area` and `._name`.
- `E` : dict `net_name -> list of pin objects`, each pin exposing `._name`
  (the cell it belongs to).
- `Amin`, `Amax` : lower/upper bounds on the area of **each** partition.
- **Returns** `(ans, total_cuts)` where `ans = [[cells in side 0], [cells in side 1]]`
  and `total_cuts` is the final cut size.

---

## Algorithm — the FM idea

FM improves a partition by repeatedly moving the single cell with the highest
**gain** (the reduction in cut size if that cell flips sides), with three twists
that let it escape local minima:

1. **Locking.** Each cell may move at most once per pass — once moved, it is
   locked. This prevents infinite ping-ponging.
2. **Allow non-improving moves.** Even moves with negative gain are taken, so the
   search can climb out of a local minimum.
3. **Best-prefix restoration.** Track the *cumulative* gain after each move; at
   the end of the pass, roll back to the prefix of moves that gave the **maximum
   cumulative gain**. Only the genuinely useful moves survive.

Passes repeat until a pass yields no positive best-cumulative-gain, at which
point the partition is a local optimum.

### Gain model used here
For a candidate cell on side `src` (moving to `dest`), over each net it touches:
- if the net currently has exactly **one** cell on `src` (the moving cell),
  moving it *removes* that net from `src` → **+1** gain;
- if the net currently has **zero** cells on `dest`, moving the cell *adds* the
  net to `dest` → **−1** gain.

This is the standard FM net-distribution gain (the net is uncut after the move
when it was cut before, and vice-versa), computed by `calc_gain`.

---

## Code walkthrough

1. **Adjacency build.** `adj[cell]` = list of nets that touch `cell`, for fast
   per-cell gain evaluation.
2. **Greedy initial partition.** Cells are sorted by area (largest first) and
   packed onto the lighter side that still fits under `Amax`. This gives a
   balanced, area-legal starting point.
3. **`get_net_distribution()`** → `dist[net] = [count_on_side0, count_on_side1]`.
   This is the quantity all gains are derived from.
4. **Pass loop** (`for _ in range(len(V))`):
   - Recompute `dist` and every cell's `gain`.
   - Maintain `area_tracker` = current area on each side.
   - **Inner move loop:** scan all unlocked cells, and among those whose move
     keeps both sides within `[Amin, Amax]`, pick the one with the highest gain.
     Execute the move, lock the cell, update `area_tracker`.
   - **Incremental gain update:** after moving a cell, update `dist` for its nets
     and recompute the gain of every unlocked cell on those nets (their gains may
     have changed).
   - Track `cum_gain`, remembering the `best_step` where `cum_gain` peaked.
   - **End of pass:** if no positive gain was found, undo every move and stop.
     Otherwise, **restore to the best prefix** by undoing all moves after
     `best_step`.
5. **Final cut count.** A net is cut iff its pins span both sides
   (`len({part[p] for p in net}) > 1`).

---

## Running it

`partitionFM` expects the `V`/`E` data structures from the course
[`FM_Partition.ipynb`](https://github.com/srini229/EE5333_tutorials/blob/master/part/FM_Partition.ipynb)
tutorial. Build small `V`/`E` dicts (cells with `._area`/`._name`, nets as pin
lists) to exercise it, then read back `ans` and `total_cuts`.

---

## Complexity & design notes

- **Area-aware move selection.** Standard textbook FM uses a balance *tolerance*;
  here the legality test is the hard interval `[Amin, Amax]` on both sides, which
  is checked before a move is ever considered the best — so the partition never
  leaves the legal region.
- **Gain maintenance.** Textbook FM keeps gains in **bucket lists** and applies
  $O(\text{pins})$ delta updates for an overall $O(\text{pins})$ pass. This
  implementation instead *recomputes* `calc_gain` for affected neighbours after
  each move. That is simpler and correct, but costs more per move; for the
  assignment's instance sizes it is perfectly fine. If you ever scale this up,
  the bucket-list + incremental-delta version is the speed win.
- **Best-prefix restoration** is the single most important detail for solution
  quality — without it, FM would keep the full (often worse) sequence of moves.
