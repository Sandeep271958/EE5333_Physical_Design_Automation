
#!/usr/bin/env python3


import LEFDEFParser
from LEFDEFParser import Rect
import heapq, bisect, time, sys
from collections import defaultdict

# Constants


ROUTING_LAYERS = ['li1', 'met1', 'met2', 'met3', 'met4', 'met5']
LAYER_IDX = {l: i for i, l in enumerate(ROUTING_LAYERS)}

# sky130
LAYER_DIR = {'li1': 'V', 'met1': 'H', 'met2': 'V',
             'met3': 'H', 'met4': 'V', 'met5': 'H'}


LAYER_SPACING = {'li1': 170, 'met1': 140, 'met2': 140,
                 'met3': 300, 'met4': 300, 'met5': 1600}


ADJ_LAYER = {
    'li1':  ['met1'],
    'met1': ['li1', 'met2'],
    'met2': ['met1', 'met3'],
    'met3': ['met2', 'met4'],
    'met4': ['met3', 'met5'],
    'met5': ['met4'],
}

# Decap / tap / fill 
SKIP_CELLS = {
    "sky130_fd_sc_hd__decap_3", "sky130_fd_sc_hd__decap_4",
    "sky130_fd_sc_hd__decap_6", "sky130_fd_sc_hd__decap_8",
    "sky130_fd_sc_hd__decap_12", "sky130_fd_sc_hd__fill_1",
    "sky130_fd_sc_hd__fill_2", "sky130_fd_sc_hd__fill_4",
    "sky130_fd_sc_hd__fill_8", "sky130_fd_sc_hd__lpflow_decapkapwr_3",
    "sky130_fd_sc_hd__lpflow_decapkapwr_4",
    "sky130_fd_sc_hd__lpflow_decapkapwr_6",
    "sky130_fd_sc_hd__lpflow_decapkapwr_8",
    "sky130_fd_sc_hd__lpflow_decapkapwr_12",
    "sky130_fd_sc_hd__lpflow_lsbuf_lh_hl_isowell_tap_1",
    "sky130_fd_sc_hd__lpflow_lsbuf_lh_hl_isowell_tap_2",
    "sky130_fd_sc_hd__lpflow_lsbuf_lh_hl_isowell_tap_4",
    "sky130_fd_sc_hd__lpflow_lsbuf_lh_isowell_tap_1",
    "sky130_fd_sc_hd__lpflow_lsbuf_lh_isowell_tap_2",
    "sky130_fd_sc_hd__lpflow_lsbuf_lh_isowell_tap_4",
    "sky130_fd_sc_hd__tap_1", "sky130_fd_sc_hd__tap_2",
    "sky130_fd_sc_hd__tapvgnd2_1", "sky130_fd_sc_hd__tapvgnd_1",
    "sky130_fd_sc_hd__tapvpwrvgnd_1", "sky130_ef_sc_hd__decap_12",
}

# Power / ground / clock nets we never route (checker also ignores these names)
SKIP_NETS = {'clk', 'VPWR', 'VGND'}

# A* costs.  Wire cost is just Manhattan length (per nm).
# Via cost is high to discourage layer changes (slide #7: vias have large parasitics).
VIA_COST     = 4000      # ~ one row of cells worth of "wire"
GUIDE_PEN    = 1500      # moderate penalty for off-guide in pass 1


OBST_MACRO = 0   # cell internal obstructions  
OBST_PIN   = 1   # pin shapes                  
OBST_WIRE  = 2   # routed wires from any net   


# Guide file parser
def parse_guide(path):
    """
    Parse a GUIDE file produced by a global router.  Format:
        net_name
        (
          x1 y1 x2 y2 layer
          ...
        )
    Returns: dict net_name -> list of (layer, x1, y1, x2, y2)
    """
    guides = defaultdict(list)
    cur = None
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line == '(':
                continue
            if line == ')':
                cur = None
                continue
            parts = line.split()
            if len(parts) == 1:
                cur = parts[0]
                _ = guides[cur]
            elif len(parts) == 5 and cur is not None:
                try:
                    x1, y1, x2, y2 = map(int, parts[:4])
                except ValueError:
                    continue
                lyr = parts[4]
                if lyr in LAYER_IDX:
                    guides[cur].append((lyr, x1, y1, x2, y2))
    return guides


