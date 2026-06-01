# EE5333 — Introduction to Physical Design Automation

Coursework, algorithm implementations, and the end-semester **detailed router**
project for EE5333 at IIT Madras.

> **Author:** Mourya (Roll No. **EE22B045**)
> **Course:** EE5333 — Introduction to Physical Design Automation
> **Language:** Python 3

---

## What this repository is

Physical Design Automation (PDA) is the part of the VLSI flow that turns a
gate-level netlist into a manufacturable layout: partitioning, floorplanning,
placement, and routing, with optimization machinery (ILP, SAT, simulated
annealing, branch-and-bound, graph algorithms) underneath each step.

This repo collects six assignments — each one a self-contained implementation of
a classic PDA / combinatorial-optimization algorithm — and a capstone
**detailed router** that consumes industrial-format `LEF` / `DEF` / `GUIDE`
files and emits a routed `DEF`.

The assignments are deliberately sequenced so the tools build on each other. The
clearest example: **A1** uses an ILP solver (`mip`) as a black box to solve graph
problems, and **A6** then implements the *guts* of that solver — simplex plus
branch-and-bound — from scratch.

---

## Repository map

```
EE5333-Physical-Design-Automation/
├── README.md                          ← you are here
├── assignments/
│   ├── A1-ILP-Graph-Problems/         Minimum Dominating Set + Max-Weight Independent Set via ILP
│   ├── A2-FM-Partitioning/            Fiduccia–Mattheyses 2-way partitioning
│   ├── A3-Floorplanning-SeqPair/      Sequence-pair floorplanning + simulated annealing
│   ├── A4-DPLL-SAT-Solver/            DPLL SAT solver (unit prop + pure literals + backtracking)
│   ├── A5-Graph-Isomorphism/          VF2-style attributed graph isomorphism
│   └── A6-Branch-and-Bound-ILP/       Simplex + branch-and-bound ILP solver
└── project-detailed-router/
    ├── README.md                      ← full design write-up + results
    ├── EE22B045_EndsemProject.py      the router (detailed_route entry point)
    ├── checker.py                     the course-provided DRC / connectivity checker
    ├── sky130.lef
    └── data/                          place c7552.def, c7552.guide, sky130.lef here
```

Each assignment folder has its own `README.md` with the problem statement, the
mathematical formulation, a walkthrough of the code, complexity notes, how to
run it, and known caveats.

---

## How the pieces map to the PD flow

| Assignment | PDA / EDA concept | Core algorithm | Exact or heuristic? |
|---|---|---|---|
| **A1** | Logic/constraint modelling | ILP formulation, solved with `mip` (CBC) | Exact (NP-hard) |
| **A2** | **Partitioning** | Fiduccia–Mattheyses with gain-based moves | Heuristic |
| **A3** | **Floorplanning** | Sequence pairs + simulated annealing | Heuristic |
| **A4** | Equivalence / constraint solving | DPLL satisfiability | Exact |
| **A5** | Netlist/layout matching | VF2 graph isomorphism | Exact |
| **A6** | The solver behind A1 | Simplex + branch-and-bound | Exact (NP-hard) |
| **Project** | **Detailed routing** | Track-based A* + MST decomposition + 3-pass relaxation | Heuristic |

This is roughly the order of the back-end flow: *partition → floorplan →
(place) → route*, with the optimization theory (ILP/SAT/B&B) threaded through.

---

## Dependencies

```bash
pip install mip numpy networkx rtree
```

Plus the **course-provided** `LEFDEFParser` module (a pybind11 wrapper around a
C++ LEF/DEF reader — not on PyPI; build it from the course tutorials repo).
The detailed router and `checker.py` both import it.

| Module | Used by |
|---|---|
| `mip` | A1 (solver), A6 (model container for B&B nodes) |
| `numpy` | A6 (simplex tableau) |
| `networkx` | `checker.py` (connectivity graph) |
| `rtree` | project router + `checker.py` (spatial obstacle index) |
| `LEFDEFParser` | project router + `checker.py` |
| `matplotlib` | A3 plotting, `checker.py` interactive viewer (optional) |

---

## Quick start

Run any assignment directly:

```bash
# A4 (DPLL) takes a DIMACS .cnf on the command line
python assignments/A4-DPLL-SAT-Solver/EE22B045_A4.py -c some_instance.cnf

# A6 (branch & bound) has its test cases inline
python assignments/A6-Branch-and-Bound-ILP/EE22B045_A6.py
```

Run the **detailed router** and check the result:

```bash
cd project-detailed-router

python EE22B045_EndsemProject.py data/c7552.def data/sky130.lef \
                                 data/c7552.guide  c7552_routed.def

python checker.py -l data/sky130.lef -i data/c7552.def -o c7552_routed.def
# add -p to open the interactive layer/DRC viewer
```

See [`project-detailed-router/README.md`](project-detailed-router/README.md) for
the complete design discussion and results.

---

## The end-semester project at a glance

A **track-based detailed router** for the `c7552` benchmark on the SkyWater
**sky130** open-PDK standard-cell library:

- **Design size:** 1981 placed cells, **1592 signal nets**, 318 boundary pins,
  die ≈ 187 µm × 198 µm.
- **Layer stack:** `li1, met1, met2, met3, met4, met5` with alternating
  horizontal/vertical preferred directions.
- **Approach:** snap everything to real routing tracks, route each net with
  **A\*** (multi-pin nets decomposed by a **Prim MST**), and run **three passes**
  that progressively relax constraints to chase down the hard nets.
- **Why three passes:** the scoring formula weights an *open* net 50× a *DRC*
  violation, so the last pass deliberately trades cheap spacing violations to
  eliminate the expensive opens.

---

## Academic-integrity note

This is a personal coursework archive for EE5333 (IIT Madras). If you are
currently enrolled, use it for reference only and follow your course's
collaboration policy.
