# A3 — Floorplanning with Sequence Pairs + Simulated Annealing

**File:** `ee22b045_A3.py`
**Task:** Given modules with an area and a set of allowed aspect ratios, find a
floorplan that **minimizes the area of the tightest bounding box** enclosing all
modules. Use a **sequence-pair** representation and **simulated annealing** to
reach a local optimum.

Floorplanning fixes the relative positions and shapes of large blocks early in
the flow. The sequence pair is a compact, well-studied encoding of a
non-overlapping packing, and simulated annealing is the textbook way to search
its huge discrete solution space.

---

## Representation

### `Module`
Holds a name, an area, and the list of legal **(width, height)** pairs derived
from the allowed aspect ratios:

```python
self._wh = [(sqrt(area * r), sqrt(area / r)) for r in aspect_ratios]
```

so each ratio `r` gives a shape with that width:height while preserving area.

### `SeqPair` — the encoding
A sequence pair is **two orderings** of the modules:

- `_pos` — the positive sequence
- `_neg` — the negative sequence
- `_ap[i]` — which aspect-ratio choice module `i` currently uses
- `_coords`, `_w`, `_h` — filled in by `costEval`

The two sequences encode *all* the relative-position constraints. For modules
A and B:

| Relation in (pos, neg) | Geometric meaning |
|---|---|
| A before B in **both** | A is **left of** B |
| A after B in **both** | A is **right of** B |
| A before B in pos, after in neg | A is **above** B |
| A after B in pos, before in neg | A is **below** B |

Every pair of modules falls into exactly one case, which guarantees a
non-overlapping placement.

---

## `costEval` — decoding a sequence pair to coordinates

The cost is the bounding-box area, obtained by computing each module's lower-left
corner from the two longest-path constraint graphs:

- **X coordinates (Horizontal Constraint Graph).** For modules `A` (at position
  `i` in `pos`) and `B` (at `j > i` in `pos`): if `A` also precedes `B` in `neg`,
  then `A` is left of `B`, so
  `X[B] = max(X[B], X[A] + W[A])`.
- **Y coordinates (Vertical Constraint Graph).** For modules `A` (at `i` in `neg`)
  and `B` (at `j > i` in `neg`): if `A` comes *after* `B` in `pos`, then `A` is
  below `B`, so
  `Y[B] = max(Y[B], Y[A] + H[A])`.

The floorplan width/height are then
`W_fp = max(X[i] + W[i])` and `H_fp = max(Y[i] + H[i])`, and the returned cost is
`W_fp * H_fp`.

---

## `perturb` — moving through the search space

A copy of the current sequence pair is made (via the `[:]` deep-copy hook,
`__getitem__`) and **one** of four moves is applied at random:

1. swap two modules in `_pos`
2. swap two modules in `_neg`
3. swap the same pair in **both** sequences
4. change one module's **aspect-ratio** choice (`_ap[i]`)

Moves 1–3 re-order blocks; move 4 reshapes a block. Together they make the
search ergodic over both topology and shape.

---

## Simulated annealing

```python
def accept(delC, T):
    if delC <= 0: return True            # always accept improvements
    return random.random() < exp(-delC/T) # accept worsening moves with prob e^(-ΔC/T)
```

- Start hot (`Tmax = total module area`), so almost anything is accepted and the
  search explores widely.
- At each temperature, attempt `N` perturbations.
- Cool geometrically: `T = T * alpha` (here `alpha = 0.9`).
- Track the best `(minS, minC)` seen and return it.

`sp_floorplan(modules)` wires this together: build an initial `SeqPair`, set
`Tmax` to the summed area, anneal from `Tmax` down to `1`, and return the placed
solution plus its area.

The example calls report **utilisation** = (sum of module areas) / (bounding-box
area) × 100% — the headline quality number for a floorplan.

---

## Running it

```bash
python ee22b045_A3.py
```

The file includes two demos: ten random unit-aspect modules, and four modules
with multiple aspect ratios. Un-comment the `plot(sol)` calls to see the packed
floorplan (requires `matplotlib`).

---

## Complexity & design notes

- **`costEval` cost.** The X/Y passes call `self._neg.index(...)` /
  `self._pos.index(...)` inside an $O(n^2)$ double loop, making each evaluation
  roughly $O(n^3)$. Fine for the assignment's small block counts; for large
  instances, precompute a `position[module] = index` map once per evaluation to
  drop it to $O(n^2)$. (A further classic speed-up is the $O(n\log n)$
  longest-common-subsequence decoding, but it is not needed here.)
- **The `[:]` copy.** `__getitem__` is overloaded so `S[:]` returns a *fresh
  deep copy* of the sequence pair. This matters: `perturb` must not mutate the
  current state in place, or the annealing accept/reject logic breaks.
- **Cooling schedule.** `alpha = 0.9` with `N = 100` inner iterations is a
  reasonable default; raising `N` or `alpha` trades runtime for slightly better
  area.
