"""
    Basic program to show the useage of lightdht.
    
    We run a dht node and log all incoming queries.
"""
import logging
import hashlib
import time
import os

import lightdht


# Enable logging:
lightdht.logger.setLevel(logging.INFO)     
req_handler = logging.StreamHandler(open("incoming-requests.log","a"))
req_handler.setLevel(logging.INFO)
formatter = logging.Formatter("[%(levelname)s@%(created)s] %(message)s")
req_handler.setFormatter(formatter)

lightdht.logger.addHandler(req_handler)

stdout_handler = logging.StreamHandler()
stdout_handler.setFormatter(formatter)
lightdht.logger.addHandler(stdout_handler)


# Create a DHT node.
id_ = os.urandom(20) #hashlib.sha1("Change this to avoid getting ID clashes").digest()
dht = lightdht.DHT(port=54767, id_=id_) 

# where to put our product
outf = open("get-peers.%s.log" % id_.encode("hex"),"a")

# handler
def myhandler(rec, c):
    try:    
        if rec["y"] =="q":
            if rec["q"] == "get_peers":
                print >>outf,";".join(
                    [   str(time.time()),
                        rec["a"].get("id").encode("hex"),
                        rec["a"].get("info_hash").encode("hex"),
                        repr(c),
                    ])
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