# Instance wrapper: replicates checker.py's Inst.  Pin shapes are transformed
# into design coordinates so they line up with what the checker expects.
class Inst:
    """Transformed instance: pin shapes and obstructions in design coords."""
    def __init__(self, comp, macro):
        self.comp = comp
        self.macro = macro
        origin = comp.location()
        self.bbox = (origin.x, origin.y,
                     origin.x + macro.xdim(),
                     origin.y + macro.ydim())
        self.pins = {}
        self.obsts = defaultdict(list)
        orient = comp.orient()
        xdim, ydim = macro.xdim(), macro.ydim()
        for p in macro.pins():
            shapes = defaultdict(list)
            for port in p.ports():
                for layer, rects in port.items():
                    if layer not in LAYER_IDX:
                        continue
                    for v in rects:
                        r = Rect(v.ll.x, v.ll.y, v.ur.x, v.ur.y)
                        r.transform(orient, origin, xdim, ydim)
                        shapes[layer].append((r.ll.x, r.ll.y, r.ur.x, r.ur.y))
            self.pins[p.name()] = dict(shapes)
        for layer, rects in macro.obstructions().items():
            if layer not in LAYER_IDX:
                continue
            for v in rects:
                r = Rect(v.ll.x, v.ll.y, v.ur.x, v.ur.y)
                r.transform(orient, origin, xdim, ydim)
                self.obsts[layer].append((r.ll.x, r.ll.y, r.ur.x, r.ur.y))


# Track collection
def get_tracks(deff):
    """layer -> {'X': sorted x positions, 'Y': sorted y positions}"""
    tracks = {}
    for layer, glist in deff.tracks().items():
        if layer not in LAYER_IDX:
            continue
        tracks[layer] = {'X': [], 'Y': []}
        for g in glist:
            poss = [g.x + i * g.step for i in range(g.num)]
            if g.orient == 'X':
                tracks[layer]['X'] = sorted(poss)
            else:
                tracks[layer]['Y'] = sorted(poss)
    return tracks


