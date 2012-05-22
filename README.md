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