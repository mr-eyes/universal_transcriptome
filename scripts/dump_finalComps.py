"""
This script is used under the project "Omnigraph"

Input:
    1. sqlite DB File
    2. PairsCount TSV file generated by the executable: single_primaryPartitioning.
    3. number of cores
    4. optional: cutoff threshold, filter out edges with weight < cutoff.

Output:
    1. Directory of fasta files, each file contains a final component sequences.
    2. TSV with col1:finalCompID col2:originalComponentsIDs


Run:
python dump_finalComps.py <db_file> <pairsCountFile> <original_connected_comps.TSV> <no_cores> <opt: cutoff (default:1)>
"""

import sqlite3
import subprocess
from collections import defaultdict
import os
from tqdm import tqdm
import multiprocessing
import plotly.graph_objs as go
from plotly.offline import plot
from collections import Counter
import click


class ConnectedComponents:

    def __init__(self, min_count=1):
        self.__source = list()
        self.__target = list()
        self.__filtered_source = list()
        self.__filtered_target = list()
        self.final_components = dict()
        self.all_final_components = dict()
        self.filtered_final_components = dict()
        self.number_of_components = int()
        self.THRESHOLD = min_count

    def add_edge(self, source_node, target_node, pair_count):
        if pair_count >= self.THRESHOLD:
            self.__source.append(source_node)
            self.__target.append(target_node)
        else:
            self.__filtered_source.append(source_node)
            self.__filtered_target.append(target_node)

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

    def construct_filtered(self):
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

        for i in range(len(self.__filtered_source)):
            __union(self.__filtered_source[i], self.__filtered_target[i])

        for x in __leaders:
            __groups[__find(x)].add(x)

        for component_id, (k, v) in enumerate(__groups.items(), start=1):
            self.filtered_final_components[component_id] = v

        self.number_of_filtered_components = len(self.filtered_final_components)

    def construct_connected_components(self):
        self.construct()
        self.construct_filtered()
        last_component = max(self.final_components.keys())
        for compID, nodes in self.final_components.items():
            self.all_final_components[compID] = nodes
        for compID, nodes in self.filtered_final_components.items():
            self.all_final_components[last_component + compID] = nodes

        self.number_of_all_components = len(self.all_final_components)

    def get_components_dict(self):
        return self.final_components

    def get_filtered__components_dict(self):
        return self.final_components

    def get_all_components(self):
        return self.all_final_components

    def dump_to_tsv(self, _file_name):
        with open(_file_name, 'w') as tsvWriter:
            for compID, nodes in self.all_final_components.items():
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


"""
0. Parse originalComp to size
"""


@click.command()
@click.option('-d', '--db', "sqlite_db_path", required=True, type=click.Path(exists=True), help="sqlite database file")
@click.option('-u', '--unitigs', "unitigs_path", required=True, type=click.Path(exists=True),
              help="cDBG unititgs fasta file")
@click.option('-p', '--pairs-count', "pairsCountFile", required=True, type=click.Path(exists=True),
              help="Pairs count TSV")
@click.option('-u', '--orig-comps', "originalConnectedComps_path", required=True, type=click.Path(exists=True),
              help="cDBG unititgs fasta file")
@click.option('-t', '--no-cores', 'no_cores', required=False, type=click.INT, default=1, show_default=True,
              help="number of cores")
@click.option('-c', '--cutoff', 'cutoff_threshold', required=False, type=click.INT, default=1, show_default=True,
              help="cutoff threshold")