# ============================================================================
# Router : the heart of the project
# ============================================================================
class Router:
    """
    Track-based detailed router with progressive relaxation.

      route_net(name, pin_access, time_budget, guide_pen, ignore_wires)
        is the main per-net call. It decomposes multi-pin nets via Prim's
        MST (slide #14) and routes each leg using A* (slide #9). The
        guide_pen and ignore_wires parameters let the caller dial how
        aggressively to relax constraints between passes.
    """

    def __init__(self, deff, insts, def_pins, layer_width, guides):
        self.deff = deff
        self.insts = insts
        self.def_pins = def_pins
        self.layer_width = layer_width
        self.guides = guides
        self.tracks = get_tracks(deff)

        # Valid X/Y positions for routing on each layer (own tracks +
        # adjacent-layer tracks for via landing).
        self.layer_xs = {}
        self.layer_ys = {}
        self.own_xset = {}
        self.own_yset = {}
        for L in ROUTING_LAYERS:
            if L not in self.tracks:
                continue
            own_x = list(self.tracks[L].get('X', []))
            own_y = list(self.tracks[L].get('Y', []))
            self.own_xset[L] = set(own_x)
            self.own_yset[L] = set(own_y)
            adj_x, adj_y = set(), set()
            for L2 in ADJ_LAYER.get(L, []):
                if L2 in self.tracks:
                    adj_x.update(self.tracks[L2].get('X', []))
                    adj_y.update(self.tracks[L2].get('Y', []))
            if LAYER_DIR[L] == 'H':
                self.layer_xs[L] = sorted(set(own_x) | adj_x)
                self.layer_ys[L] = sorted(own_y)
            else:
                self.layer_xs[L] = sorted(own_x)
                self.layer_ys[L] = sorted(set(own_y) | adj_y)

        # rtree obstacle index per layer
        import rtree
        self.rtree_mod = rtree
        self.obst_tree = {L: rtree.index.Index() for L in ROUTING_LAYERS}
        self.obst_owner = {}    # nid -> owner string
        self.obst_rect  = {}    # nid -> rect tuple
        self.obst_type  = {}    # nid -> OBST_MACRO / OBST_PIN / OBST_WIRE
        self.obst_layer = {}    # nid -> layer (for fast remove)
        self._next_id   = 0

    # Obstacle management
    def add_obstacle(self, layer, r, owner, otype=OBST_MACRO):
        nid = self._next_id
        self._next_id += 1
        self.obst_tree[layer].insert(nid, (r[0], r[1], r[2], r[3]))
        self.obst_owner[nid] = owner
        self.obst_rect[nid]  = r
        self.obst_type[nid]  = otype
        self.obst_layer[nid] = layer
        return nid

    def remove_obstacle(self, nid):
        """Delete obstacle by id (used for rolling back partial routes)."""
        if nid not in self.obst_rect:
            return
        L = self.obst_layer[nid]
        r = self.obst_rect[nid]
        try:
            self.obst_tree[L].delete(nid, (r[0], r[1], r[2], r[3]))
        except Exception:
            pass
        self.obst_owner.pop(nid, None)
        self.obst_rect.pop(nid, None)
        self.obst_type.pop(nid, None)
        self.obst_layer.pop(nid, None)

    def is_blocked(self, layer, r, own_owner, ignore_wires=False):
        """True iff some non-own obstacle on `layer` lies within spacing of r.
        If ignore_wires=True, OBST_WIRE obstacles (other nets' routed wires)
        are also ignored - we accept the spacing/short violations they'd cause.
        Macro obstructions and pin shapes are NEVER ignored."""
        s = LAYER_SPACING[layer]
        rb = (r[0] - s, r[1] - s, r[2] + s, r[3] + s)
        for nid in self.obst_tree[layer].intersection(rb):
            if self.obst_owner.get(nid) == own_owner:
                continue
            if ignore_wires and self.obst_type.get(nid) == OBST_WIRE:
                continue
            other = self.obst_rect[nid]
            if (rb[0] < other[2] and other[0] < rb[2] and
                rb[1] < other[3] and other[1] < rb[3]):
                return True
        return False

    # Geometry building blocks
    def wire_rect(self, layer, x1, y1, x2, y2):
        """Metal rect for a wire segment from (x1,y1) to (x2,y2) on `layer`."""
        W = self.layer_width[layer]
        h = W // 2
        if x1 == x2 and y1 == y2:
            return (x1 - h, y1 - h, x1 + h, y1 + h)
        if y1 == y2:
            x_min, x_max = min(x1, x2), max(x1, x2)
            if x_max - x_min < W:
                cx = (x_min + x_max) // 2
                x_min, x_max = cx - h, cx + h
            return (x_min, y1 - h, x_max, y1 + h)
        else:
            y_min, y_max = min(y1, y2), max(y1, y2)
            if y_max - y_min < W:
                cy = (y_min + y_max) // 2
                y_min, y_max = cy - h, cy + h
            return (x1 - h, y_min, x1 + h, y_max)

    def via_pad(self, layer, x, y):
        """Square metal pad of layer-min-width centred at (x,y)."""
        W = self.layer_width[layer]
        h = W // 2
        return (x - h, y - h, x + h, y + h)

    # Pin access: where can a wire start/end and still touch this pin?
    def find_pin_access(self, pin_shapes):
        """
        pin_shapes : {layer -> [rect, ...]}
        Returns    : list of (x, y, L) entry points (de-duplicated)
        """
        access = set()
        for Lp, rects in pin_shapes.items():
            if Lp not in self.tracks:
                continue
            for (px1, py1, px2, py2) in rects:
                cx, cy = (px1 + px2) // 2, (py1 + py2) // 2
                cand_layers = [Lp] + ADJ_LAYER.get(Lp, [])
                for L in cand_layers:
                    if L not in self.tracks:
                        continue
                    W = self.layer_width[L]
                    h = W // 2
                    if LAYER_DIR[L] == 'H':
                        for yt in self.layer_ys[L]:
                            if yt + h <= py1 or yt - h >= py2:
                                continue
                            added_any = False
                            for xt in self.layer_xs[L]:
                                if px1 <= xt <= px2:
                                    access.add((xt, yt, L))
                                    added_any = True
                            if not added_any:
                                pos = bisect.bisect_left(self.layer_xs[L], cx)
                                for k in (pos - 1, pos, pos + 1):
                                    if 0 <= k < len(self.layer_xs[L]):
                                        xc = self.layer_xs[L][k]
                                        if xc + h >= px1 and xc - h <= px2:
                                            access.add((xc, yt, L))
                    else:
                        for xt in self.layer_xs[L]:
                            if xt + h <= px1 or xt - h >= px2:
                                continue
                            added_any = False
                            for yt in self.layer_ys[L]:
                                if py1 <= yt <= py2:
                                    access.add((xt, yt, L))
                                    added_any = True
                            if not added_any:
                                pos = bisect.bisect_left(self.layer_ys[L], cy)
                                for k in (pos - 1, pos, pos + 1):
                                    if 0 <= k < len(self.layer_ys[L]):
                                        yc = self.layer_ys[L][k]
                                        if yc + h >= py1 and yc - h <= py2:
                                            access.add((xt, yc, L))
        return list(access)

    # A* search engine
    def neighbors(self, state, in_guide_fn, own_net, guide_pen, ignore_wires):
        """Yield (next_state, edge_cost) tuples.
        guide_pen     : penalty added to edges that leave the guide rect set
        ignore_wires  : if True, spacing checks ignore other nets' routed wires
        """
        x, y, L = state
        out = []

        # ---- same-layer extension ----------------------------------------
        if LAYER_DIR[L] == 'H':
            xs = self.layer_xs[L]
            i = bisect.bisect_left(xs, x)
            cand = []
            if i < len(xs) and xs[i] == x:
                if i - 1 >= 0:           cand.append(xs[i - 1])
                if i + 1 < len(xs):      cand.append(xs[i + 1])
            else:
                if i - 1 >= 0:           cand.append(xs[i - 1])
                if i     < len(xs):      cand.append(xs[i])
            for xn in cand:
                if xn == x: continue
                seg = self.wire_rect(L, min(x, xn), y, max(x, xn), y)
                if self.is_blocked(L, seg, own_net, ignore_wires):
                    continue
                pen = 0 if in_guide_fn(L, xn, y) else guide_pen
                out.append(((xn, y, L), abs(xn - x) + pen))
        else:
            ys = self.layer_ys[L]
            i = bisect.bisect_left(ys, y)
            cand = []
            if i < len(ys) and ys[i] == y:
                if i - 1 >= 0:           cand.append(ys[i - 1])
                if i + 1 < len(ys):      cand.append(ys[i + 1])
            else:
                if i - 1 >= 0:           cand.append(ys[i - 1])
                if i     < len(ys):      cand.append(ys[i])
            for yn in cand:
                if yn == y: continue
                seg = self.wire_rect(L, x, min(y, yn), x, max(y, yn))
                if self.is_blocked(L, seg, own_net, ignore_wires):
                    continue
                pen = 0 if in_guide_fn(L, x, yn) else guide_pen
                out.append(((x, yn, L), abs(yn - y) + pen))

        # ---- via to adjacent layer ---------------------------------------
        for L2 in ADJ_LAYER.get(L, []):
            if L2 not in self.tracks:
                continue
            if LAYER_DIR[L2] == 'H':
                if y not in self.own_yset[L2]:
                    continue
            else:
                if x not in self.own_xset[L2]:
                    continue
            pad1 = self.via_pad(L, x, y)
            pad2 = self.via_pad(L2, x, y)
            if self.is_blocked(L, pad1, own_net, ignore_wires):  continue
            if self.is_blocked(L2, pad2, own_net, ignore_wires): continue
            pen = 0 if in_guide_fn(L2, x, y) else guide_pen
            out.append(((x, y, L2), VIA_COST + pen))

        return out

    def astar(self, sources, targets, in_guide_fn, own_net,
              ttl=5.0, guide_pen=GUIDE_PEN, ignore_wires=False):
        """Standard A*; returns the lowest-cost path or None.
        Uses an O(1) bounding-box heuristic instead of O(|T|) min-over-targets:
        when |T| is large (multi-pin nets with many access points per pin),
        this is materially faster while remaining admissible."""
        if not sources or not targets:
            return None
        target_set = set(targets)

        
        T = list(target_set)
        tx_min = min(t[0] for t in T)
        tx_max = max(t[0] for t in T)
        ty_min = min(t[1] for t in T)
        ty_max = max(t[1] for t in T)
        tli    = [LAYER_IDX[t[2]] for t in T]
        tl_min = min(tli)
        tl_max = max(tli)

        def h(s):
            x, y, L = s
            li = LAYER_IDX[L]
            dx = 0 if tx_min <= x <= tx_max else min(abs(x - tx_min), abs(x - tx_max))
            dy = 0 if ty_min <= y <= ty_max else min(abs(y - ty_min), abs(y - ty_max))
            dl = 0 if tl_min <= li <= tl_max else min(abs(li - tl_min), abs(li - tl_max))
            return dx + dy + VIA_COST * dl

        g_score = {}
        parent  = {}
        pq      = []
        for s in sources:
            if s in g_score:
                continue
            g_score[s] = 0
            parent[s]  = None
            heapq.heappush(pq, (h(s), 0, s))

        t0 = time.time()
        cnt = 0
        while pq:
            cnt += 1
            if (cnt & 0x3FF) == 0 and time.time() - t0 > ttl:
                return None
            f, g, s = heapq.heappop(pq)
            if g > g_score.get(s, float('inf')):
                continue
            if s in target_set:
                path = []
                cur = s
                while cur is not None:
                    path.append(cur)
                    cur = parent[cur]
                return list(reversed(path))
            for nxt, edge in self.neighbors(s, in_guide_fn, own_net,
                                            guide_pen, ignore_wires):
                ng = g + edge
                if ng < g_score.get(nxt, float('inf')):
                    g_score[nxt] = ng
                    parent[nxt]  = s
                    heapq.heappush(pq, (ng + h(nxt), ng, nxt))
        return None

    # Path -> wire/pad rectangles
    def path_to_rects(self, path):
        """Compress a path into one rect per same-layer run + via pads."""
        out = []
        if not path:
            return out
        i = 0
        n = len(path)
        while i < n:
            L = path[i][2]
            j = i
            while j + 1 < n and path[j + 1][2] == L:
                j += 1
            xs = [path[k][0] for k in range(i, j + 1)]
            ys = [path[k][1] for k in range(i, j + 1)]
            if i == j:
                pad = self.via_pad(L, xs[0], ys[0])
                out.append((L, pad))
            else:
                x_min, x_max = min(xs), max(xs)
                y_min, y_max = min(ys), max(ys)
                W = self.layer_width[L]
                h = W // 2
                if LAYER_DIR[L] == 'H':
                    y_c = ys[0]
                    if x_min == x_max:
                        out.append((L, self.via_pad(L, x_min, y_c)))
                    else:
                        if x_max - x_min < W:
                            cx = (x_min + x_max) // 2
                            x_min, x_max = cx - h, cx + h
                        out.append((L, (x_min, y_c - h, x_max, y_c + h)))
                else:
                    x_c = xs[0]
                    if y_min == y_max:
                        out.append((L, self.via_pad(L, x_c, y_min)))
                    else:
                        if y_max - y_min < W:
                            cy = (y_min + y_max) // 2
                            y_min, y_max = cy - h, cy + h
                        out.append((L, (x_c - h, y_min, x_c + h, y_max)))
            i = j + 1
        return out

    # Multi-pin net routing : Prim's MST decomposition (lecture slide #14)
    def route_net(self, name, pin_access_list, time_budget,
                  guide_pen=GUIDE_PEN, ignore_wires=False):
        """
        Route net `name`. Each pin already converted to a list of (x,y,L)
        access points in `pin_access_list`.

        Returns: list of (layer, rect) on success, [] for trivial nets
        (<2 reachable pins), None on failure. On failure, ALL obstacles
        added during this call are rolled back so they don't leak into
        the obstacle map as invisible blockers for subsequent nets.
        """
        pins = [pts for pts in pin_access_list if pts]
        if len(pins) < 2:
            if len(pin_access_list) <= 1:
                return []
            return None

        guide_rects = self.guides.get(name, [])
        guides_by_layer = defaultdict(list)
        for (gL, x1, y1, x2, y2) in guide_rects:
            guides_by_layer[gL].append((x1, y1, x2, y2))

        if guide_rects:
            def in_guide(L, x, y):
                for (x1, y1, x2, y2) in guides_by_layer.get(L, ()):
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        return True
                return False
        else:
            def in_guide(L, x, y):
                return True

        endpoint_pin = {}
        for i, pts in enumerate(pins):
            for s in pts:
                endpoint_pin[s] = i

        connected = {0}
        tree = set(pins[0])
        out_rects = []
        pending_nids = []     # nids added during this call -> rollback on failure
        deadline = time.time() + time_budget

        while len(connected) < len(pins):
            time_left = deadline - time.time()
            if time_left <= 0:
                for nid in pending_nids:
                    self.remove_obstacle(nid)
                return None

            targets = []
            for i, pts in enumerate(pins):
                if i not in connected:
                    targets.extend(pts)

            remaining_legs = len(pins) - len(connected)
            leg_budget = max(0.3, min(time_left / remaining_legs, time_left * 0.9))
            path = self.astar(tree, targets, in_guide, name,
                              ttl=leg_budget,
                              guide_pen=guide_pen,
                              ignore_wires=ignore_wires)

            if path is None:
                for nid in pending_nids:
                    self.remove_obstacle(nid)
                return None

            hit_pin = endpoint_pin.get(path[-1])
            if hit_pin is None:
                for nid in pending_nids:
                    self.remove_obstacle(nid)
                return None
            connected.add(hit_pin)

            for (L, r) in self.path_to_rects(path):
                nid = self.add_obstacle(L, r, name, OBST_WIRE)
                pending_nids.append(nid)
                out_rects.append((L, r))

            tree.update(path)
            tree.update(pins[hit_pin])

        return out_rects


