"""Bottleneck criticality: max-flow / min-cut between two zones (Dinic's algorithm).

Centrality asks "how central is this road"; max-flow asks a sharper, more operational
question: "how many vehicles per hour can actually get from A to B, and which segments are
the wall that caps it?" By the max-flow/min-cut theorem the answer to the second is the
min-cut — the cheapest set of edges whose removal severs A from B — and those edges are the
*literal* bottlenecks a planner should widen or protect.

We model the road network as a flow network with per-segment capacity (vehicles/hour by
class), tie every source-zone node to a synthetic super-source and every sink-zone node to a
super-sink, and run Dinic. Dinic is the right tool here — O(V^2 E) worst case but near-linear
on the sparse, unit-ish graphs roads produce — and implementing it by hand is the point: this
is the competitive-programming core of the bottleneck analysis.

Undirected roads are modelled as a capacity-`c` arc in each direction that share a residual
(pushing flow one way frees capacity the other), which is the standard undirected-max-flow
construction.
"""

from __future__ import annotations

from collections import deque

EPS = 1e-9


class Dinic:
    """Max-flow on a residual network. Edges are stored in reverse-paired slots (i, i^1) so an
    arc and its residual reverse are found by flipping the low bit of the index."""

    def __init__(self, n):
        self.n = n
        self.to = []
        self.cap = []
        self.adj = [[] for _ in range(n)]

    def add_edge(self, u, v, cap, rcap=0.0):
        """Add arc u->v of capacity `cap`; its reverse v->u starts at `rcap` (use rcap=cap for
        an undirected edge, 0 for a directed one)."""
        self.adj[u].append(len(self.to)); self.to.append(v); self.cap.append(cap)
        self.adj[v].append(len(self.to)); self.to.append(u); self.cap.append(rcap)

    def _bfs(self, s, t):
        self.level = [-1] * self.n
        self.level[s] = 0
        q = deque([s])
        while q:
            u = q.popleft()
            for i in self.adj[u]:
                if self.cap[i] > EPS and self.level[self.to[i]] < 0:
                    self.level[self.to[i]] = self.level[u] + 1
                    q.append(self.to[i])
        return self.level[t] >= 0

    def _dfs(self, u, t, pushed):
        if u == t:
            return pushed
        while self.it[u] < len(self.adj[u]):
            i = self.adj[u][self.it[u]]
            v = self.to[i]
            if self.cap[i] > EPS and self.level[v] == self.level[u] + 1:
                d = self._dfs(v, t, min(pushed, self.cap[i]))
                if d > EPS:
                    self.cap[i] -= d
                    self.cap[i ^ 1] += d   # return capacity to the reverse arc
                    return d
            self.it[u] += 1                # this arc is exhausted for this phase
        return 0.0

    def max_flow(self, s, t):
        flow = 0.0
        while self._bfs(s, t):             # build a fresh level graph each phase
            self.it = [0] * self.n
            while True:
                pushed = self._dfs(s, t, float("inf"))
                if pushed <= EPS:
                    break
                flow += pushed
        return flow

    def reachable_from(self, s):
        """Nodes still reachable from s in the residual graph — the source side of the min-cut."""
        seen = [False] * self.n
        seen[s] = True
        q = deque([s])
        while q:
            u = q.popleft()
            for i in self.adj[u]:
                if self.cap[i] > EPS and not seen[self.to[i]]:
                    seen[self.to[i]] = True
                    q.append(self.to[i])
        return seen


def min_cut_between(U, sources, sinks, capacity="capacity"):
    """Max-flow value and the min-cut edges between two node sets on undirected graph `U`.

    `sources`/`sinks` are node ids. Returns the flow (veh/h), the cut edges with their
    capacities, and the source-side partition. Nodes appearing in both sets are ignored.
    """
    sources = [n for n in dict.fromkeys(sources) if n in U]
    sinks = set(n for n in sinks if n in U)
    sources = [n for n in sources if n not in sinks]
    if not sources or not sinks:
        return {"max_flow": 0.0, "cut_edges": [], "source_side": [], "reason": "empty zone"}

    idx = {n: i for i, n in enumerate(U.nodes())}
    S, T = len(idx), len(idx) + 1
    dinic = Dinic(len(idx) + 2)

    total_cap = 0.0
    road_arcs = []                          # (u, v, forward_arc_index, capacity)
    for u, v, data in U.edges(data=True):
        c = float(data.get(capacity, 1.0))
        total_cap += c
        fi = len(dinic.to)
        dinic.add_edge(idx[u], idx[v], c, c)
        road_arcs.append((u, v, fi, c))

    inf = total_cap + 1.0                   # super-source/sink arcs must never bind the cut
    for n in sources:
        dinic.add_edge(S, idx[n], inf)
    for n in sinks:
        dinic.add_edge(idx[n], T, inf)

    flow = dinic.max_flow(S, T)
    reach = dinic.reachable_from(S)

    # A road edge is in the min-cut iff exactly one endpoint stays reachable in the residual.
    cut = []
    for u, v, _fi, c in road_arcs:
        if reach[idx[u]] != reach[idx[v]]:
            cut.append({"u": u, "v": v, "capacity": round(c, 1)})

    source_side = [n for n in U.nodes() if reach[idx[n]]]
    return {
        "max_flow": round(flow, 1),
        "cut_edges": cut,
        "cut_size": len(cut),
        "source_side": source_side,
    }
