#!/usr/bin/env python2

'''
Graph algorithms used in chapter 4 and appendix C of Large-Scale C++ Software Design.

A Python Graph API? http://wiki.python.org/moin/PythonGraphApi
It seems that the best one is NetworkX(http://networkx.lanl.gov/).

zhichyu@jupiter:~/cppdep$ ./networkx_ext.py
================================================================================
original digraph:
nodes(12):  1 2 3 4 5 6 7 8 9 10 11 12
edges(18):  1->1 1->2 1->3 1->5 2->4 2->6 3->8 3->4 3->5 6->2 6->7 7->6 8->9 9->3 10->11 10->12 11->12 12->11
================================================================================
after stripping cycles:
nodes(7):  1 2 4 5 8 10 11
edges(7):  1->8 1->2 1->5 2->4 8->4 8->5 10->11
cycle 8:
nodes(3):  8 9 3
edges(3):  8->9 9->3 3->8
cycle 2:
nodes(3):  2 6 7
edges(4):  2->6 6->2 6->7 7->6
cycle 11:
nodes(2):  11 12
edges(2):  11->12 12->11
================================================================================
after layering:
nodes(7):  1 2 4 5 8 10 11
edges(6):  1->8 1->2 2->4 8->4 8->5 10->11
layer 0: [4, 5, 11]
layer 1: [8, 2, 10]
layer 2: [1]
redundant edges stripped: [(1, 5)]
================================================================================
CCD: 46	 NCCD: 1.274036(typical range is [0.85, 1.10])	 SIZE: 12
cumulate dependencies: {1: 10, 2: 4, 3: 5, 4: 1, 5: 1, 6: 4, 7: 4, 8: 5, 9: 5, 10: 3, 11: 2, 12: 2}
zhichyu@jupiter:~/cppdep$
'''

import networkx as nx

def is_reachable(digraph, nodeA, nodeB):
    if(nodeA==nodeB):
        return False
    set_rch_nodes = set([nodeA])
    set_current_nodes = set([nodeA])
    set_next_nodes = set()
    while(1):
        for node in set_current_nodes:
            suc_nodes = digraph.successors(node)
            set_next_nodes.update(suc_nodes)
        if(nodeB in set_next_nodes):
            return True
        set_next_nodes.difference_update(set_rch_nodes)
        if(len(set_next_nodes)==0):
            return False
        set_rch_nodes.update(set_next_nodes)
        set_current_nodes, set_next_nodes = set_next_nodes, set_current_nodes
        set_next_nodes.clear()
    assert(0)
    return False

def make_DAG(digraph, key_node=None):
    '''Make out a DAG.
    Only one node in each cycle is kept in the original graph. That node is used as the key of cycle subgraphs.
    key_node!=None indicates selecting the minimal one among all nodes of the cycle per key_node.
    Otherwise which one being selected is an implementation specific behavior.
    Note: Selfloop edges will be stripped silently.
    '''
    # output_graph(digraph)
    cycles = dict()
    dict_node2cycle = dict()
    for node in digraph.nodes_iter():
        dict_node2cycle[node] = None
    # Strip all selfloop edges silently.
    digraph.remove_edges_from(digraph.selfloop_edges())
    subgraphs = nx.strongly_connected_component_subgraphs(digraph)
    for ind in range(len(subgraphs)-1, -1, -1):
        subgraph = subgraphs[ind]
        if(subgraph.number_of_nodes()==1):
            # Selfloop edges have been stripped.
            assert(subgraph.number_of_edges()==0)
            del subgraphs[ind]
        else:
            nodes = subgraph.nodes()
            if(key_node):
                min_node = min(nodes, key=key_node)
            else:
                min_node = nodes[0]
            cycles[min_node] = subgraph
            for node in nodes:
                dict_node2cycle[node] = min_node
    for min_node in cycles:
        nodes = cycles[min_node].nodes()
        nodes.remove(min_node)
        # print 'min_node: %s, other nodes: ' % str(min_node), ' '.join(map(str, nodes))
        for node in nodes:
            pre_nodes = digraph.predecessors(node)
            suc_nodes = digraph.successors(node)
            for pre_node in pre_nodes:
                if(pre_node==min_node or (pre_node in nodes) or digraph.has_edge(pre_node, min_node)):
                    continue
                digraph.add_edge(pre_node, min_node)
            for suc_node in suc_nodes:
                if(suc_node==min_node or (suc_node in nodes) or digraph.has_edge(min_node, suc_node)):
                    continue
                digraph.add_edge(min_node, suc_node)
            # All edges assiciated with a node will also be removed when removing the node from the graph.
            digraph.remove_node(node)
    return(cycles, dict_node2cycle)