# Top-level entry point
def detailed_route(input_DEF, input_LEF, input_GUIDE, output_DEF):
    """
    Read placed DEF, LEF, global-route GUIDE; perform detailed routing on
    every signal net (excluding clk / VPWR / VGND); write the solution DEF.

    Scoring formula:
        score = (runtime / max_runtime) * (#DRC + 50 * #opens)
    => closing an open is worth 50 DRC; we use three passes that progressively
       relax constraints:
        Pass 1 : strict (in-guide preferred, full spacing)
        Pass 2 : off-guide free
        Pass 3 : ignore other nets' wires (accepts some shorts to close opens)
    """
    t_start = time.time()

    # ---- 1. Parse LEF ----
    leff = LEFDEFParser.LEFReader()
    leff.readLEF(input_LEF)

    layer_width = {}
    for L in leff.layers():
        try:
            layer_width[L.name()] = L.width()
        except Exception:
            pass
    for L, W in {'li1': 170, 'met1': 140, 'met2': 140,
                 'met3': 300, 'met4': 300, 'met5': 1600}.items():
        layer_width.setdefault(L, W)

    macros = {m.name(): m for m in leff.macros()}

    # ---- 2. Parse DEF ----
    deff = LEFDEFParser.DEFReader()
    deff.readDEF(input_DEF)

    # ---- 3. Build instances ----
    insts = {}
    for c in deff.components():
        mname = c.macro()
        if mname in SKIP_CELLS:
            continue
        if mname in macros:
            insts[c.name()] = Inst(c, macros[mname])

    # ---- 4. Boundary pins ----
    def_pins = {}
    for p in deff.pins():
        pname = p.name()
        shapes = defaultdict(list)
        for port in p.ports():
            for layer, rects in port.items():
                if layer not in LAYER_IDX:
                    continue
                for r in rects:
                    shapes[layer].append((r.ll.x, r.ll.y, r.ur.x, r.ur.y))
        def_pins[pname] = dict(shapes)

    # ---- 5. Parse GUIDE ----
    guides = parse_guide(input_GUIDE)

    # ---- 6. Build Router ----
    router = Router(deff, insts, def_pins, layer_width, guides)

    # ---- 7. Initial obstacle map ----
    for inst in insts.values():
        for L, rlist in inst.obsts.items():
            for r in rlist:
                router.add_obstacle(L, r, '$OBST', OBST_MACRO)

    # ---- 8. Collect routable nets ----
    used_pin_keys = set()
    used_def_pins = set()
    net_pin_shapes = {}

    for net in deff.nets():
        nname = net.name()
        if nname in SKIP_NETS:
            continue
        shapes_list = []
        for pair in net.pins():
            cell, pin = pair[0], pair[1]
            if cell in insts:
                shapes = insts[cell].pins.get(pin, {})
                if shapes:
                    shapes_list.append(shapes)
                    used_pin_keys.add((cell, pin))
            elif cell == 'PIN':
                shapes = def_pins.get(pin, {})
                if shapes:
                    shapes_list.append(shapes)
                    used_def_pins.add(pin)
        if len(shapes_list) >= 2:
            net_pin_shapes[nname] = shapes_list

    # ---- 8a. Add pin shapes as obstacles (typed OBST_PIN - never ignored) ----
    for nname, slist in net_pin_shapes.items():
        for shapes in slist:
            for L, rlist in shapes.items():
                for r in rlist:
                    router.add_obstacle(L, r, nname, OBST_PIN)

    for cname, inst in insts.items():
        for pname, shapes in inst.pins.items():
            if (cname, pname) in used_pin_keys:
                continue
            for L, rlist in shapes.items():
                for r in rlist:
                    router.add_obstacle(L, r, '$UNUSED', OBST_PIN)

    for pname, shapes in def_pins.items():
        if pname in used_def_pins:
            continue
        for L, rlist in shapes.items():
            for r in rlist:
                router.add_obstacle(L, r, '$UNUSED', OBST_PIN)

    # ---- 9. Net ordering: shortest nets first ----
    def net_size(nname):
        xs, ys = [], []
        for shapes in net_pin_shapes[nname]:
            for L, rlist in shapes.items():
                for r in rlist:
                    xs.append((r[0] + r[2]) // 2)
                    ys.append((r[1] + r[3]) // 2)
        if not xs:
            return 0
        return (max(xs) - min(xs)) + (max(ys) - min(ys))

    net_order = sorted(net_pin_shapes.keys(), key=net_size)
    n_total = len(net_order)
    print(f"[detailed_route] routing {n_total} nets (excluding {SKIP_NETS})")

    # ---- 10. Three-pass routing ----
    HARD_BUDGET_SEC = 28 * 60          # 28 of the 30-min hard cap
    P1_DEADLINE = t_start + HARD_BUDGET_SEC * 0.55
    P2_DEADLINE = t_start + HARD_BUDGET_SEC * 0.78
    P3_DEADLINE = t_start + HARD_BUDGET_SEC * 0.97

    net_to_rects = {}
    pin_access_cache = {}

    def get_pin_access(nname):
        if nname not in pin_access_cache:
            pin_access_cache[nname] = [
                router.find_pin_access(s) for s in net_pin_shapes[nname]
            ]
        return pin_access_cache[nname]

    def run_pass(nets, deadline, cap, guide_pen, ignore_wires, tag):
        """Run one routing pass. Returns list of nets that failed."""
        failed = []
        routed_here = 0
        for i, nname in enumerate(nets):
            now = time.time()
            if now >= deadline:
                failed.extend(nets[i:])
                break
            remaining = deadline - now
            n_left = len(nets) - i
            per_net = max(0.4, min(remaining / n_left, cap))
            per_net = min(per_net, remaining)
            pin_access = get_pin_access(nname)
            rects = router.route_net(nname, pin_access, per_net,
                                     guide_pen=guide_pen,
                                     ignore_wires=ignore_wires)
            if rects:
                net_to_rects[nname] = rects
                routed_here += 1
            elif rects is None:
                failed.append(nname)
        elapsed = time.time() - t_start
        print(f"[{tag}] routed {routed_here}/{len(nets)} this pass, "
              f"{len(failed)} failed, elapsed {elapsed:.1f}s")
        return failed

    # Pass 1: strict
    failed_1 = run_pass(net_order, P1_DEADLINE,
                        cap=3.0, guide_pen=GUIDE_PEN, ignore_wires=False,
                        tag="pass 1: strict")

    # Pass 2: off-guide free
    if failed_1 and time.time() < P2_DEADLINE:
        failed_1.sort(key=net_size)
        failed_2 = run_pass(failed_1, P2_DEADLINE,
                            cap=8.0, guide_pen=0, ignore_wires=False,
                            tag="pass 2: off-guide")
    else:
        failed_2 = list(failed_1)

    # Pass 3: DRC-tolerant (ignore other nets' wires)
    if failed_2 and time.time() < P3_DEADLINE:
        failed_2.sort(key=net_size)
        failed_3 = run_pass(failed_2, P3_DEADLINE,
                            cap=12.0, guide_pen=0, ignore_wires=True,
                            tag="pass 3: drc-tolerant")
    else:
        failed_3 = list(failed_2)

    failed = failed_3

    # ---- 11. Write solution back into the DEF ----
    net_by_name = {n.name(): n for n in deff.nets()}
    for nname, rects in net_to_rects.items():
        net_obj = net_by_name.get(nname)
        if net_obj is None:
            continue
        for (L, r) in rects:
            net_obj.addRect(L, r[0], r[1], r[2], r[3])

    deff.writeDEF(output_DEF)

    total = time.time() - t_start
    print(f"[detailed_route] {len(net_to_rects)}/{n_total} nets routed, "
          f"{len(failed)} failed, elapsed {total:.1f}s -> {output_DEF}")


# CLI
if __name__ == '__main__':
    if len(sys.argv) != 5:
        print("Usage: python ROLLNo.py <in.def> <in.lef> <in.guide> <out.def>",
              file=sys.stderr)
        sys.exit(1)
    detailed_route(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
