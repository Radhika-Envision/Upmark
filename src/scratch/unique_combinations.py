'''
Finds a set of random numbers whose combinations are all unique. If no such
sequence exists, it runs forever ^^;
'''

import itertools
import random

def unique(sums):
    return all(a != b for a, b in itertools.combinations(sums, 2))

def combinations(ns):
    return itertools.chain(
        (sum(c) for c in itertools.combinations(ns, 5)),
        (sum(c) for c in itertools.combinations(ns, 4)),
        (sum(c) for c in itertools.combinations(ns, 3)),
        (sum(c) for c in itertools.combinations(ns, 2)),
        (sum(c) for c in itertools.combinations(ns, 1)))

while True:
    seq = [random.randint(1,13) for i in range(5)]
    if unique(combinations(seq)):
        print(seq, combinations(seq))
        break
