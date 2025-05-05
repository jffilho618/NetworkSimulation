import json
import pprint

def dijkstra(origem, lsdb):
    """
    Implementação do algoritmo de Dijkstra para calcular caminhos mais curtos.
    
    Args:
        origem: IP do roteador de origem
        lsdb: Banco de dados de estado de enlace (Link State Database)
        
    Returns:
        Dicionário com mapeamento de sub-redes de destino para próximo salto
    """
    print(f"\n--- Calculando rotas para {origem} ---") # Log de início
    # 1. Monta o grafo, incluindo roteadores e sub-redes
    grafo = {}

    for router_id, lsa in lsdb.items():
        if router_id not in grafo:
            grafo[router_id] = {}

        # Adiciona sub-redes diretamente conectadas (IGNORANDO LOOPBACK)
        if "subnets" in lsa:
            for subnet in lsa["subnets"]:
                # Pula a rede de loopback
                if subnet == "127.0.0.0/8":
                    continue 
                # Adiciona conexões de custo 0 para sub-redes válidas
                grafo[router_id][subnet] = 0
                if subnet not in grafo:
                    grafo[subnet] = {}
                grafo[subnet][router_id] = 0

        # Adiciona vizinhos roteadores (CORRIGIDO)
        # (O código para adicionar vizinhos que corrigimos antes permanece o mesmo)
        for viz_name, (ip_viz, custo) in lsa["vizinhos"].items():
            if ip_viz in lsdb: 
                grafo[router_id][ip_viz] = custo
                if ip_viz not in grafo:
                     grafo[ip_viz] = {}
                grafo[ip_viz][router_id] = custo

    # (O restante da função dijkstra permanece o mesmo)
    # ...



    # --- LOG DE DEPURAÇÃO: Imprime o grafo construído ---
    print("\n--- Grafo Construído ---")
    pprint.pprint(grafo)
    print("--- Fim do Grafo ---\n")
    # ---------------------------------------------------

    # 2. Inicializa Dijkstra
    dist = {node: float("inf") for node in grafo}
    prev = {node: None for node in grafo}
    dist[origem] = 0
    visitados = set()
    pq = [(0, origem)] # Usando uma lista como min-priority queue (simplificado)

    while pq:
        # Extrai o nó com menor distância (simulação de min-heap)
        pq.sort()
        d, u = pq.pop(0)

        if u in visitados:
            continue
        if d > dist[u]: # Otimização: ignora entradas obsoletas na "fila"
            continue
            
        visitados.add(u)
        
        # Atualizar distâncias dos vizinhos
        if u in grafo: # Verifica se u existe no grafo antes de iterar
            for v, custo in grafo[u].items():
                if v in dist and dist[u] + custo < dist[v]: # Verifica se v existe em dist
                    dist[v] = dist[u] + custo
                    prev[v] = u
                    pq.append((dist[v], v))

    # --- LOG DE DEPURAÇÃO: Imprime dist e prev ---
    print("\n--- Tabela de Distâncias (dist) ---")
    pprint.pprint(dist)
    print("--- Fim da Tabela de Distâncias ---\n")
    print("\n--- Tabela de Predecessores (prev) ---")
    pprint.pprint(prev)
    print("--- Fim da Tabela de Predecessores ---\n")
    # ---------------------------------------------

        # 3. Monta tabela de rotas, incluindo apenas sub-redes (BACKTRACKING CORRIGIDO)
    tabela = {}
    for destino in grafo:
        # Ignora o próprio roteador de origem e destinos inalcançáveis
        if destino == origem or prev[destino] is None:
            continue

        # Considera apenas sub-redes como destinos finais
        if "/" in destino:
            # Backtrack para encontrar o próximo salto (next hop router IP)
            current_node = destino
            next_hop_ip = None

            # Volta no caminho até encontrar o nó cujo predecessor é a origem
            while prev[current_node] is not None and prev[current_node] != origem:
                current_node = prev[current_node]
            
            # Após o loop, 'current_node' é o nó que está diretamente conectado à origem
            # Este 'current_node' É o próximo salto que queremos
            if prev[current_node] == origem:
                next_hop_ip = current_node # Este deve ser o IP do roteador vizinho
                
                # Garante que o próximo salto seja um IP de roteador (não uma sub-rede)
                if "/" not in next_hop_ip:
                    tabela[destino] = next_hop_ip
                # else: # Opcional: Log se o próximo salto identificado não for um IP
                #    print(f"[AVISO] Próximo salto para {destino} a partir de {origem} é {next_hop_ip}, que não é um IP. Rota descartada.")
            # else: # Opcional: Log se o backtracking falhar
            #    print(f"[ERRO] Backtracking falhou para {destino} a partir de {origem}. Nó final: {current_node}, Prev: {prev[current_node]}")

    return tabela



if __name__ == "__main__":
    # Exemplo para teste com informações de sub-redes
    lsdb = {
        "172.20.2.3": {
            "id": "172.20.2.3",
            "vizinhos": {
                "router1": ["172.20.1.3", 0.0034530162811279297],
                "router3": ["172.20.3.3", 0.0012178421020507812]
            },
            "subnets": ["172.20.2.0/24"],
            "seq": 13701
        },
        "172.20.3.3": {
            "id": "172.20.3.3",
            "vizinhos": {
                "router2": ["172.20.2.3", 0.003142833709716797],
                "router4": ["172.20.4.3", 0.0016400814056396484]
            },
            "subnets": ["172.20.3.0/24"],
            "seq": 13351
        },
        "172.20.1.3": {
            "id": "172.20.1.3",
            "vizinhos": {
                "router5": ["172.20.5.3", 0.012853384017944336],
                "router2": ["172.20.2.3", 0.00501561164855957]
            },
            "subnets": ["172.20.1.0/24"],
            "seq": 13584
        },
        "172.20.5.3": {
            "id": "172.20.5.3",
            "vizinhos": {
                "router1": ["172.20.1.3", 0.005136013031005859],
                "router4": ["172.20.4.3", 0.0030078887939453125]
            },
            "subnets": ["172.20.5.0/24"],
            "seq": 13675
        },
        "172.20.4.3": {
            "id": "172.20.4.3",
            "vizinhos": {
                "router3": ["172.20.3.3", 0.005071878433227539],
                "router5": ["172.20.5.3", 0.011375188827514648]
            },
            "subnets": ["172.20.4.0/24"],
            "seq": 13770
        }
    }

    print(dijkstra("172.20.1.3", lsdb))