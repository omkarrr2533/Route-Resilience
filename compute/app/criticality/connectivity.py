"""Single points of failure: articulation points and bridges (Tarjan, linear time).

These are the cheap, exact, immediately-actionable half of criticality. An articulation
point is a junction whose removal splits the network; a bridge is a road segment whose
removal does the same. Unlike betweenness they are not a ranking — they are a hard yes/no
on "does the city fall apart without this" — which is exactly what a planner wants flagged
first.

Connectivity is an undirected notion, so callers should pass the undirected projection of
the road graph (see graph.build.undirected_view). The DFS is written iteratively: Bengaluru
drive networks are tens of thousands of nodes deep along arterials and Python's recursion
limit will happily blow up on the recursive textbook version.
"""

from __future__ import annotations

from itertools import count


def articulation_points_and_bridges(G):
    """Return (articulation_points: set, bridges: list of (u, v)).

    Standard low-link DFS: ``disc[v]`` is discovery time, ``low[v]`` is the earliest
    discovery time reachable from v's subtree via at most one back edge. A non-root v is
    an articulation point when some child c has ``low[c] >= disc[v]`` (the subtree can't
    escape above v); the edge (v, c) is a bridge when ``low[c] > disc[v]`` (it can't even
    reach v itself by another route). The DFS root is special-cased on its child count.
    """
    disc = {}
    low = {}
    timer = count()

    articulation = set()
    bridges = []

    for root in G.nodes():
        if root in disc:
            continue
        root_children = 0

        # Each stack frame carries an iterator over the node's neighbours so we can
        # "pause" a node, descend, and resume exactly where we left off.
        stack = [(root, None, iter(G[root]))]
        disc[root] = low[root] = next(timer)

        while stack:
            v, parent, neighbours = stack[-1]
            advanced = False

            for w in neighbours:
                if w == parent:
                    continue
                if w not in disc:
                    if parent is None:
                        root_children += 1
                    disc[w] = low[w] = next(timer)
                    stack.append((w, v, iter(G[w])))
                    advanced = True
                    break                       # descend into w before touching siblings
                else:
                    low[v] = min(low[v], disc[w])  # back edge

            if advanced:
                continue

            # Done with v: fold its low-link into its parent and test the parent.
            stack.pop()
            if parent is not None:
                low[parent] = min(low[parent], low[v])
                if stack and stack[-1][1] is not None and low[v] >= disc[parent]:
                    articulation.add(parent)
                if low[v] > disc[parent]:
                    bridges.append((parent, v))

        if root_children > 1:
            articulation.add(root)              # root splits iff it has 2+ DFS subtrees

    return articulation, bridges


def k_edge_components(G, k):
    """Thin wrapper for redundancy queries ("which corridors survive k cuts?").

    We lean on NetworkX here on purpose: a correct, general k-edge-connectivity routine is
    a lot of machinery for marginal resume value, whereas Brandes and Tarjan above are the
    parts worth owning by hand. Returns a list of node sets.
    """
    import networkx as nx

    return [set(c) for c in nx.k_edge_components(G, k)]
