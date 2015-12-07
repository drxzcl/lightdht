import collections
import threading
import random
import time


def strxor(a, b):
    """ xor two strings of different lengths """
    if len(a) > len(b):
        return bytes([(x ^ y) for (x, y) in zip(a[:len(b)], b)])
    else:
        return bytes([(x ^ y) for (x, y) in zip(a[:len(b)], b)])
        #return "".join([chr(ord(x) ^ ord(y)) for (x, y) in zip(a, b[:len(a)])])


class RoutingTable(object):
    def update_entry(self, node_id, node):
        raise NotImplemented

    def get_close_nodes(self, target, N=3):
        raise NotImplemented

    def remove_node(self, node_id):
        raise NotImplemented

    def bad_node(self, node_id, node):
        raise NotImplemented

    def node_count(self):
        raise NotImplemented

    def sample(self, id_, N, prefix_bytes=1):
        raise NotImplemented


# This is our routing table.
# We don't do any bucketing or anything like that, we just
# keep track of all the nodes we know about.
# This gives us significant memory overhead over a bucketed
# implementation and ruins the logN scaling behaviour of the DHT.
# We don't care ;)
class FlatRoutingTable(RoutingTable):
    def __init__(self):
        self._nodes = {}
        self._nodes_lock = threading.Lock()
        self._bad = set()

    def update_entry(self, node_id, node):
        if node not in self._bad:
            with self._nodes_lock:
                self._nodes[node_id] = node

    def get_close_nodes(self, target, N=3):
        """
            Find the N nodes in the routing table closest to target

            We do this by brute force: we compute the distance of the
            target node to all the nodes in the routing table.
            A bucketing system would speed things up considerably, and
            require less memory.
            However, we like to keep as many nodes as possible in our routing
            table for research purposes.
        """

        # If we have no known nodes, exception!
        if len(self._nodes) == 0:
            raise RuntimeError("No nodes in routing table!")

        # Sort the entire routing table by distance to the target
        # and return the top N matches
        with self._nodes_lock:
            nodes = [(node_id, self._nodes[node_id]) for node_id in self._nodes]
        nodes.sort(key=lambda x: strxor(target, x[0]))
        return nodes[:N]

    def remove_node(self, node_id):
        with self._nodes_lock:
            if node_id in self._nodes:
                del self._nodes[node_id]

    def bad_node(self, node_id, node):
        self.remove_node(node_id)
        self._bad.add(node)

    def node_count(self):
        return len(self._nodes)

    def sample(self, id_, N, prefix_bytes=1):
        with self._nodes_lock:
            return random.sample([(k, v) for k, v in list(self._nodes.items()) if k[:prefix_bytes] == id_[:prefix_bytes]], N)


class PrefixRoutingTable(RoutingTable):
    def __init__(self, prefix_bytes=1):
        self._nodes = collections.defaultdict(dict)
        self._nodes_lock = threading.Lock()
        self._bad = set()
        self._prefix_bytes = prefix_bytes

    def update_entry(self, node_id, node):
        if node not in self._bad:
            with self._nodes_lock:
                self._nodes[node_id[:self._prefix_bytes]][node_id] = node

    def get_close_nodes(self, target, N=3):
        with self._nodes_lock:
            p = min(list(self._nodes.keys()), key=lambda x: abs(x[0] ^ target[0]))
            ids = sorted(self._nodes[p], key=lambda x: strxor(x, target))[:8]
            return [(id, self._nodes[p][id]) for id in ids]

    def remove_node(self, node_id):
        with self._nodes_lock:
            if node_id in self._nodes[node_id[:self._prefix_bytes]]:
                del self._nodes[node_id[:self._prefix_bytes]][node_id]

    def bad_node(self, node_id, node):
        self.remove_node(node_id)
        self._bad.add(node)

    def node_count(self):
        t = 0
        for p in self._nodes:
            t+=len(self._nodes[p])
        return t

    def sample(self, id_, N, prefix_bytes=1):
        # Only support matching prefixes for now
        if prefix_bytes != self._prefix_bytes:
            raise ValueError("Expected prefix_bytes:%d, got %d" % (self._prefix_bytes, prefix_bytes))
        with self._nodes_lock:
            return random.sample(list(self._nodes[id_[:prefix_bytes]].items()), N)

    def _random_node(self,prefix, outstanding=False):
        """
            Get a random node from this prefix bucket.
            if it's empty, grab any old node
        """

        N = 3 # choice between N eligible closest nodes
        nlist = []
        for p in sorted(list(self._nodes.keys()), key = lambda x: abs(ord(x) ^ ord(prefix))):
            if len(nlist) >= N:
                break
            for k,v in list(self._nodes[p].items()):
                if (v.treq > v.trep) and not outstanding: # outstanding requests
                    continue
                nlist.append((k,v))
                if len(nlist) >= N:
                    break

        if not nlist:
            # try again with pending nodes too
            return self._random_node(prefix, True)

        return random.choice(nlist)

    def cleanup (self, timeout):
        abandoned_transactions = []
        for prefix in list(self._nodes.keys()):
            for k,v in list(self._nodes[prefix].items()):
                # outstanding request and request older than timeout
                if (v.treq - v.trep) > 0 and (time.time() - v.treq) > timeout:
                    # Node is bad
                    with self._nodes_lock:
                        if k in self._nodes[prefix]:
                            for tid in self._nodes[prefix][k].t:
                                abandoned_transactions.append(tid)
                            del self._nodes[prefix][k]
                        self._bad.add(v.c)
        return abandoned_transactions