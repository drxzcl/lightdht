"""
    Basic program to show the useage of lightdht.
    
    We run a dht node and log all incoming queries.
"""
import logging
import hashlib
import time


import lightdht


# Enable logging:
lightdht.logger.setLevel(logging.INFO)     
error_handler = logging.StreamHandler(open("dht-errors.log","a"))
error_handler.setLevel(logging.WARNING)
lightdht.logger.addHandler(error_handler)

stdout_handler = logging.StreamHandler()
lightdht.logger.addHandler(stdout_handler)


# Create a DHT node.
dht = lightdht.DHT(port=54767, id_=hashlib.sha1(
        "Change this to avoid getting ID clashes").digest()) 

# where to put our product
outf = open("get-peers.log","a")

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

# Start it!
with dht:
    # Go to sleep and let the DHT service requests.
    while True:
        time.sleep(1)
