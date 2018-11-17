'''
Small script to translate HTTP Archive files into directed network graphs.
This allows you to create a directed network graph that simulates the
behavior of a browser accessing a specific webpage.

@author Skyler Bistarkey
'''

import time
from datetime import datetime

import json
import networkx as nx

class HARParser():
    def __init__(self, filename, server_and_port):
        self._filename = filename
        self._server_and_port = server_and_port
        self._port = self._server_and_port.split(":")[1]
        
        # HAR files are just JSON files after all
        with open(self._filename, "r", encoding="utf-8") as f:
            self._json_data = json.loads(f.read())

    def _get_entries(self):
        try:
            return self._json_data["log"]["entries"]
        except Exception as e:
            print("Error getting entries from HAR file: " + str(e))

    # Return the time of the HAR entry in milliseconds
    # HAR time entries are formatted as YYYY-mm-ddTHH:MM:SS.mmm-TT:TT
    def _time_fmt_to_ms(self, timestring):
        # Remove the timezone - it's not important for this
        timestring, ms = timestring[:-6].split(".")
        dt = datetime.strptime(timestring, "%Y-%m-%dT%H:%M:%S")

        # Return the request time in milliseconds
        return time.mktime(dt.timetuple())*1000 + int(ms)

    # Represent the directed graph as a list of lists
    # Each list will represent a series of files obtained in parallel
    # They are stored in chronological order - i.e., all transfers in one list must
    # be obtained before moving onto the next one
    def _make_graph_as_list(self, debug_log=False):
        try:
            graph_list = [] # Each entry will be a list of all the item sizes that will be obtained in parallel
            temp_list = [] # Temporary list to hold a single entry in the graph list

            for entry in self._get_entries():
                # We only really care about 3 things for each entry -
                #   1. The time the entry was created
                #   2. How long the entry took before the request was satisfied
                #   3. How big was the file obtained
                entry_time = self._time_fmt_to_ms(entry["startedDateTime"])
                entry_time_len = int(entry["time"])
                entry_size = (float(entry["response"]["headersSize"]) + float(entry["response"]["bodySize"])) / 1024.0
                
                # If the request time of the current entry is within any of the waiting periods of the
                # temp list, it is considered to be part of that burst
                if all((entry_time >= (t[0] + t[1])) for t in temp_list):
                    graph_list.append(temp_list.copy())
                    temp_list.clear()
                    temp_list.append((entry_time, entry_time_len, entry_size))
                
                else:
                    temp_list.append((entry_time, entry_time_len, entry_size))

            graph_list.append(temp_list.copy())

            # Possibly more useful than scanning the XML file
            if debug_log:
                for i in graph_list:
                    for j in i:
                        print(j)
                print("-----")

            return graph_list
        
        except Exception as e:
            print("Error parsing HAR file: " + str(e))
            return []

    # Create a directed network graph from a series parallel transfers
    def create_digraph(self, outfile):
        graph_list = self._make_graph_as_list()
        sync_str = "sync"

        if len(graph_list) == 0:
            raise Exception("Error: List parsed from HAR file was empty!")

        prev_node = "start"
        next_node = sync_str + "0"

        graph = nx.DiGraph()
        graph.add_node("start", serverport=self._port, peers=self._server_and_port)
        graph.add_node(next_node)

        # Each collection of transfers branches out from the previous sync and collects at the next one
        for i, graph_entry in enumerate(graph_list):
            for j, indiv_entry in enumerate(graph_entry):
                node_entry = "transfer{}-{}".format(i, j)
                xfer_size = "{:0.2f} KiB".format(indiv_entry[2]) # Round transfer size to 2 decimal places

                graph.add_node(node_entry, type="get", protocol="tcp", size=xfer_size)
                graph.add_edge(prev_node, node_entry)
                graph.add_edge(node_entry, next_node)
            
            prev_node = next_node
            next_node = sync_str + str(i+1)

        # For now, just add a pause of 1 min before going back to the start
        graph.add_node("pause", time="60")
        graph.add_edge(prev_node, "pause")
        graph.add_edge("pause", "start")
            
        nx.write_graphml(graph, outfile)

if __name__ == "__main__":
    hp = HARParser("./Archive 18-11-17 10-06-12.har", "server1:443")

    hp.create_digraph("test.xml")