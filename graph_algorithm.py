#!/usr/bin/env python

'''
Graph algorithms used in chapter 4 and appendix C of Large-Scale C++ Software Design.

A Python Graph API? http://wiki.python.org/moin/PythonGraphApi
It seems that the best one is NetworkX(http://networkx.lanl.gov/).
'''

import networkx as nx

def is_reachable(digraph, nodeA, nodeB):
    rch_nodes = digraph.successors(nodeA)
    ind = 0
    while(1):
        if(ind>=len(rch_nodes)):
            return False
        node = rch_nodes[ind]
        if(node==nodeB):
            return True
        suc_nodes = digraph.successors(node)
        for suc_node in suc_nodes:
            if(suc_node not in rch_nodes):
                rch_nodes.append(suc_node)
        ind += 1
    assert(0)
    return False

def strip_redundant_edges(digraph, key_edge=None):
    '''DiGraph.edges() may return different order of edges among several runs. 
    This may cause different edges being considered as redundant. 
    key_edge!=None means sorting edges befor iterating them in order to avoid above randomness. 
    '''
    redundant_edges = list()
    edges = digraph.edges()
    if(key_edge):
        edges.sort(key=key_edge)
    for edge in edges:
        digraph.remove_edge(edge[0], edge[1])
        if(edge[0] == edge[1]):
            redundant_edges.append(edge)
            continue
        reachable = is_reachable(digraph, edge[0], edge[1])
        if(reachable):
            redundant_edges.append(edge)
        else:
            digraph.add_edge(edge[0], edge[1])
    return redundant_edges

def strip_cycles(digraph, key_node=None):
    '''Make out a DAG. Only one node in each cycle is kep in graph, others are removed.
    DiGraph.nodes() may return different order of nodes. key_node!=None means sorting nodes to avoid above randomness.
    '''
    cycles = dict()
    dict_node2cycle = dict()
    for node in digraph.nodes_iter():
        dict_node2cycle[node] = None
    subgraphs = nx.strongly_connected_component_subgraphs(digraph)
    for ind in range(len(subgraphs)-1, -1, -1):
        subgraph = subgraphs[ind]
        if(len(subgraph)==1):
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
        for node in nodes:
            pre_nodes = digraph.predecessors(node)
            suc_nodes = digraph.successors(node)
            for pre_node in pre_nodes:
                if(pre_node==node or dict_node2cycle[pre_node]==min_node or digraph.has_edge(pre_node, min_node)):
                    continue
                digraph.add_edge(pre_node, min_node)
            for suc_node in suc_nodes:
                if(suc_node==node or dict_node2cycle[suc_node]==min_node or digraph.has_edge(min_node, suc_node)):
                    continue
                digraph.add_edge(min_node, suc_node)
            # All edges assiciated with a node will also be removed when removing the node from the graph.
            digraph.remove_node(node)
    return(cycles, dict_node2cycle)

def layering(digraph, key_node=None):
    '''Assumption: All redundant edges and all cycles have been stripped.'''
    layers = list()
    dict_layer_no = dict()
    nodes = digraph.nodes()
    if(len(nodes)==0):
        return (layers, dict_layer_no)
    out_degrees = digraph.out_degree()
    dict_out_degrees = dict()
    #print digraph.out_degree()
    nodes_layer0 = list()
    for ind in range(0, len(nodes)):
        node = nodes[ind]
        dict_out_degrees[node] = out_degrees[ind]
        if(out_degrees[ind]==0):
            nodes_layer0.append(node)
            dict_layer_no[node] = 0
    assert(len(nodes_layer0)!=0)
    if(key_node):
        nodes_layer0.sort(key=key_node)
    layers.append(nodes_layer0)
    cur_layer_no = 1
    while(1):
        nodes_layer1 = list()
        for node in nodes_layer0:
            pre_nodes = digraph.predecessors(node)
            for pre_node in pre_nodes:
                dict_out_degrees[pre_node] -= 1
                if(pre_node not in nodes_layer1):
                    nodes_layer1.append(pre_node)
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
    return (layers, dict_layer_no)

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
    print 'nodes(%d): '%digraph.number_of_nodes(), digraph.nodes()
    print 'edges(%d): '%digraph.number_of_edges(), digraph.edges()


if __name__ == '__main__':
    digraph = nx.DiGraph()
    edges1 = [(1,1), (1,2), (2,4), (2,6), (6,2), (6,7), (7,6)]
    edges2 = [(1,3), (3,4), (3,5), (3,8), (8,9), (9,3)]
    edges3 = [(10,11), (10, 12), (11,12), (12,11)]
    digraph.add_edges_from(edges1)
    digraph.add_edges_from(edges2)
    digraph.add_edges_from(edges3)
    print '='*80
    print 'original digraph: '
    output_graph(digraph);
    strip_redundant_edges(digraph)
    print '='*80
    print 'after stripping redundant edges: '
    output_graph(digraph);
    (cycles, dict_cycle_no) = strip_cycles(digraph)
    print '='*80
    print 'after stripping cycles: '
    output_graph(digraph);
    for (min_node, cycle) in cycles.items():
        print 'cycle %s: '%(str(min_node))
        output_graph(cycle)
    (layers, dict_layer_no) = layering(digraph)
    print '='*80
    print 'after layering: '
    output_graph(digraph)
    for ind in range(0, len(layers)):
        print 'layer %d: '%(ind) + repr(layers[ind])
    (ccd, dict_cd) = calc_ccd(digraph, cycles, layers)
    print '='*80
    size = len(dict_cd)
    import math
    ccd_fullBTree = (size+1)*(math.log(size+1, 2)) - size
    nccd = ccd/ccd_fullBTree
    print 'CCD: %d\t NCCD: %f(typical range is [0.85, 1.10])\t SIZE: %d'%(ccd, nccd, size)
    print 'cumulate dependencies: ' + repr(dict_cd)

