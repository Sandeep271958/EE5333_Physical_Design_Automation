# End-Semester Project — Detailed Router

**File:** `EE22B045_EndsemProject.py`
**Checker:** `checker.py` (course-provided)
**Benchmark:** `c7552` on the SkyWater **sky130** open standard-cell PDK

> **Entry point**
> ```python
> detailed_route(input_DEF, input_LEF, input_GUIDE, output_DEF)
> ```
> Read a *placed* DEF, the sky130 LEF, and a global-routing GUIDE; perform
> detailed routing on every signal net; write a DEF containing the routed metal
> shapes for each net.

---

## Table of contents

1. [What detailed routing is](#1-what-detailed-routing-is)
2. [The inputs](#2-the-inputs)
3. [Architecture: the end-to-end pipeline](#3-architecture-the-end-to-end-pipeline)
4. [Key data structures](#4-key-data-structures)
5. [The routing engine](#5-the-routing-engine)
6. [Geometry: from a path to legal metal](#6-geometry-from-a-path-to-legal-metal)
7. [The three-pass strategy — the core of the project](#7-the-three-pass-strategy--the-core-of-the-project)
8. [Staying aligned with the checker](#8-staying-aligned-with-the-checker)
9. [How to run](#9-how-to-run)
10. [Results and discussion](#10-results-and-discussion)
11. [Limitations and future work](#11-limitations-and-future-work)
12. [File manifest](#12-file-manifest)

---

## 1. What detailed routing is

Routing happens in two stages:

- **Global routing** carves the chip into a coarse grid of *gcells* and decides,
  for each net, the *sequence of gcells and layers* it should pass through — a
  rough corridor, not actual wires. The output is the **GUIDE** file.
- **Detailed routing** (this project) takes those corridors and produces the
  **actual metal geometry**: rectangles on specific layers, on legal tracks, with
  **vias** between layers, such that every net is electrically **connected** and
  no **design-rule (DRC)** is broken.

The detailed router must respect the foundry's rules: minimum wire width,
minimum spacing between shapes on the same layer, and the preferred routing
direction of each layer.

### The sky130 layer stack used here

| Layer | Preferred direction | Min width (nm) | Min spacing (nm) |
|-------|---------------------|----------------|------------------|
| `li1` | Vertical            | 170            | 170 |
| `met1`| Horizontal          | 140            | 140 |
| `met2`| Vertical            | 140            | 140 |
| `met3`| Horizontal          | 300            | 300 |
| `met4`| Vertical            | 300            | 300 |
| `met5`| Horizontal          | 1600           | 1600 |

Adjacent layers connect by a via (`li1↔met1↔met2↔…↔met5`). Alternating
H/V preferred directions is what makes Manhattan routing efficient: horizontal
runs on one layer, vertical runs on the next, hop between them with vias.

---

## 2. The inputs

All three are industrial EDA formats, read with the course's `LEFDEFParser`.

### DEF — the placed design (`c7552.def`)
The design *after placement*: cells have fixed locations, nets list their pin
connections, and the file carries the routing-track definitions.

| Quantity | Value |
|---|---|
| Design | `c7552` |
| Die area | `(0, 0) – (187035, 197755)` nm ≈ **187 µm × 198 µm** |
| Units | 1000 DB units / micron |
| Placed components | **1981** |
| Signal nets | **1592** |
| Boundary (I/O) pins | 318 |

A net entry looks like:
```
- N1 ( _1607_ D ) ( _1400_ Q ) ( _1067_ A ) + USE SIGNAL ;
```
i.e. net `N1` connects pin `D` of instance `_1607_`, pin `Q` of `_1400_`, and pin
`A` of `_1067_`. Boundary pins use the special cell name `PIN`:
```
- N100_d ( PIN N100_d ) ( input1 A ) + USE SIGNAL ;
```

### GUIDE — the global-routing solution (`c7552.guide`)
For each of the 1592 nets, a block of per-layer rectangles describing the
corridor the global router chose:
```
N1
(
  13800 172500 20700 179400 li1
  13800 172500 20700 179400 met1
  13800  69000 20700 179400 met2
  ...
)
```
There is **no GUIDE parser in `LEFDEFParser`**, so the project ships its own
(`parse_guide`) that reads these `net → [(layer, x1, y1, x2, y2), …]` blocks.

### LEF — the technology + cell library (`sky130.lef`)
Layer rules (width, spacing, direction) and, for every standard cell (macro), its
**pin shapes** and **internal obstructions** (metal you must route around). The
router reads layer widths from here and falls back to the table above for any
layer the LEF doesn't pin down.

Power/ground/clock nets (`VPWR`, `VGND`, `clk`) are **never routed** — the checker
ignores them too.

---

## 3. Architecture: the end-to-end pipeline

`detailed_route` runs eleven stages:

```
 1. Parse LEF                → layer widths, macro library
 2. Parse DEF                → components, boundary pins, tracks, nets
 3. Build Inst objects       → transform each cell's pins/obstructions to design coords
 4. Collect boundary pins    → I/O pin shapes
 5. Parse GUIDE              → per-net global corridors (custom parser)
 6. Build Router             → per-layer tracks, via-landing sets, rtree index
 7. Seed obstacle map        → all macro obstructions
 8. Collect routable nets    → nets with ≥2 reachable pins; add ALL pins as obstacles (typed)
 9. Order nets               → shortest bounding box first
10. Three-pass routing       → strict → off-guide → DRC-tolerant
11. Write DEF                → addRect() every routed shape, writeDEF()
```

The guiding principle behind the structure: **make legal-by-construction the
default, and only relax when a net would otherwise fail.** Stages 6–9 set up a
world where any path the router finds is already DRC-clean; stage 10 then spends
its time budget escalating only for the nets that resist.

---

## 4. Key data structures

### `Inst` — a placed cell in design coordinates
A standard cell's pin shapes are defined in the LEF in the cell's *local* frame.
Once placed, they must be **transformed** by the instance's origin and
orientation (`N`, `S`, `FN`, `FS`, …). `Inst.__init__` applies
`Rect.transform(orient, origin, xdim, ydim)` to every pin rectangle and every
obstruction, so the router and the checker see pins at the **same absolute
coordinates**. This transform-matching is essential — if the router computed pin
locations differently from the checker, every net would read as open.

### `Router` — tracks, via-landing sets, and the obstacle index
- **Per-layer track positions.** From the DEF's `TRACKS`, each layer gets its
  legal X and Y coordinates. A horizontal layer routes *along* its own Y tracks
  but may sit on X positions borrowed from adjacent layers (so vias land on the
  neighbour's tracks); vertical layers are the mirror image. `own_xset`/`own_yset`
  record a layer's *own* tracks, used to decide where a via may legally drop.
- **`rtree` spatial index per layer** (`obst_tree[layer]`). Obstacle lookup is the
  inner-loop hot path; an R-tree answers "what lies within spacing of this
  rectangle?" in ~$O(\log n)$ instead of scanning thousands of shapes.
- **Obstacle typing** (`OBST_MACRO`, `OBST_PIN`, `OBST_WIRE`). Every obstacle is
  tagged. This is what lets the final pass ignore *only* other nets' routed wires
  while **never** crossing a pin or a cell obstruction — see §7.

### Obstacle map contents
1. all macro (cell-internal) obstructions — `OBST_MACRO`;
2. **all** routable nets' pin shapes — `OBST_PIN` (so one net cannot stomp on
   another's pin);
3. unused pins (pins on cells/boundaries not part of any routed net) — also
   `OBST_PIN`;
4. each routed wire, added as it is laid down — `OBST_WIRE` (so later nets avoid
   earlier nets).

---

## 5. The routing engine

### Pin access points (`find_pin_access`)
A wire can only "touch" a pin at points that (a) overlap the pin's metal and
(b) lie on a legal track. `find_pin_access` enumerates, for each pin shape and
each candidate layer (the pin's own layer plus adjacent layers for via access),
the set of `(x, y, layer)` entry points that satisfy both. If no track falls
inside the pin, it snaps to the nearest track that still overlaps. These entry
points become the *sources* and *targets* of the A\* search.

### A\* on the track graph (`astar`, `neighbors`)
Routing one connection is a shortest-path search where:

- **A node** is a `(x, y, layer)` triple on the track graph.
- **Same-layer moves** step to the next/previous track in the layer's preferred
  direction; edge cost = Manhattan distance, plus a **guide penalty** if the step
  leaves the net's global corridor.
- **Via moves** hop to an adjacent layer at the same `(x, y)`, but only where that
  point is on the neighbour's own track; edge cost = `VIA_COST` (a large constant).
- **Blocked?** Each candidate wire/via rectangle is spacing-checked against the
  R-tree (`is_blocked`); blocked moves are not generated.

The cost constants encode the physics and the strategy:

| Constant | Value | Meaning |
|---|---|---|
| wire cost | Manhattan length (per nm) | prefer short wires |
| `VIA_COST` | 4000 | vias have large parasitics → discourage layer changes |
| `GUIDE_PEN` | 1500 | soft cost for leaving the global corridor (pass 1 only) |

**The heuristic.** A\* needs an admissible (never-overestimating) heuristic to the
goal. With multi-pin nets there can be *many* target access points, so taking the
min distance over all targets would be $O(|T|)$ per node. Instead the router
computes the **bounding box of all targets** once and uses an $O(1)$
box-distance (plus `VIA_COST ×` layer distance) heuristic. It stays admissible
because the true cost to reach any target is at least the distance to the target
box, and it is materially faster on nets with many access points.

A per-search time-to-live (`ttl`) makes A\* bail out of pathological searches so
one hard net can't consume the whole budget.

### Multi-pin nets: Prim-style MST decomposition (`route_net`)
A net with *k* pins is not one path but a tree. The router grows the tree
greedily (Prim's MST idea):

1. Start with pin 0's access points as the connected `tree`.
2. Repeat until all pins are connected: run A\* from the **entire current tree**
   to **all access points of all unconnected pins**, and connect whichever pin is
   reached first.
3. Each found path is converted to metal, **added to the obstacle map as
   `OBST_WIRE`**, and merged into the tree.

This naturally produces a Steiner-ish tree: later legs can start from any point
already routed, not just the original pins.

**Rollback on failure.** If any leg fails (no path within the time budget), every
obstacle this net added during the call is removed. Without this, a half-routed
failed net would leave "ghost" wires in the obstacle map that silently block
later nets.

### Net ordering
Nets are routed **shortest bounding-box first**. Short nets are easy, rarely
conflict, and routing them first fills in the obstacle map cheaply, leaving the
long/hard nets to negotiate around a mostly-settled layout.

---

## 6. Geometry: from a path to legal metal

A\* returns a list of track points; `path_to_rects` compresses it into the
minimum number of DRC-legal rectangles:

- **Runs on one layer** collapse into a single rectangle spanning the run, widened
  to the layer's minimum width if the run is shorter than that width (so a tiny
  jog never produces a sub-min-width sliver — the #1 width-DRC trap).
- **Layer changes** emit a square **via pad** of the layer's min width at the
  transition point, on *both* layers, so the checker sees overlapping metal on
  adjacent layers (its definition of a via — see §8).

`wire_rect` and `via_pad` centre every shape on the track and enforce min width;
this is where "legal by construction" is actually enforced at the geometry level.

---

## 7. The three-pass strategy — the core of the project

### The scoring formula drives everything
The checker scores a solution as:

```
score = (runtime / max_runtime) × (#DRC_violations + 50 × #open_nets)
```

Two facts fall out of this and shape the whole design:

1. **An open net costs 50× a DRC violation.** Leaving a net disconnected is
   catastrophic; a spacing violation is cheap by comparison. So the router's
   overriding priority is **connect every net**, even at the price of some DRCs.
2. **Runtime is a linear multiplier.** Faster is strictly better for the same
   quality, but there is no benefit to finishing early if nets remain open —
   spend the budget closing them.

### Three passes, progressively relaxing constraints
Rather than one rigid routing attempt, the router makes three sweeps, each one
loosening a constraint for the nets that still failed:

| Pass | Budget (of 28 min) | Guide penalty | Ignore other nets' wires? | Intent |
|------|-------------------|---------------|----------------------------|--------|
| **1 — strict** | up to ~55% | `1500` (in-guide preferred) | no | Cleanly route the easy majority, in-corridor, fully spacing-legal. |
| **2 — off-guide** | up to ~78% | `0` (corridor ignored) | no | Let the nets that failed wander outside their global corridor to find a legal path. |
| **3 — DRC-tolerant** | up to ~97% | `0` | **yes** | For the stubborn remainder, allow crossing other nets' *wires* (accepting spacing/short DRCs) to **close the open** — because 1 open = 50 DRC. |

Crucially, pass 3 ignores **only** `OBST_WIRE` obstacles. It will still never
overlap a **pin** (`OBST_PIN`) or a **cell obstruction** (`OBST_MACRO`) — those
are hard blockers, because shorting onto a pin or routing through a cell is not a
recoverable "cheap DRC," it's a broken design. Between passes the failed-net list
is re-sorted shortest-first and the per-net time cap is loosened (3 s → 8 s →
12 s), since the survivors are the hard cases that deserve more search.

### Time budgeting
A hard budget of **28 of the 30 minutes** is split across the three pass
deadlines (55% / 78% / 97%). Within a pass, each net gets an adaptive slice
(`remaining_time / nets_left`, capped), and A\* itself carries a `ttl`. The result
degrades gracefully: if time runs out, whatever is routed is kept and written
out, rather than crashing or producing nothing.

This staged relaxation is the single most important design idea in the project:
**spend cheap effort first, escalate only for what resists, and trade DRCs for
opens exactly in the ratio the score rewards.**

---

## 8. Staying aligned with the checker

The router was written against the checker's exact definitions so that "looks
routed" and "scores as routed" coincide:

- **Connectivity = one connected component.** `checker.py` builds, per net, a
  graph whose nodes are the net's shapes (pins + routed rects) and whose edges
  join shapes that **overlap on the same or adjacent layers**. The net is
  connected iff that graph is a single component. The router therefore makes sure
  consecutive wire segments overlap, vias drop pads on *both* layers at the same
  point, and pin-access points actually sit on the pin metal.
- **Spacing DRC = bloat-and-query.** The checker bloats each shape by the layer
  spacing and flags any overlap with another net's shape (or an obstruction). The
  router's `is_blocked` uses the *same* spacing values and the same
  bloated-rectangle test, so a path the router believes is legal is legal to the
  checker.
- **Width DRC.** The checker flags any rectangle narrower than the layer's min
  width; `path_to_rects`/`wire_rect` widen every shape to min width to prevent it.
- **Same skip sets.** Identical `skipCells` (decap/fill/tap) and
  `skipNets` (`clk`/`VPWR`/`VGND`) lists, and the same coordinate transform, so the
  two programs agree on what exists and where.

---

## 9. How to run

From `project-detailed-router/`, with the three input files in `data/`:

```bash
# 1. Route
python EE22B045_EndsemProject.py \
    data/c7552.def data/sky130.lef data/c7552.guide \
    c7552_routed.def

# 2. Check DRCs + connectivity (add -p for the interactive viewer)
python checker.py \
    -l data/sky130.lef \
    -i data/c7552.def \
    -o c7552_routed.def
```

The router prints per-pass progress, e.g.:
```
[detailed_route] routing 1592 nets (excluding {'clk', 'VPWR', 'VGND'})
[pass 1: strict]       routed  N/1592 this pass, M failed, elapsed  ...s
[pass 2: off-guide]    routed  ...
[pass 3: drc-tolerant] routed  ...
[detailed_route] X/1592 nets routed, Y failed, elapsed Zs -> c7552_routed.def
```

The checker prints each violation and the totals:
```
Total number of spacing violations : <#DRC>
Total number of nets : 1592
Total number of open nets : <#opens>
```

---

## 10. Results and discussion

> **A note on the numbers below.** The router depends on the course's compiled
> `LEFDEFParser` and on `rtree`; reproduce the exact counts by running §9 on your
> machine and filling in the table. The discussion explains *what the design
> achieves and why*, and how to read the output — which is the part that
> generalizes beyond a single run.

### Results template — fill from your checker run

| Metric | Value | Source |
|---|---|---|
| Total signal nets | 1592 | DEF |
| Nets routed | ____ / 1592 | router final line |
| Nets left open | ____ | checker `open nets` |
| Spacing DRC violations | ____ | checker `spacing violations` |
| Width DRC violations | ____ | checker `MinWidth` lines |
| Router runtime | ____ s | router final line |
| **Score** = (runtime/max)·(#DRC + 50·#opens) | ____ | formula |

Per-pass contribution (from the `[pass N]` lines):

| Pass | Nets routed this pass | Cumulative routed | Elapsed (s) |
|------|----------------------|-------------------|-------------|
| 1 — strict | ____ | ____ | ____ |
| 2 — off-guide | ____ | ____ | ____ |
| 3 — DRC-tolerant | ____ | ____ | ____ |

### How to interpret the result

- **Opens dominate the score (50× weight).** The headline question is "how many
  of the 1592 nets are open?" The three-pass design exists specifically to drive
  this toward zero. If the checker still reports opens, those are nets so
  congested that even the wire-ignoring pass 3 couldn't reach them in the time
  budget — the candidates for the future-work ideas in §11.
- **DRCs are the deliberate price of pass 3.** A non-zero spacing count is
  expected and often *correct* under this scoring: each spacing violation pass 3
  accepts to close an open is a 50-to-1 trade in your favour. A solution with a
  handful of DRCs and zero opens beats a "clean" solution that leaves nets open.
- **Width DRCs should be ~0.** `wire_rect`/`path_to_rects` enforce min width by
  construction, so a non-zero width count points to a geometry edge case worth
  investigating rather than an intentional trade.
- **Runtime is a multiplier, not a target to minimize blindly.** Because the
  budget is staged, the router uses *more* time only when nets remain unrouted.
  Finishing in well under 28 minutes with everything routed is the ideal outcome;
  using the full budget means the design is hard and the late passes were earning
  their keep.

### Why the staged design is the right call here
A single strict pass would leave the congested nets open — and each open is worth
50 DRCs, so a few opens wreck the score. A single permissive pass would route
everything but generate far more DRCs than necessary, because even the *easy*
nets would be allowed to violate spacing. Separating "easy, do it cleanly" from
"hard, relax just enough" is what lets the router collect the cheap clean routes
**and** rescue the expensive opens, spending its limited time where it changes
the score the most.

---

## 11. Limitations and future work

The router is a **constructive, route-once** detailed router: each net is routed
once and never ripped up. The natural improvements:

- **Rip-up and reroute (RRR).** When a net fails, tear out the wires blocking it,
  route it, and re-route the victims. The single biggest quality lever.
- **Negotiated-congestion routing (PathFinder).** Add a *history cost* to
  congested tracks and iterate, so nets cooperatively avoid hot spots instead of
  greedily grabbing tracks in net-order. This addresses the root cause of the
  opens that pass 3 has to paper over with DRCs.
- **Smarter net ordering / criticality.** Order by congestion or pin count, not
  just bounding-box size.
- **Proper via rules.** The current via model is a min-width pad on each layer;
  real cut/enclosure rules and via-spacing would make the output closer to
  sign-off clean.
- **Parallelism.** Independent (non-overlapping) nets can be routed concurrently
  to use the time budget better.
- **Exact pin-access modelling.** Enumerate on-grid access with full pin-overlap
  geometry rather than the snap-to-nearest fallback, reducing avoidable opens on
  awkwardly shaped pins.

---

## 12. File manifest

| File | What it is |
|---|---|
| `EE22B045_EndsemProject.py` | The detailed router. `detailed_route(...)` is the entry point; `Router` is the engine; `parse_guide` is the custom GUIDE parser. |
| `checker.py` | Course-provided DRC + connectivity checker and interactive viewer. |
| `data/c7552.def` | Placed design (cells, nets, tracks, pins). *Place here.* |
| `data/c7552.guide` | Global-routing corridors per net. *Place here.* |
| `data/sky130.lef` | Technology + standard-cell library. *Place here.* |

### Code-structure cheat sheet

```
parse_guide(path)                     custom GUIDE parser  → net → [(layer,x1,y1,x2,y2)]
class Inst                            cell pins/obstructions transformed to design coords
get_tracks(deff)                      layer → {'X':[...], 'Y':[...]} legal track positions
class Router
  ├─ add/remove_obstacle              rtree obstacle bookkeeping (with type + owner)
  ├─ is_blocked                       spacing check vs rtree (honours ignore_wires)
  ├─ wire_rect / via_pad              min-width-legal geometry primitives
  ├─ find_pin_access                  legal (x,y,layer) entry points on a pin
  ├─ neighbors                        A* successors: same-layer steps + vias, with costs
  ├─ astar                            A* with O(1) bounding-box heuristic + ttl
  ├─ path_to_rects                    compress a path → minimal legal rectangles
  └─ route_net                        Prim-MST multi-pin routing + rollback-on-fail
detailed_route(in_def,in_lef,in_guide,out_def)
                                      parse → build → seed obstacles → order →
                                      3-pass route → write DEF
```