#!/usr/bin/env python3
"""
Decentralized sector-claiming agent (one instance per UAV, no shared state).

Each UAV keeps only what it has actually heard:
  * a table of peers (last advertised position, committed EW-CVT generator and weight, state),
  * the set of sectors it knows to be scanned (grow-only; merged on contact),
  * the sector claims each peer last advertised, with the planned arrival time (ETA) of each.

Beacons carry exactly this information and are exchanged over the lossy RF link, so in a sparse
swarm most of them are lost and views go stale. Everything below is therefore written to tolerate
stale, partial information:

  * Claims are *leases*: a peer advertises when its route should bring it home. If it is still
    missing `slack` seconds after that, it is *suspected* lost and its claims are released. This is
    the failure detector. Silence alone is not a signal, because the mesh is mostly
    disconnected in flight. A suspicion can be wrong (the peer was only out of range); the cost is
    duplicate scanning, which the simulator measures.
  * Conflicts (two UAVs holding the same sector) are resolved by weighted distance
    ||c_s - g_i||^2 / w_i on the *advertised* generators and weights, ties broken by id. The UAV that
    sees both claims and loses yields. Every UAV applies the same rule, so views converge on contact.
  * A UAV that has nothing left claims the nearest unclaimed sector (work stealing), so orphaned
    work is always eventually picked up.
"""
import math

INACTIVE = ("LANDED", "RTL", "CRASHED")


class SwarmAgent:
    def __init__(self, uid, peer_ids, centers, failover=True):
        self.id = str(uid)
        self.centers = centers                     # sector_id -> (x, y); the map is known a priori
        self.failover = failover
        self.peers = {str(j): {"x": 0.0, "y": 0.0, "gen": (0.0, 0.0), "w": 1.0,
                               "state": "TRANSIT", "heard": 0.0, "ret": None, "suspected": False}
                      for j in peer_ids if str(j) != self.id}
        self.peer_claims = {j: {} for j in self.peers}   # peer -> {sector: eta}
        self.scanned = set()
        self.mine = {}                             # my claims: sector -> eta (None until routed)
        self.abandoned = set()                     # sectors released by suspected peers
        self.stats = {"suspicions": 0, "restores": 0, "yields": 0, "adopted": 0, "steals": 0}

    # ---------------------------------------------------------------- messages
    def beacon(self, x, y, gen, w, state, ret=None):
        return {"id": self.id, "x": x, "y": y, "gen": tuple(gen), "w": w, "state": state, "ret": ret,
                "claims": dict(self.mine), "scanned": frozenset(self.scanned)}

    def receive(self, b, now):
        j = b["id"]
        p = self.peers.get(j)
        if p is None:
            return
        if p["suspected"]:
            p["suspected"] = False
            self.stats["restores"] += 1
        p.update(x=b["x"], y=b["y"], gen=tuple(b["gen"]), w=b["w"], state=b["state"], ret=b.get("ret"), heard=now)
        self.peer_claims[j] = dict(b["claims"])
        self.scanned |= b["scanned"]
        for s in [s for s in self.mine if s in self.scanned]:
            del self.mine[s]

    def mark_scanned(self, sid):
        self.scanned.add(sid)
        self.mine.pop(sid, None)

    # ---------------------------------------------------------------- failure detection
    def expire(self, now, slack):
        """Suspect every peer that is overdue back at base.

        A peer advertises when its route should bring it home (`ret`). Silence before that is
        expected (the mesh is mostly disconnected in flight) and says nothing. A peer still
        missing slack seconds after its advertised return is presumed lost, and its claims are
        released for the others to take."""
        out = []
        for j, p in self.peers.items():
            if p["suspected"] or p["state"] in INACTIVE or p["ret"] is None:
                continue
            if now > p["ret"] + slack:
                p["suspected"] = True
                self.stats["suspicions"] += 1
                self.abandoned |= {s for s in self.peer_claims[j] if s not in self.scanned}
                self.peer_claims[j] = {}
                out.append(j)
        return out

    def active_peers(self, include_landed=False):
        """Peers believed to be available for planning. Peers last seen landed are normally out,
        but a UAV that is itself at base shares the pad with them and plans with them."""
        skip = ("RTL", "CRASHED") if include_landed else INACTIVE
        return [j for j, p in self.peers.items() if not p["suspected"] and p["state"] not in skip]

    # ---------------------------------------------------------------- claiming
    def assign(self, pos, gen, w, speed, end_pos, end_eta, at_base=False, margin=30.0):
        """Recompute my claims from my own view. Returns the new claim set.

        end_pos / end_eta: where and when my current route finishes, used to check that I would
        reach a sector long before the peer that currently claims it (so taking it cannot cause a
        duplicate scan even if the peer never hears about it).

        Work released by suspected peers (`abandoned`) is only taken by a UAV that is at base: in
        flight a UAV cannot tell a lost peer from one that landed and went quiet, and acting on that
        guess makes it redo the whole swarm's finished work."""
        A = {self.id: (gen, w)}
        for j in self.active_peers(include_landed=at_base):
            A[j] = (self.peers[j]["gen"], self.peers[j]["w"])

        def cost(j, s):
            cx, cy = self.centers[s]
            gx, gy = A[j][0]
            return (((cx - gx) ** 2 + (cy - gy) ** 2) / max(0.01, A[j][1]), j)

        pool = [s for s in self.centers if s not in self.scanned
                and (self.failover or s not in self.abandoned)]
        pool_set = set(pool)
        claimant, c_eta = {}, {}
        for j in self.active_peers():
            for s, eta in self.peer_claims[j].items():
                if s in pool_set and (s not in claimant or cost(j, s) < cost(claimant[s], s)):
                    claimant[s], c_eta[s] = j, eta

        def my_eta(s):
            return end_eta + math.hypot(self.centers[s][0] - end_pos[0], self.centers[s][1] - end_pos[1]) / speed

        new = {}
        for s in list(self.mine):                       # keep what I hold unless a better claim beats it
            if s not in pool_set:
                continue
            j = claimant.get(s)
            if j is None or cost(self.id, s) < cost(j, s):
                new[s] = self.mine[s]
            else:
                self.stats["yields"] += 1
        for s in pool:                                  # take sectors I am the preferred owner of
            if s in new or (s in self.abandoned and not at_base):
                continue
            if min(A, key=lambda k: cost(k, s)) != self.id:
                continue
            j = claimant.get(s)
            if j is None:
                new[s] = None
            elif cost(self.id, s) < cost(j, s) and c_eta[s] is not None and my_eta(s) + margin < c_eta[s]:
                new[s] = None                           # I will certainly get there first
        if not new:                                     # idle: pick up leftover work
            def near(s):
                return math.hypot(self.centers[s][0] - pos[0], self.centers[s][1] - pos[1])
            if at_base:
                # Everyone on the pad shares the released work by the same power-distance rule.
                B = {k: v for k, v in A.items() if k == self.id or self.peers[k]["state"] == "LANDED"}
                for s in pool:
                    if s in self.abandoned and min(B, key=lambda k: cost(k, s)) == self.id:
                        new[s] = None
            else:
                left = [s for s in pool if s not in claimant and s not in self.abandoned]
                if left:
                    new[min(left, key=near)] = None
            if new:
                self.stats["steals"] += 1
        for s in new:
            if s in self.abandoned:
                self.abandoned.discard(s)
                self.stats["adopted"] += 1
        self.mine = new
        return new
