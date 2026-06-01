import random

class Clause:
  def __init__(self, vl):
    self._vars = [v for v in vl]
    self._vact = [True for v in vl]
    self._nact = len(self._vars)
    self._val  = None # None for not decided; False/True for evaled to False/True

  def eval(self, m):
    has_unassigned = False
    for v in self._vars:
      var_idx = abs(v)
      val = m[var_idx]
      if val is not None:
        actual_val = val if v >0 else not val

        if actual_val:
          return True
      else:
        has_unassigned = True

    if has_unassigned:
      return None
    return False

  def getUnitVal(self):
    if self._nact == 1:
      for i in range(len(self._vars)):
        if self._vact[i]:
          return self._vars[i]
    return None
  
  def propagate(self, m):
    self._vact = [True for v in self._vars]
    self._nact = 0

    for i in range(len(self._vars)):
      v = self._vars[i]
      var_idx = abs(v)
      val = m[var_idx]

      if val is not None:
        actual_val = val if v>0 else not val
        if not actual_val:
          self._vact[i] = False
        else:
          self._nact += 1
      else:
        self._nact += 1

    self._val = self.eval(m)

    return self._val

  def __repr__(self):
    return '[' + str(self._vars) + ' ' + str(self._vact) + ' ' + str(self._nact) + ' ' + str(self._val) + ']'


def unitClauses(f):
  return [c for c in f if 1 == c._nact and c._val is not True]
        

def pureLiterals(f, m):
  plc = [i for i in range(1, len(m)) if None == m[i]]
  
  p = []

  for var in plc:
    appears_pos = False
    appears_neg = False

    for c in f:
      if c._val is True:
        continue
      if var in c._vars:
        appears_pos = True
      if -var in c._vars:
        appears_neg = True

    if appears_pos and not appears_neg:
      p.append(var)
    elif appears_neg and not appears_pos:
      p.append(-var)

  return p


def pickBranchingLiteral(m):
  l = [i for i in range(1, len(m)) if None == m[i]]
  return l[0] if len(l) else None

def dpll(f, m):
  mc = [i for i in m]

  for c in f:
    c.propagate(mc)

  while True:
    units = unitClauses(f)
    if not units:
      break

    l = units[0].getUnitVal()
    if l is not None:
      mc[abs(l)] = (l>0)
      
      for c in f:
        c.propagate(mc)
  
  while True:
    pures = pureLiterals(f,mc)
    if not pures:
      break

    p = pures[0]
    mc[abs(p)] = (p>0)

    for c in f:
      c.propagate(mc)

  if any(c._val is False for c in f):
    return False, None
  
  if all(c._val is True for c in f):
    return True, mc
  
  l = pickBranchingLiteral(mc)
  if l is None:
    return False , None
  
  mc_true = list(mc)
  mc_true[l] = True
  result, final_m = dpll(f, mc_true)
  if result:
    return True, final_m
  
  mc_false = list(mc)
  mc_false[l] = False
  return dpll(f, mc_false)

def loadCNFFile(fn):
  numvars = 0
  numclauses = 0
  clauses = []
  with open(fn, 'r') as fs:
    for line in fs:
      if line[0] == '%': break
      if line[0] == 'p':
        numvars = int(line.split()[2])
        numclauses = int(line.split()[3])
        continue
      if line[0] == 'c': continue
      if numvars > 0:
        tmp = line.split()
        tmp = [int(tmp[i]) for i in range(len(tmp) - 1)]
        clauses.append(Clause(tmp))
        assert abs(tmp[0]) <= numvars and abs(tmp[1]) <= numvars and abs(tmp[2]) <= numvars
  assert len(clauses) == numclauses
  return numvars, clauses

if __name__ == '__main__':
  import argparse

  ap = argparse.ArgumentParser()
  ap.add_argument("-c", "--cnf", type=str, default="", help='<cnf file>')
  args = ap.parse_args()
  if args.cnf != "":
    # print(f"CNF file  : {args.cnf}") # Sometimes autograders fail if you print extra stuff
    numvars, clauses = loadCNFFile(args.cnf)
    m = [None for i in range(numvars + 1)]
    ret, m = (dpll(clauses, m))
    
    # SAFETY CHECK TO PREVENT CRASHING ON Moodle
    if ret:
        print([(i if m[i] == True else -i) for i in range(1, len(m))])
    else:
        print("UNSATISFIABLE")