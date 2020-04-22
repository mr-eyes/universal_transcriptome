"""
This script is used under the project "Omnigraph"

Input: PairsCount TSV file generated by the executable: single_primaryPartitioning
Output:
    1. Directory of fasta files, each file contains a final component sequences.
    2. TSV with col1:finalCompID col2:originalComponentsIDs


Run:
python dump_finalComps.py <db_file> <pairsCountFile>
"""

import sys
from collections import defaultdict


class ConnectedComponents:

    def __init__(self, min_count=1):
        self.__source = list()
        self.__target = list()
        self.final_components = dict()
        self.number_of_components = int()
        self.THRESHOLD = min_count

    def add_edge(self, source_node, target_node, pair_count):
        if pair_count >= self.THRESHOLD:
            self.__source.append(source_node)
            self.__target.append(target_node)

    def construct(self):
        __leaders = defaultdict(lambda: None)
        __groups = defaultdict(set)

        def __find(x):
            l = __leaders[x]
            if l is not None:
                l = __find(l)
                __leaders[x] = l
                return l
            return x

        def __union(x, y):
            lx, ly = __find(x), __find(y)
            if lx != ly:
                __leaders[lx] = ly

        for i in range(len(self.__source)):
            __union(self.__source[i], self.__target[i])

        for x in __leaders:
            __groups[__find(x)].add(x)

        for component_id, (k, v) in enumerate(__groups.items(), start=1):
            self.final_components[component_id] = v

        self.number_of_components = len(self.final_components)

    def get_components_dict(self):
        return self.final_components

    def dump_to_tsv(self, file_name):
        with open(file_name, 'w') as tsvWriter:
            for compID, nodes in self.final_components.items():
                nodes = ','.join(map(str, nodes))
                tsvWriter.write(f"{compID}\t{nodes}\n")

    def __del__(self):
        del self


def get_nodes_sizes(components_file_path):
    """
    Return the size of each original component so we can apply threshold on weight.
    :param components_file_path:
    :return: node_to_size
    """
    node_to_size = dict()
    with open(components_file_path, 'r') as compsReader:
        for _line in compsReader:
            _line = list(map(int, _line.strip().split(',')))
            _compID = int(_line[0])
            node_to_size[_compID] = len(_line) - 1

    return node_to_size


if len(sys.argv) < 2:
    raise ValueError("run: python dump_finalComps.py dump_finalComps.py <db_file> <pairsCountFile>")

pairsCountFile = sys.argv[1]

# Parsing the weighted edges
edges = []
with open(pairsCountFile, 'r') as pairsCountReader:
    next(pairsCountReader)  # skip header
    for line in pairsCountReader:
        edges.append(tuple(map(int, line.strip().split())))

components = ConnectedComponents(min_count=1)
for edge in edges:
    components.add_edge(*edge)

components.construct()
print(f"number of connected components: {components.number_of_components}")
