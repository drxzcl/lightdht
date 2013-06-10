LightDHT: A lightweight python implementation of the Bittorrent distributed hashtable.
=============

The aim of LightDHT is to provide a simple, flexible implementation of the
Bittorrent mainline DHT for use in research applications. If you want to trade files,
you have come to the wrong place. LightDHT does not implement the actual
file transfer parts of the bittorrent protocol. It only takes part in the
DHT.

Philosophy:
 
 - Ease of use over performance
 - Adaptability over scalability

In order to keep LightDHT easy to use, you have the option to perform DHT RPC calls 
synchronously. This means that when you call a DHT method, your program will
block until you have an answer to your request. That answer will be the
return value of the function. This has the advantage that it keeps the
logical program flow intact, and makes it more comfortable to use. You can also schedule a callback function, that will be called when the response arrives. This requires more complex code, but enables you to do multiple things at once. Your specific application will dictate whether you should be using synchronous or asynchronous communication.

In order to maintain O(log N) scaling across the network, BEP0005 (the
standard governing the DHT) mandates that implementations use a bucket-based
approach to the routing table. This enables the node to fulfill all requests
in constant time and (more or less) constant memory. In LightDHT, we throw 
that recommendation to the wind.

Since the main focus of LightDHT is reseach, we are going to keep around all
the data we can. This means that we keep around every single node we know
about. You can choose between using a simple flat routing table, where all the node information is stored in a single dictionary, or a slightly more complex multi-level prefix-based routing table, where nodes are grouped together based on their node IDs.

[![githalytics.com alpha](https://cruel-carlota.pagodabox.com/66b2052410e17ef51bdab10b5440c540 "githalytics.com")](http://githalytics.com/drxzcl/lightdht)