def main(no_cores, cutoff_threshold, sqlite_db_path, unitigs_path, pairsCountFile, originalConnectedComps_path):
    """
    Dump the final components from the sqlite DB to fasta files
    """

    """
    0. Get component sizes
    """

    origComp_to_sizebp = dict()
    unitig_to_origComp = dict()

    print("Calculating original component sizes")
    with open(originalConnectedComps_path, 'r') as compsReader:
        for _line in compsReader:
            _line = list(map(int, _line.strip().split(',')))
            _compID = int(_line[0])
            origComp_to_sizebp[_compID] = 0
            for unitig_id in _line[1:]:
                unitig_to_origComp[int(unitig_id)] = _compID

    lines_number = int(subprocess.getoutput('wc -l ' + unitigs_path).split()[0]) // 2

    with open(unitigs_path, 'r') as unitigsReader:
        for line in tqdm(unitigsReader, total=lines_number):
            header = line.strip().split()
            unitig_id = int(header[0][1:])
            seq_len = len(next(unitigsReader).strip())
            origComp_to_sizebp[unitig_to_origComp[unitig_id]] += seq_len

    """
    1. Parse the pairsCount to edges
    """

    edges = []
    with open(pairsCountFile, 'r') as pairsCountReader:
        next(pairsCountReader)  # skip header
        for line in pairsCountReader:
            edges.append(tuple(map(int, line.strip().split())))

    """
    2. Construct final components
    """

    components = ConnectedComponents(min_count=cutoff_threshold)
    for edge in edges:
        components.add_edge(*edge)

    components.construct_connected_components()

    """
    3. Multithreaded dumping the partitions to fasta files
    """

    all_lengths = multiprocessing.Manager().list()
    originalComp_total_sizesbp = multiprocessing.Manager().list()
    shared_origComp_to_sizebp = multiprocessing.Manager().dict(origComp_to_sizebp)

    def perform_writing(params):
        global all_lengths
        global originalComp_total_sizesbp
        global shared_origComp_to_sizebp

        file_path, _finalCompID, _originalComps = params
        conn = sqlite3.connect(sqlite_db_path)
        _originalComps = tuple(_originalComps)
        read_1_sql = "select * from reads where seq1_original_component in ({seq})".format(seq=','.join(['?'] * len(_originalComps)))
        read_1_curs = conn.execute(read_1_sql, _originalComps)

        read_2_sql = "select * from reads where seq1_original_component in ({seq})".format(seq=','.join(['?'] * len(_originalComps)))
        read_2_curs = conn.execute(read_2_sql, _originalComps)

        origCompSizeBP = 0
        for _orig_comp in _originalComps:
            origCompSizeBP += shared_origComp_to_sizebp[_orig_comp]

        originalComp_total_sizesbp.append(origCompSizeBP)

        with open(file_path, 'w') as fastaWriter:
            for row in read_1_curs:
                if (row[3] and row[4]) and (row[3] != row[4]):
                    all_lengths.append(len(row[1]))
                    fastaWriter.write(f">{row[0]}.1\t{_finalCompID}\n{row[1]}\n")

            for row in read_2_curs:
                if (row[3] and row[4]) and (row[3] != row[4]):
                    all_lengths.append(len(row[2]))
                    fastaWriter.write(f">{row[0]}.2\t{_finalCompID}\n{row[2]}\n")

        conn.close()

    print("---" * 10)
    print(f"Total bp: {sum(all_lengths)}")
    print(f"number of components: {components.number_of_components}")
    print(f"number of filtered components: {components.number_of_filtered_components}")
    print(f"number of all components: {components.number_of_all_components}")
    print("---" * 10)

    print(originalComp_total_sizesbp)

    output_dir = os.path.basename(sqlite_db_path).replace(".db", '') + f"_cutoff({cutoff_threshold})"
    os.makedirs(output_dir)

    all_params = list()
    for finalComp, originalComps in components.get_all_components().items():
        file_name = os.path.join(output_dir, f"{finalComp}.fa")
        all_params.append((file_name, finalComp, originalComps))

    with multiprocessing.Pool(no_cores) as pool:
        for _ in tqdm(pool.imap_unordered(perform_writing, all_params), total=len(all_params)):
            pass

    """
    Histogram of lengths BP
    """

    histogram = dict(Counter(all_lengths))
    data = list()
    data.append(go.Bar(name="countHisto", x=list(map(str, histogram.keys())), y=list(histogram.values())))
    fig = go.Figure(data)
    fig.update_layout(barmode='group', yaxis_type="log", xaxis=dict(tickmode='linear'))
    plot(fig, filename=f"histogram_{output_dir}.html", auto_open=False)


if __name__ == '__main__':
    main()
