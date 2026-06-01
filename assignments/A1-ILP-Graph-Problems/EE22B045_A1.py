

# N is num. vertices; vertices are indexed {0,1,...,(N-1)}
# E is a list of edges; each edge is an unordered pair of vertices
# Return value : list of vertices that constitute the MDS
def mds(N, E):
    import mip

    model = mip.Model("DominatingSet")
    model.verbose = 0 # turn off Cbc console logs

    adj = [[] for _ in range(N)]
    for u,v in E:
      adj[u].append(v)
      adj[v].append(u)

    x = [model.add_var(var_type=mip.BINARY,\
        name=f"x_{i}") for i in range(N)]
    model.objective = mip.minimize(mip.xsum(x))

    for i in range(N):
      neighbors = adj[i]
      model += (x[i] + mip.xsum(x[neighbor] for neighbor in neighbors)) >= 1

    model.optimize()
    model.write('dominating_set.lp')
    if model.status == mip.OptimizationStatus.OPTIMAL:
        return [i for i in range(N) if x[i].x > 0.9]
    return []



# N is num. vertices; vertices are indexed {0,1,...,(N-1)}
# E is a list of edges; each edge is an unordered pair of vertices
# W is list of weights : w[i] is the weight of vertex i
# Return value : (list of vertices that constitute the MWIS, weight of MWIS)

def mwis(N, E, W):
    import mip
    model = mip.Model("WeightedIndependentSet")
    model.verbose = 0 # turn off Cbc console logs

  

    x = [model.add_var(var_type=mip.BINARY,\
        name=f"x_{i}") for i in range(N)]
    model.objective = mip.maximize(mip.xsum(x[i]*W[i] for i in range(N)))

    for u, v in E:
      model += (x[u] + x[v]) <= 1

    model.optimize()
    model.write('weight_independent_set.lp')
    if model.status == mip.OptimizationStatus.OPTIMAL:
                                   
        Selected_vertices = [i for i in range(N) if x[i].x > 0.9]
        Total_weight = sum(W[i] for i in Selected_vertices)
        return (Selected_vertices, Total_weight)
    return [[],0]