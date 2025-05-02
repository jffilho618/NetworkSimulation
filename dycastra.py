import json

def dijkstra(origem, lsdb):
    # Mapeamento de roteadores para sub-redes
    subnet_map = {
        "172.20.1.3": "172.20.1.0/24",
        "172.20.2.3": "172.20.2.0/24",
        "172.20.3.3": "172.20.3.0/24",
        "172.20.4.3": "172.20.4.0/24",
        "172.20.5.3": "172.20.5.0/24"
    }

    # 1. Monta o grafo, incluindo apenas sub-redes
    grafo = {}
    for router_id, lsa in lsdb.items():
        if router_id not in grafo:
            grafo[router_id] = {}
        # Adiciona a sub-rede do roteador como nó conectado
        if router_id in subnet_map:
            subnet = subnet_map[router_id]
            grafo[router_id][subnet] = 0  # Custo 0 para a própria sub-rede
            if subnet not in grafo:
                grafo[subnet] = {}
            grafo[subnet][router_id] = 0  # Sub-rede conectada ao roteador
        # Adiciona vizinhos roteadores
        for viz_name, (ip_viz, custo) in lsa["vizinhos"].items():
            if ip_viz in lsdb:
                grafo[router_id][ip_viz] = custo
                if ip_viz not in grafo:
                    grafo[ip_viz] = {}
                grafo[ip_viz][router_id] = custo

    # 2. Inicializa Dijkstra
    dist = {node: float('inf') for node in grafo}
    prev = {node: None for node in grafo}
    dist[origem] = 0
    visitados = set()

    while len(visitados) < len(grafo):
        u = min((node for node in grafo if node not in visitados), key=lambda node: dist[node])
        visitados.add(u)
        for v, custo in grafo[u].items():
            if dist[u] + custo < dist[v]:
                dist[v] = dist[u] + custo
                prev[v] = u

    # 3. Monta tabela de rotas, incluindo apenas sub-redes
    tabela = {}
    for destino in grafo:
        if destino == origem or prev[destino] is None:
            continue
        # Inclui apenas sub-redes na tabela de rotas
        if destino.endswith("/24"):
            next_hop = destino
            while prev[next_hop] != origem and prev[next_hop] is not None:
                next_hop = prev[next_hop]
            if next_hop != destino:
                tabela[destino] = next_hop

    return tabela

if __name__ == "__main__":
    lsdb = {
        "172.20.2.3": {
            "id": "172.20.2.3",
            "vizinhos": {
                "router1": ["172.20.1.3", 0.0034530162811279297],
                "router3": ["172.20.3.3", 0.0012178421020507812]
            },
            "seq": 13701
        },
        "172.20.3.3": {
            "id": "172.20.3.3",
            "vizinhos": {
                "router2": ["172.20.2.3", 0.003142833709716797],
                "router4": ["172.20.4.3", 0.0016400814056396484]
            },
            "seq": 13351
        },
        "172.20.1.3": {
            "id": "172.20.1.3",
            "vizinhos": {
                "router5": ["172.20.5.3", 0.012853384017944336],
                "router2": ["172.20.2.3", 0.00501561164855957]
            },
            "seq": 13584
        },
        "172.20.5.3": {
            "id": "172.20.5.3",
            "vizinhos": {
                "router1": ["172.20.1.3", 0.005136013031005859],
                "router4": ["172.20.4.3", 0.0030078887939453125]
            },
            "seq": 13675
        },
        "172.20.4.3": {
            "id": "172.20.4.3",
            "vizinhos": {
                "router3": ["172.20.3.3", 0.005071878433227539],
                "router5": ["172.20.5.3", 0.011375188827514648]
            },
            "seq": 13770
        }
    }

    print(dijkstra("172.20.1.3", lsdb))