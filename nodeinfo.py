"""
    Basic program to show the useage of lightdht.
    
    We run a dht node and log all incoming queries.
"""
import logging
import time
import os

from . import lightdht


# Enable logging:
loglevel = logging.DEBUG
req_handler = logging.StreamHandler(open("incoming-requests.log","a"))
req_handler.setLevel(loglevel)
formatter = logging.Formatter("[%(levelname)s@%(created)s] %(message)s")
req_handler.setFormatter(formatter)
stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(formatter)
logging.getLogger("krpcserver").setLevel(loglevel)
logging.getLogger("krpcserver").addHandler(req_handler)
logging.getLogger("krpcserver").addHandler(stdout_handler)
logging.getLogger("lightdht").setLevel(loglevel)
logging.getLogger("lightdht").addHandler(req_handler)
logging.getLogger("lightdht").addHandler(stdout_handler)

# Create a DHT node.
id_ = os.urandom(20)
dht = lightdht.DHT(port=54768, id_=id_, version="XN\x00\x00") 

# where to put our product
outf = open("get-peers.%s.log" % id_.encode("hex"),"a")

# handler
def myhandler(rec, c):
    try:    
        if rec["y"] =="q":
            if rec["q"] == "get_peers":
                print(";".join(
                    [   str(time.time()),
                        rec["a"].get("id").encode("hex"),
                        rec["a"].get("info_hash").encode("hex"),
                        repr(c),
                    ]), file=outf)
                outf.flush()
                        
    finally:
        # always ALWAYS pass it off to the real handler
        dht.default_handler(rec,c) 

dht.handler = myhandler
dht.active_discovery = False
dht.self_find_delay = 30

# Start it!
with dht:
    # Go to sleep and let the DHT service requests.
    while True:
        time.sleep(1)
