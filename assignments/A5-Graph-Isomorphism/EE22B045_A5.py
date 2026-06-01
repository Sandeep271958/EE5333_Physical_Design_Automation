def build_graph(graph_in):
    attributes, edges = graph_in
    attr = {i: attributes[i] for i in range(len(attributes))}

    neighbors = {i: set() for i in range(len(attributes))}
    for (u,v) in edges:
        neighbors[u].add(v)
        neighbors[v].add(u)

    return attr, neighbors

def get_candidates(g_node, g_attr, g_nbrs, h_attr, h_nbrs, used_h):
    candidates = []
    g_degree = len(g_nbrs[g_node])
    g_attributes = g_attr[g_node]

    for h_node in h_attr:
        if h_node in used_h:
            continue
        if h_attr[h_node] != g_attributes:
            continue
        if len(h_nbrs[h_node]) != g_degree:
            continue

        candidates.append(h_node)

    return candidates


def feasibility(g_node, h_node, mapping, g_nbrs, h_nbrs):
    """Check if mapping g_node -> h_node is consistent with current partial mapping.
    mapping: dict {g_vertex: h_vertex} built so far"""
    for g_nb in g_nbrs[g_node]:
        if g_nb in mapping:
            h_nb = mapping[g_nb]
            if h_nb not in h_nbrs[h_node]:
                return False
    
    reverse_mapping = {v: k for k, v in mapping.items()}
    for h_nb in h_nbrs[h_node]:
        if h_nb in reverse_mapping:
            g_nb = reverse_mapping[h_nb]
            if g_nb not in g_nbrs[g_node]:
                return False
            
    return True

def vf2(g_order, idx, mapping, g_attr, g_nbrs, h_attr, h_nbrs):
    if idx == len(g_order):
        return mapping.copy()
    
    g_node  = g_order[idx]
    used_h  = set(mapping.values())
    candidates = get_candidates(g_node, g_attr, g_nbrs, h_attr, h_nbrs, used_h)

    for h_node in candidates:
        if feasibility(g_node, h_node, mapping, g_nbrs, h_nbrs):
            mapping[g_node] = h_node
            result = vf2(g_order, idx + 1, mapping,
                               g_attr, g_nbrs, h_attr, h_nbrs)
            if result is not None:
                return result
            del mapping[g_node]         # Backtrack

    return None

def isomorphism(G,H):
    g_attr_list, g_edges = G
    h_attr_list, h_edges = H
    n = len(g_attr_list)

    if len(g_attr_list) != len(h_attr_list) or len(g_edges) != len(h_edges):
        return None
    
    g_attr, g_nbrs = build_graph(G)
    h_attr, h_nbrs = build_graph(H)

    result = vf2(list(range(n)), 0, {}, g_attr, g_nbrs, h_attr, h_nbrs)

    if result is None:
        return None
    
    return [result[i] for i in range(n)]


