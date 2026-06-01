import numpy as np
from mip import Model, maximize, INTEGER, xsum

verbose = False
eps = 1e-6

def print_tableau(A, b, c, f):
    for i in range(len(A)):
        print("{0:30} | {1}".format(str(A[i]), b[i]))
    print('_______________________________________')
    print("{0:30} | {1}\n".format(str(c), f))

def simplex(m, obj):
    varMap = {v.name: i for i, v in enumerate(m.vars)}
    numVars = len(m.constrs) + len(m.vars)
    A = np.zeros(shape=(len(m.constrs), numVars))
    c = np.zeros(numVars)
    for i, v in obj.expr.items():
        c[varMap[i.name]] = v
    b = np.zeros(len(m.constrs))
    for i, e in enumerate(m.constrs):
        sens = e.expr.sense
        b[i] = e.rhs if sens == '<' else -e.rhs
        for ind, val in e.expr.expr.items():
            A[i][varMap[ind.name]] = val if sens == '<' else -val
        if sens == '<' or sens == '>':
            A[i][len(m.vars) + i] = 1
    f = 0
    sol = np.zeros(numVars)
    print("Initial tableau:")
    print_tableau(A, b, c, f)
    for i in range(len(m.vars), numVars):
        sol[i] = b[i - len(m.vars)]
    while np.any(c > 0):
        if not np.any(c > 0):
            break
        pivot = np.argmax(c > 0)
        pr = np.argmin(
            [b[i] / A[i][pivot] if A[i][pivot] > 0 else np.inf
             for i in range(len(b))]
        )
        scale = A[pr][pivot]
        A[pr] /= scale
        b[pr] /= scale
        for i in range(len(b)):
            if i == pr:
                continue
            scale = A[i][pivot]
            A[i] -= scale * A[pr]
            b[i] -= scale * b[pr]
        scale = c[pivot]
        c -= scale * A[pr]
        f -= scale * b[pr]
        sol = np.zeros(numVars)
        for j in range(numVars):
            if np.sum(A, axis=0)[j] == 1.0:
                i = np.argmax(A[:, j] > 0)
                sol[j] = b[i]
        if verbose:
            print(f'after : A = {A} b = {b}, c = {c}, f = {f}, sol = {sol}')
    print("Final tableau:")
    print_tableau(A, b, c, f)
    return sol, -f

def is_sol_integer(sol, Nvar):
    for i in range(Nvar):
        if abs(round(sol[i]) - sol[i]) > eps:
            return False
    return True

def _check_feasibility(sol, m_node, Nvar):
    for i in range(Nvar):
        if sol[i] < -eps:
            return False
    varMap = {v.name: i for i, v in enumerate(m_node.vars)}
    for constr in m_node.constrs:
        lhs = sum(coef * sol[varMap[v.name]]
                  for v, coef in constr.expr.expr.items())
        if constr.expr.sense == '<' and lhs > constr.rhs + eps:
            return False
        if constr.expr.sense == '>' and lhs < constr.rhs - eps:
            return False
    return True

def solve_ilp(m, obj):
    Nvar = len(m.vars)
    best_sol = [None]
    best_f = [-np.inf]

    def _make_node(extra_constrs):
        m_new = Model()
        vars_new = [m_new.add_var(name=v.name) for v in m.vars]
        ntv = {v.name: vars_new[i] for i, v in enumerate(m.vars)}

        obj_new = maximize(
            xsum(coef * ntv[v.name] for v, coef in obj.expr.items())
        )

        for constr in m.constrs:
            lhs = xsum(coef * ntv[v.name]
                       for v, coef in constr.expr.expr.items())
            if constr.expr.sense == '<':
                m_new += lhs <= constr.rhs
            else:
                m_new += lhs >= constr.rhs

        for vi, sense, rhs in extra_constrs:
            if sense == '<=':
                m_new += vars_new[vi] <= rhs
            else:
                m_new += vars_new[vi] >= rhs

        return m_new, obj_new

    def _bnb(extra_constrs):
        m_node, obj_node = _make_node(extra_constrs)
        sol, f = simplex(m_node, obj_node)

        if not _check_feasibility(sol, m_node, Nvar):
            return

        if f <= best_f[0] + eps:
            return

        if is_sol_integer(sol, Nvar):
            best_f[0] = f
            best_sol[0] = sol.copy()
            return

        branch_var = next(
            (i for i in range(Nvar)
             if abs(round(sol[i]) - sol[i]) > eps),
            -1
        )
        
        if branch_var == -1:
            return

        val = sol[branch_var]
        floor_val = int(np.floor(val))
        ceil_val = int(np.ceil(val))

        _bnb(extra_constrs + [(branch_var, '<=', floor_val)])
        _bnb(extra_constrs + [(branch_var, '>=', ceil_val)])

    _bnb([])
    return best_sol[0], best_f[0]

m = Model()
x = [m.add_var(var_type=INTEGER) for i in range(2)]
obj = m.objective = maximize(x[0] + x[1])
m += x[0] + 3 * x[1] <= 9.2
m += 2 * x[0] + x[1] <= 8.4
sol, f = solve_ilp(m, obj)
solve_ilp(m, obj)
print('solution :', sol[0:len(m.vars)], f'objective : {f}\n')
m.optimize()
print('mip sol :', [v.x for v in m.vars], 'objective :', m.objective.x)

m = Model()
x = [m.add_var(var_type=INTEGER) for i in range(3)]
obj = m.objective = maximize(6 * x[0] + x[1])
m += 9 * x[0] + x[1] + x[2] <= 18.4
m += 24 * x[0] + x[1] + 4 * x[2] <= 42.3
m += 12 * x[0] + 3 * x[1] + 4 * x[2] <= 96.5
sol, f = solve_ilp(m, obj)
print('solution :', sol[0:len(m.vars)], f'objective : {f}\n')
m.optimize()
print('mip sol :', [v.x for v in m.vars], 'objective :', m.objective.x)