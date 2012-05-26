"""
LightDHT - A lightweight python implementation of the Bittorrent distributed
           hashtable.


The aim of LightDHT is to provide a simple, flexible implementation of the
Bittorrent DHT for use in research applications. If you want to trade files,
you have come to the wrong place. LightDHT does not implement the actual
file transfer parts of the bittorrent protocol. It only takes part in the
DHT.


Philosophy:
 
 - Ease of use over performance
 - Adaptability over scalability

In order to keep LightDHT easy to use, all DHT RPC calls are performed
synchronously. This means that when you call a DHT method, your program will
block until you have an answer to your request. That answer will be the
return value of the function. This has the advantage that it keeps the
logical program flow intact, and makes it more comfortable to use.

In order to maintain O(log N) scaling across the network, BEP0005 (the
standard governing the DHT) mandates that implementations use a bucket-based
approach to the routing table. This enables the node to fulfill all requests
in constant time and (more or less) constant memory. In LightDHT, we throw 
that recommendation to the wind.

Since the main focus of LightDHT is reseach, we are going to keep around all
the data we can. This means that we keep around every single node we know
about. Since in practice the number of nodes is limited and the request
rates are rather low, we do not bother keeping the routing table organized
in a tree structure for quick lookups. Instead we keep it in a dictionary
and sort on-demand. The performance penalty is well worth the reduced 
complexity of the implementation, and the flexibility of having all nodes in
an easy to use data structure.

"""

import socket
import sys
import time
import hashlib
import struct
import threading 
import traceback
import logging

from bencode import bencode, bdecode
from BTL import BTFailure

# Logging is disabled by default.
# See http://docs.python.org/library/logging.html
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


#
# Utility functions

def dottedQuadToNum(ip):
    "convert decimal dotted quad string to long integer"

    hexn = ''.join(["%02X" % long(i) for i in ip.split('.')])
    return long(hexn, 16)

def numToDottedQuad(n):
    "convert long int to dotted quad string"
    
    d = 256 * 256 * 256
    q = []
    while d > 0:
        m,n = divmod(n,d)
        q.append(str(m))
        d = d/256

    return '.'.join(q)

def strxor(a, b):     
    """ xor two strings of different lengths """
    if len(a) > len(b):
        return "".join([chr(ord(x) ^ ord(y)) for (x, y) in zip(a[:len(b)], b)])
    else:
        return "".join([chr(ord(x) ^ ord(y)) for (x, y) in zip(a, b[:len(a)])])

def decode_nodes(nodes):
    """ Decode node_info into a list of id, connect_info """
    nrnodes = len(nodes)/26
    nodes = struct.unpack("!" + "20sIH"*nrnodes,nodes)
    for i in xrange(nrnodes):
        id_, ip, port = nodes[i*3], numToDottedQuad(nodes[i*3+1]), nodes[i*3+2]
        yield id_,(ip, port)

def encode_nodes(nodes):
    """ Encode a list of (id, connect_info) pairs into a node_info """
    n = []
    for node in nodes:
        n.extend([node[0], dottedQuadToNum(node[1][0]),node[1][1]])
    return struct.pack("!" + "20sIH"*len(nodes),*n)



class KRPCTimeout(RuntimeError):
    """
        This exception is raised whenever a KRPC request times out
        in synchronous mode.
    """
    pass

class KRPCError(RuntimeError):
    pass


