# A5 — Attributed Graph Isomorphism (VF2)

**File:** `EE22B045_A5.py`
**Task:** Given two undirected, attributed graphs `G` and `H` with `|V_G| = |V_H|`
and `|E_G| = |E_H|`, decide whether they are **isomorphic** and, if so, return a
bijection `f : V_G → V_H` that preserves both **edges** and **vertex attributes**.

Formally, $f$ must satisfy
$$\forall u,v \in V_G:\ (u,v)\in E_G \iff (f(u),f(v))\in E_H$$
and `attr(u) == attr(f(u))` for every vertex.

Graph isomorphism shows up in physical design as **layout-versus-schematic
(LVS)** and netlist/cell matching — deciding whether two structural descriptions
are the same up to relabelling. The attribute check models matching like with
like (e.g. a NAND only maps to a NAND).

---

## Input / output format

- A graph is `([list of vertex attributes], [list of edges])`, vertices labelled
  `0 .. N-1`, edges as unordered pairs.
- `isomorphism(G, H)` returns a list `mapping` where `mapping[i]` is the vertex of
  `H` that `G`'s vertex `i` maps to — or `None` if the graphs are not isomorphic.

```python
G = ([0, 1, 0, 2, 2], [(0, 2), (0, 3), (1, 3), (1, 4), (2, 4)])
H = ([0, 0, 2, 1, 2], [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)])
isomorphism(G, H)   # e.g. [0, 3, 1, 4, 2]
```

---

## Algorithm — VF2-style backtracking with pruning

The solver grows a partial mapping one vertex at a time, backtracking whenever
the partial mapping cannot be extended consistently. Three checks keep the search
small:

1. **Cheap global rejects** (`isomorphism`): if the graphs differ in vertex count
   or edge count, return `None` immediately.
2. **Candidate filtering** (`get_candidates`): a `G`-vertex can only map to an
   `H`-vertex with the **same attribute**, the **same degree**, and not already
   used. This prunes most of the branching factor before any recursion.
3. **Feasibility / consistency** (`feasibility`): before committing
   `g_node → h_node`, verify the partial mapping stays edge-consistent in **both
   directions** —
   - every already-mapped neighbour of `g_node` must map to a neighbour of
     `h_node`, and
   - every already-mapped neighbour of `h_node` must come from a neighbour of
     `g_node`.

If both directions hold, the pair is added; otherwise it is rejected.

---

## Code walkthrough

- **`build_graph(G)`** → `(attr, neighbors)`: an attribute dict and a dict of
  neighbour **sets** (sets give $O(1)$ adjacency tests, which `feasibility`
  leans on).
- **`get_candidates(g_node, …)`** returns the `H`-vertices that match `g_node` on
  attribute and degree and aren't taken yet.
- **`feasibility(g_node, h_node, mapping, …)`** does the two-directional
  edge-consistency check described above. It builds the reverse map on the fly to
  check `h_node`'s side.
- **`vf2(g_order, idx, mapping, …)`** is the recursion: at depth `idx`, take the
  next `G`-vertex, try each feasible candidate, recurse, and **backtrack**
  (`del mapping[g_node]`) on failure. When `idx == len(g_order)`, a complete
  consistent mapping has been found.
- **`isomorphism(G, H)`** runs the global rejects, builds both graphs, calls
  `vf2` over the vertex order `0 .. N-1`, and reformats the result dict into the
  required ordered list.

---

## Running it

```python
from EE22B045_A5 import isomorphism

# Isomorphic example → prints a valid mapping
print(isomorphism(
    ([0, 1, 0, 2, 2], [(0, 2), (0, 3), (1, 3), (1, 4), (2, 4)]),
    ([0, 0, 2, 1, 2], [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)])))

# Non-isomorphic example → prints None
print(isomorphism(
    ([0, 1, 0, 1, 0, 1], [(0,1),(1,2),(2,3),(3,4),(4,5),(5,0)]),
    ([1, 0, 1, 0, 1, 0], [(0,1),(1,2),(2,0),(3,4),(4,5),(5,3)])))
```

---

## Complexity & design notes

- **Worst case is factorial**, but in practice the attribute + degree filtering
  and the two-way feasibility check collapse the search tree quickly. On the
  second example above, the degree/attribute structure makes the graphs
  unmatchable almost immediately.
- **Vertex ordering matters.** The recursion processes `G`'s vertices in plain
  numeric order. The real VF2 picks the next vertex to be one *adjacent to the
  already-mapped set* (and, among those, the most constrained), which keeps the
  partial mapping connected and prunes earlier. That ordering is the main
  available speed-up.
- **An interesting theory aside:** unlike A1/A4/A6's problems, general graph
  isomorphism is **not known to be NP-complete** (nor known to be in P) — it sits
  in its own complexity limbo, with Babai's celebrated quasi-polynomial-time
  algorithm as the best known general result. VF2 is the practical workhorse used
  in tools.
