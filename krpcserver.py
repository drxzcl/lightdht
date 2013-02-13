import threading
import socket
import time
import struct
import logging
import traceback

from bencode import bencode, bdecode
from BTL import BTFailure

# Our version string!
version = 'XN\x00\x00'

# Logging is disabled by default.
# See http://docs.python.org/library/logging.html
logger = logging.getLogger(__name__)
#logger.addHandler(logging.NullHandler())

class KRPCTimeout(RuntimeError):
    """
        This exception is raised whenever a KRPC request times out
        in synchronous mode.
    """
    pass

class KRPCError(RuntimeError):
    pass

class KRPCServer(object):

    def __init__(self, port):
        self._port = port
        self._shutdown_flag = False
        self._thread = None
        self._sock = None
        self._transaction_id = 0
        self._transactions = {}
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
                            node = self._transactions[t][1]
                            node.trep = time.time()
                            if t in node.t:
                                node.t.remove(t)
                            if self._transactions[t][0] is not None:
                                self._transactions[t][0](rec, node) # invoke the callback
                            else:
                                self._results[t] = rec # sync path
                            del self._transactions[t]
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
                                del self._transactions[t]
                            self._results[t] = rec
                    else:
                        # log it
                        logger.warning("Node %r reported error %r, but did "
                                       "not specify a 't'" % (c,rec))
                else:
                    raise RuntimeError,"Unknown KRPC message %r from %r" % (rec,c)

                # Scrub the transaction list
                t1 = time.time()
                for tid,(cb,node) in self._transactions.items():
                    if t1-node.treq > 10.0:
                        with self._transactions_lock:
                            if tid in self._transactions:
                                del self._transactions[tid]


            except socket.timeout:
                # no packets, that's ok
                pass
            except BTFailure:
                # bdecode error, ignore the packet
                pass
            except:
                # Log and carry on to keep the packet pump alive.
                logger.critical("Exception while handling KRPC requests:\n\n"+traceback.format_exc()+("\n\n%r from %r" % (rec,c)))


    def send_krpc(self, req , node,callback=None):
        """
            Perform a KRPC request
        """
        logger.debug("KRPC request to %r", node.c)
        t = -1
        if "t" not in req:
            # add transaction id
            with self._transactions_lock:
                self._transaction_id += 1
                t = struct.pack("i",self._transaction_id)
            req["t"] = t
        else:
            t = req["t"]
        req["v"] = version
        data = bencode(req)
        self._transactions[t] = callback, node
        node.treq = time.time()
        node.t.add(t)

        self._sock.sendto(data, node.c)
        return t

    def send_krpc_reply(self, resp, connect_info):
        """
           Bencode and send a reply to a KRPC client
        """
        logger.info("REPLY: %r %r" % (connect_info, resp))

        data = bencode(resp)
        self._sock.sendto(data,connect_info)

    def _synctrans(self, q, node):
        """
            Perform a synchronous transaction.
            Used by the KRPC methods below
        """
        # We fake a syncronous transaction by sending
        # the request, then waiting for the server thread
        # to post the results of our transaction into
        # the results dict.
        t = self.send_krpc(q, node)
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


    def ping(self,id_,node):
        q = { "y":"q", "q":"ping", "a":{"id":id_}}
        return self._synctrans(q, node)

    def find_node(self, id_,node, target):
        q = { "y":"q", "q":"find_node", "a":{"id":id_,"target":target}}
        return self._synctrans(q, node)

    def get_peers(self, id_,node, info_hash):
        q = { "y":"q", "q":"get_peers", "a":{"id":id_,"info_hash":info_hash}}
        return self._synctrans(q, node)

    def announce_peer(self, id_,node, info_hash, port, token):
        # We ignore "name" and "seed" for now as they are not part of BEP0005
        q = {'a': {
            #'name': '',
            'info_hash': info_hash,
            'id': id_,
            'token': token,
            'port': port},
             'q': 'announce_peer', 'y': 'q'}
        return self._synctrans(q, node)