class KRPCServer(object):

    def __init__(self, port,id_):
        self._port = port
        self._id = id_
        self._shutdown_flag = False
        self._thread = None
        self._sock = None
        self._transaction_id = 0       
        self._transactions = set()
        self._transactions_lock = threading.Lock()
        self._results = {}
        self.handler = self.default_handler

    def default_handler(self, req, c):
        """
            Default incoming KRPC request handler.
            Gets replaces by application specific code.
        """
        print req
                

    def start(self):
        """
            Start the KRPC server
        """
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)        
        self._sock.settimeout(0.5)
        self._sock.bind( ("0.0.0.0",self._port) )
        self._thread = threading.Thread(target=self._pump)
        self._thread.daemon = True
        self._thread.start()
        
    def shutdown(self):
        """
            Shut down the KRPC server
        """
        self._shutdown_flag = True
        self._thread.join()

    def _pump(self):
        """
            Thread that processes incoming datagrams
        """
        # Listen and react
        while True:
            if self._shutdown_flag:
                break
            rec = {}
            try:        
                rec,c = self._sock.recvfrom(4096)
                rec = bdecode(rec)
                if rec["y"] == "r": 
                    # It's a reply.
                    # Remove the transaction id from the list of pending
                    # transactions and add the result to the result table.
                    # The client thread will take it from there.
                    t = rec["t"]
                    with self._transactions_lock:
                        if t in self._transactions:
                            self._transactions.remove(t)
                        self._results[t] = rec
                elif rec["y"] == "q":
                    # It's a request, send it to the handler.
                    self.handler(rec,c)
                elif rec["y"] == "e":
                    # just post the error to the results array,  but only if
                    # we have a transaction ID!
                    # Some software (e.g. LibTorrent) does not post the "t"
                    if "t" in rec:
                        t = rec["t"]
                        with self._transactions_lock:
                            if t in self._transactions:
                                self._transactions.remove(t)
                            self._results[t] = rec
                    else:
                        # log it
                        logger.warning("Node %r reported error %r, but did "
                                        "not specify a 't'" % (c,rec))
                else:
                    raise RuntimeError,"Unknown KRPC message %r from %r" % (rec,c)
                    
            except socket.timeout:
                # no packets, that's ok
                pass
            except BTFailure:
                # bdecode error, ignore the packet
                pass
            except:
                # Log and carry on to keep the packet pump alive.
                logger.critical("Exception while handling KRPC requests:\n\n"+traceback.format_exc()+("\n\n%r from %r" % (rec,c)))
                

    def send_krpc(self, req ,connect_info):
        """
            Perform a KRPC request
        """
        logger.debug("KRPC request to %r", connect_info)
        t = -1
        if "t" not in req:
            # add transaction id
            with self._transactions_lock:
                self._transaction_id += 1
                t = struct.pack("i",self._transaction_id)
            req["t"] = t
        else:
            t = req["t"]
        data = bencode(req)
        self._transactions.add(t)
        self._sock.sendto(data, connect_info)
        return t
        
    def send_krpc_reply(self, resp, connect_info):
        """
           Bencode and send a reply to a KRPC client
        """
        data = bencode(resp)
        self._sock.sendto(data,connect_info)

    def _synctrans(self, q, connect_info):
        """
            Perform a synchronous transaction.
            Used by the KRPC methods below
        """
        # We fake a syncronous transaction by sending
        # the request, then waiting for the server thread
        # to post the results of our transaction into
        # the results dict.
        t = self.send_krpc(q, connect_info)
        dt = 0
        while t not in self._results:
            time.sleep(0.1)                
            dt+=0.1
            if dt > 5.0:                
                raise KRPCTimeout
                        
        # Retrieve the result
        r = self._results[t]
        del self._results[t]
        
        if r["y"]=="e":
            # Error condition!
            raise KRPCError, "Error %r while processing transaction %r" % (r,q)
         
        return r["r"]
        
            
    def ping(self,c):
        q = { "y":"q", "q":"ping", "a":{"id":self._id}}        
        return self._synctrans(q, c)        
        
    def find_node(self, c, id_):
        q = { "y":"q", "q":"find_node", "a":{"id":self._id,"target":id_}}
        return self._synctrans(q, c)
        
    def get_peers(self, connect_info, info_hash):
        q = { "y":"q", "q":"get_peers", "a":{"id":self._id,"info_hash":info_hash}}
        return self._synctrans(q, connect_info)
        

class NotFoundError(RuntimeError):
    pass
        
