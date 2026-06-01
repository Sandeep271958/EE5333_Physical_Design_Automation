def partitionFM(V, E, Amin, Amax):
    # build adjacency list for faster lookups
    adj = {u: [] for u in V}
    for net_name, pins in E.items():
        for pin in pins:
            adj[pin._name].append(net_name)

    # greedy initial partition based on area descending
    cells_sorted = sorted(V.keys(), key=lambda x: V[x]._area, reverse=True)
    part = {}          
    area = [0.0, 0.0]
    
    for cell in cells_sorted:
        a = V[cell]._area
        # pack to balance, but respect Amax
        if area[0] <= area[1] and area[0] + a <= Amax:
            p = 0
        elif area[1] + a <= Amax:
            p = 1
        else:
            p = 0 if area[0] <= area[1] else 1
            
        part[cell] = p
        area[p] += a

    def get_net_distribution():
        dist = {}
        for net, pins in E.items():
            dist[net] = [0, 0]
            for p in pins:
                dist[net][part[p._name]] += 1
        return dist

    def calc_gain(cell, dist):
        src = part[cell]
        dest = 1 - src
        gain = 0
        for net in adj[cell]:
            if dist[net][src] == 1:
                gain += 1
            if dist[net][dest] == 0:
                gain -= 1
        return gain

    # run passes until no better cuts are found
    for _ in range(len(V)):
        dist = get_net_distribution()
        gains = {u: calc_gain(u, dist) for u in V}
        
        area_tracker = [
            sum(V[u]._area for u in V if part[u] == 0),
            sum(V[u]._area for u in V if part[u] == 1)
        ]

        locked = set()
        history = []
        cum_gain = 0
        best_gain = 0
        best_step = -1

        # try to move every cell once per pass
        for step in range(len(V)):
            target_cell = None
            max_g = -float('inf')

            # find best valid move
            for cell in V:
                if cell in locked:
                    continue
                    
                src = part[cell]
                dest = 1 - src
                
                new_src_area = area_tracker[src] - V[cell]._area
                new_dest_area = area_tracker[dest] + V[cell]._area
                
                # check if move violates area bounds
                if new_src_area >= Amin and new_dest_area <= Amax:
                    if gains[cell] > max_g:
                        max_g = gains[cell]
                        target_cell = cell

            if not target_cell:
                break # no valid moves left

            # execute move
            src = part[target_cell]
            dest = 1 - src

            area_tracker[src] -= V[target_cell]._area
            area_tracker[dest] += V[target_cell]._area
            part[target_cell] = dest
            locked.add(target_cell)

            # update neighbors of the moved cell incrementally
            for net in adj[target_cell]:
                dist[net][src] -= 1
                dist[net][dest] += 1
                
                for pin in E[net]:
                    if pin._name not in locked:
                        gains[pin._name] = calc_gain(pin._name, dist)

            cum_gain += max_g
            history.append(target_cell)

            if cum_gain > best_gain:
                best_gain = cum_gain
                best_step = step

        # no overall improvement in this pass, undo and stop
        if best_gain <= 0:
            for cell in history:
                part[cell] = 1 - part[cell]
            break

        # restore to the peak gain state in this pass
        for i in range(len(history) - 1, best_step, -1):
            part[history[i]] = 1 - part[history[i]]

    # calculate final cut size
    total_cuts = 0
    for net, pins in E.items():
        sides = {part[p._name] for p in pins}
        if len(sides) > 1:
            total_cuts += 1

    ans = [[], []]
    for cell in V:
        ans[part[cell]].append(V[cell])

    return ans, total_cuts