def layering_DAG(digraph, key_node=None):
    '''
    Layering all nodes and strip redundant edges in the graph.
    Assumption: digraph is a DAG(Directed Acyclic Graph).
    '''
    layers = list()
    dict_layer_no = dict()
    redundant_edges = list()
    nodes = digraph.nodes()
    if(len(nodes)==0):
        return (layers, dict_layer_no)
    dict_out_degrees = digraph.out_degree()
    #print digraph.out_degree()
    nodes_layer0 = list()
    for node in dict_out_degrees:
        if(dict_out_degrees[node]==0):
            nodes_layer0.append(node)
            dict_layer_no[node] = 0
    assert(len(nodes_layer0)!=0)
    if(key_node):
        nodes_layer0.sort(key=key_node)
    layers.append(nodes_layer0)
    cur_layer_no = 1
    while(1):
        nodes_layer1 = set()
        for node in nodes_layer0:
            pre_nodes = digraph.predecessors(node)
            for pre_node in pre_nodes:
                dict_out_degrees[pre_node] -= 1
                nodes_layer1.add(pre_node)
        nodes_layer1 = list(nodes_layer1)
        for ind in range(len(nodes_layer1)-1, -1, -1):
            node = nodes_layer1[ind]
            if(dict_out_degrees[node] > 0):
                del nodes_layer1[ind]
            else:
                dict_layer_no[node] = cur_layer_no
        if(len(nodes_layer1)==0):
            break
        if(key_node):
            nodes_layer1.sort(key=key_node)
        layers.append(nodes_layer1)
        nodes_layer0 = nodes_layer1
        cur_layer_no += 1
    for ind in range(1,len(layers)):
        for node in layers[ind]:
            for suc_node in digraph.successors(node):
                # Edges between adjacent layers are always non-redundant if the graph is a DAG(ie. no cycles).
                if(dict_layer_no[suc_node]==ind-1):
                    continue
                digraph.remove_edge(node, suc_node)
                reachable = is_reachable(digraph, node, suc_node)
                if(reachable):
                    redundant_edges.append((node, suc_node))
                    continue
                digraph.add_edge(node, suc_node)
    return (layers, dict_layer_no, redundant_edges)

def calc_ccd(digraph, cycles, layers):
    ccd = 0
    dict_cd = dict()
    if(len(digraph.nodes())==0):
        return (ccd, dict_cd)
    for node in digraph.nodes():
        dict_cd[node] = 1
    min_nodes = set(cycles.keys())
    for layer in layers:
        for node in layer:
            for suc_node in digraph.successors(node):
                dict_cd[node] += dict_cd[suc_node]
            if(node in min_nodes):
                dict_cd[node] += len(cycles[node]) - 1
    for min_node in cycles:
        cd = dict_cd[min_node]
        for node2 in cycles[min_node].nodes_iter():
            if(node2 == min_node):
                continue
            dict_cd[node2] = cd
    ccd =  reduce(lambda x,y: x+y, dict_cd.values())
    return (ccd, dict_cd)

def output_graph(digraph):
    print 'nodes(%d): '%digraph.number_of_nodes(), ' '.join(map(str, digraph.nodes()))
    print 'edges(%d): '%digraph.number_of_edges(), ' '.join(map(lambda x: str(x[0])+'->'+str(x[1]), digraph.edges()))

if __name__ == '__main__':
    digraph = nx.DiGraph()
    edges1 = [(1,1), (1,2), (2,4), (2,6), (6,2), (6,7), (7,6)]
    edges2 = [(1,3), (1,5), (3,4), (3,5), (3,8), (8,9), (9,3)]
    edges3 = [(10,11), (10, 12), (11,12), (12,11)]
    digraph.add_edges_from(edges1)
    digraph.add_edges_from(edges2)
    digraph.add_edges_from(edges3)
    print '='*80
    print 'original digraph: '
    output_graph(digraph);
    (cycles, dict_cycle_no) = make_DAG(digraph)
    print '='*80
    print 'after stripping cycles: '
    output_graph(digraph);
    for (min_node, cycle) in cycles.items():
        print 'cycle %s: '%(str(min_node))
        output_graph(cycle)
    (layers, dict_layer_no, redundant_edges) = layering_DAG(digraph)
    print '='*80
    print 'after layering: '
    output_graph(digraph)
    for ind in range(0, len(layers)):
        print 'layer %d: '%(ind) + repr(layers[ind])
    print 'redundant edges stripped:', redundant_edges
    (ccd, dict_cd) = calc_ccd(digraph, cycles, layers)
    print '='*80
    size = len(dict_cd)
    import math
    ccd_fullBTree = (size+1)*(math.log(size+1, 2)) - size
    nccd = ccd/ccd_fullBTree
    print 'CCD: %d\t NCCD: %f(typical range is [0.85, 1.10])\t SIZE: %d'%(ccd, nccd, size)
    print 'cumulate dependencies: ' + repr(dict_cd)