class DHT(object):
    def __init__(self, port, id_):    
        self._id = id_
        self._server = KRPCServer(port,self._id)
        
        # This is our routing table.
        # We don't do any bucketing or anything like that, we just
        # keep track of all the nodes we know about.
        # This gives us significant memory overhead over a bucketed
        # implementation and ruins the logN scaling behaviour of the DHT.
        # We don't care ;)
        
        self._nodes = {}
        self._nodes_lock = threading.Lock()
        self._bad = set()

        # Thread details
        self._shutdown_flag = False
        self._thread = None   

        

    def start(self):
        """
            Start the DHT node
        """
        self._server.start()
        self._server.handler = self._handler

        # Add the default nodes
        DEFAULT_CONNECT_INFO = (socket.gethostbyaddr("router.bittorrent.com")[2][0], 6881)
        DEFAULT_ID = self._server.ping(DEFAULT_CONNECT_INFO)['id']
        with self._nodes_lock:
            self._nodes[DEFAULT_ID] = DEFAULT_CONNECT_INFO

        # Start our event thread
        self._thread = threading.Thread(target=self._pump)
        self._thread.daemon = True
        self._thread.start()        
        

    def shutdown(self):
        self._server.shutdown()
                
    def __enter__(self):
        self.start()

    def __exit__(self, type, value, traceback):
        self.shutdown()
                
    def _pump(self):
        """
            Thread that maintains DHT connectivity and does 
            routing table housekeeping.
            Started by self.start()
            
            The very first thing this function does, is look up itself
            in the DHT. This connects it to neighbouring nodes and enables
            it to give reasonable answers to incoming queries. 
            
            Afterward we look up random nodes to increase our connectedness
            and gather information about the DHT as a whole            
            
        """
        # Try to establish links to close nodes
        logger.info("Establishing connections to DHT")
        target = self._id
        
        iteration = 0
        while True:
            try:
                self.find_node(target)
                logger.info("Tracing done, routing table contains %d nodes", len(self._nodes))
                time.sleep(10)
                iteration += 1
                target = hashlib.sha1("this is my salt 2348724" + str(iteration)+self._id).digest()
                if iteration % 10 == 0:
                    target = self._id
            except:
                # This loop should run forever. If we get into trouble, log
                # the exception and carry on.
                logger.critical("Exception in DHT maintenance thread:\n\n"+traceback.format_exc())


    def get_close_nodes(self,target, N=3): 
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
            raise RuntimeError, "No nodes in routing table!"
        
        # Sort the entire routing table by distance to the target
        # and return the top N matches
        with self._nodes_lock:
            nodes = [(node_id,self._nodes[node_id]) for node_id in self._nodes]        
        nodes.sort(key=lambda x:strxor(target,x[0]))
        return nodes[:N]          


    def _recurse(self, target, function, max_attempts=10, result_key=None):
        """
            Recursively query the DHT, following "nodes" replies
            until we hit the desired key
            
            This is the workhorse function used by all recursive queries.
        """
        logger.info("Recursing to target %r" % target.encode("hex"))
        attempts = 0
        while attempts < max_attempts:
            for id_, c in self.get_close_nodes(target):
                try:
                    r = function(c,target)
                    logger.debug("Results from %r ", c)# d.encode("hex"))
                    attempts += 1                
                    if result_key and result_key in r:
                        return r[result_key]
                    if "nodes" in r:
                        # we have nodes that could be closer.
                        # Add them to the routing table and go again!
                        for node_id,node_c in decode_nodes(r["nodes"]):
                            if node_c not in self._bad:
                                with self._nodes_lock:
                                    self._nodes[node_id] = node_c
                except KRPCTimeout:
                    # The node did not reply.
                    # Blacklist it.
                    with self._nodes_lock:
                        self._bad.add(c)
                        del self._nodes[id_]
                except KRPCError:
                    # Sometimes we just flake out due to UDP being unreliable
                    # Don't sweat it, just log and carry on.
                    logger.error("KRPC Error:\n\n"+traceback.format_exc())
                    
                    
        if result_key:
            # We were expecting a result, but we did not find it!
            # Raise the NotFoundError exception instead of returning None
            raise NotFoundError

    def find_node(self, target, attempts = 10):
        """ 
            Recursively call the find_node function to get as
            close as possible to the target node 
        """
            
        logger.info("Tracing to %r" % target.encode("hex"))
        self._recurse(target,self._server.find_node, max_attempts=attempts)        

    def get_peers(self,info_hash,attempts=10):
        """ 
            Recursively call the get_peers function to fidn peers
            for the given info_hash
        """
        logger.info("Finding peers for %r" % info_hash.encode("hex"))
        return self._recurse(info_hash,self._server.get_peers, result_key="values",max_attempts=attempts)        

    def _handler(self,rec,c):
        """
            Process incoming requests
        """
        logger.info("Received request %r from %r" % (rec,c))
        # Use the request to update teh routing table
        with self._nodes_lock:
            self._nodes[rec["a"]["id"]] = c
        # Skeleton response
        resp = {"y":"r","t":rec["t"],"r":{}}
        if rec["q"] == "ping":
            resp["r"]["id"] = self._id
            self._server.send_krpc_reply(resp,c)
        elif rec["q"] == "find_node":
            target = rec["a"]["target"]
            resp["r"]["nodes"] = encode_nodes(self.get_close_nodes(target))
            self._server.send_krpc_reply(resp,c)
        elif rec["q"] == "get_peers":
            # We don't keep any peer administration, just return
            # other (closer?) nodes.
            # we don't supply a token, which should prevent announces.
            info_hash = rec["a"]["info_hash"]
            resp["r"]["nodes"] = encode_nodes(self.get_close_nodes(info_hash))
            self._server.send_krpc_reply(resp,c)
        else:
            raise RuntimeError,"Unknown request in query %r" % rec

if __name__ == "__main__":            

    # Enable logging:
    # Tell the module's logger to log at level DEBUG
    logger.setLevel(logging.DEBUG)     
    # Create a handler, tell it to log at level INFO on stdout
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    # Add the handler
    logger.addHandler(handler)

    # Create a DHT node.
    dht1 = DHT(port=54767, id_=hashlib.sha1(
            "Change this to avoid getting ID clashes").digest()) 
    # Start it!
    with dht1:
        # Look up peers that are sharing one of the Ubuntu 12.04 ISO torrents
        print dht1.get_peers("8ac3731ad4b039c05393b5404afa6e7397810b41".decode("hex"))   
        # Go to sleep and let the DHT service requests.
        while True:
            time.sleep(1)


