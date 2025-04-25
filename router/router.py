import socket
import time
import json
import os 
import threading
import subprocess
from typing import Dict, Any, Set, Tuple, List, Optional
import heapq

PORTA = 5000

def log(msg: str):
    print(msg, flush=True)

class Vizinho:
    def __init__(self, ip: str, peso: int):
        self.ip = ip
        self.peso = peso

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ip": self.ip,
            "peso": self.peso
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Vizinho':
        return cls(
            ip=data["ip"],
            peso=data["peso"]
        )

class LSA:
    def __init__(self, id: str, ip: str, seq: int, vizinhos: Dict[str, Vizinho]):
        self.id = id
        self.ip = ip
        self.seq = seq
        self.vizinhos = vizinhos
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ip": self.ip,
            "seq": self.seq,
            "vizinhos": {k: v.to_dict() for k, v in self.vizinhos.items()}
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LSA':
        vizinhos = {k: Vizinho.from_dict(v) for k, v in data["vizinhos"].items()}
        return cls(
            id=data["id"],
            ip=data["ip"],
            seq=data["seq"],
            vizinhos=vizinhos
        )
    

class LSDB:
    def __init__(self):
        self.lsas: Dict[str, LSA] = {}

    def atualizar_lsa(self, lsa: LSA) -> bool:
        if (lsa.id not in self.lsas) or (self.lsas[lsa.id].seq < lsa.seq):
            self.lsas[lsa.id] = lsa
            log(f"LSA atualizado de {lsa.id} com seq {lsa.seq}")
            return True
        return False

    def get_topologia(self) -> Dict[str, Dict[str, int]]:
        grafo = {}
        
        # Primeiro, garante que todos os roteadores estejam no grafo
        for lsa in self.lsas.values():
            grafo[lsa.id] = {}
            # Adiciona também todos os vizinhos como nós no grafo
            for vizinho_id in lsa.vizinhos:
                if vizinho_id not in grafo:
                    grafo[vizinho_id] = {}
        
        # Depois, preenche as conexões
        for lsa in self.lsas.values():
            for vizinho_id, vizinho in lsa.vizinhos.items():
                grafo[lsa.id][vizinho_id] = vizinho.peso
                # Adiciona a conexão reversa se ainda não existir
                if vizinho_id in grafo and lsa.id not in grafo[vizinho_id]:
                    grafo[vizinho_id][lsa.id] = vizinho.peso
                    
        return grafo


class TabelaRotas:
    def __init__(self, grafo: Dict[str, Dict[str, int]], origem: str):
        self.rotas: Dict[str, Tuple[str, int]] = {}  # destino: (via, custo)
        if origem in grafo:
            self._dijkstra(grafo, origem)
        else:
            log(f"ERRO: Origem {origem} não existe no grafo")

    def _dijkstra(self, grafo: Dict[str, Dict[str, int]], origem: str):
        # Inicializa dist e prev para todos os nós no grafo
        dist = {n: float('inf') for n in grafo}
        prev = {n: None for n in grafo}
        dist[origem] = 0
        heap = [(0, origem)]
        visitados = set()

        while heap:
            d, atual = heapq.heappop(heap)
            if atual in visitados:
                continue
                
            visitados.add(atual)
            
            if atual not in grafo:
                continue
                
            for vizinho, peso in grafo[atual].items():
                if vizinho not in grafo:
                    continue
                    
                alt = dist[atual] + peso
                if vizinho not in dist:
                    dist[vizinho] = float('inf')
                    prev[vizinho] = None
                    
                if alt < dist[vizinho]:
                    dist[vizinho] = alt
                    prev[vizinho] = atual
                    heapq.heappush(heap, (alt, vizinho))

        # Calcula rotas apenas para nós que foram alcançados
        for destino in grafo:
            if destino != origem and prev[destino] is not None:
                via = destino
                while prev[via] != origem and prev[via] is not None:
                    via = prev[via]
                if prev[via] == origem:  # Garante que existe caminho
                    self.rotas[destino] = (via, dist[destino])


class Router:
    def __init__(self, id: str, ip: str, vizinhos: Dict[str, Vizinho]):
        self.id = id
        self.ip = ip
        self.vizinhos = vizinhos
        self.seq = 0
        self.lsdb = LSDB()
        
        # Adiciona o próprio LSA ao LSDB
        self.lsdb.atualizar_lsa(self.criar_lsa())
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.ip, PORTA))
        log(f"{self.id} ouvindo na porta {PORTA} ({self.ip})")
        
        # Configurar rotas para subredes diretamente conectadas
        self._configurar_rotas_iniciais()
        
        threading.Thread(target=self.escutar_lsa, daemon=True).start()
        threading.Thread(target=self.enviar_periodicamente, daemon=True).start()
    
    def _configurar_rotas_iniciais(self):
        log(f"{self.id} configurando rotas iniciais...")
        # Configurar interfaces com endereços IP
        interfaces = subprocess.run(["ip", "addr"], capture_output=True, text=True, check=False).stdout
        log(f"{self.id} interfaces: {interfaces}")
        
        # Não limpar rotas, apenas listar para debug
        rotas = subprocess.run(["ip", "route"], capture_output=True, text=True, check=False).stdout
        log(f"{self.id} rotas iniciais: {rotas}")

    def criar_lsa(self) -> LSA:
        self.seq += 1
        return LSA(self.id, self.ip, self.seq, self.vizinhos)

    def enviar_lsa(self):
        if not self.vizinhos:
            log(f"{self.id} não tem vizinhos para enviar LSA")
            return
            
        lsa = self.criar_lsa()
        lsa_json = json.dumps(lsa.to_dict()).encode()
        
        enviados = []
        for viz_id, viz in self.vizinhos.items():
            try:
                self.socket.sendto(lsa_json, (viz.ip, PORTA))
                enviados.append(f"{viz_id}({viz.ip})")
            except Exception as e:
                log(f"{self.id} erro ao enviar LSA para {viz_id}: {e}")
        
        if enviados:
            log(f"{self.id} enviou LSA (seq {lsa.seq}) para: {', '.join(enviados)}")
        else:
            log(f"{self.id} falhou ao enviar LSA para qualquer vizinho")

    def escutar_lsa(self):
        while True:
            data, addr = self.socket.recvfrom(4096)
            lsa_dict = json.loads(data.decode())
            lsa = LSA.from_dict(lsa_dict)
            log(f"{self.id} recebeu LSA de {lsa.id} (seq {lsa.seq}) de {addr}")
            if self.lsdb.atualizar_lsa(lsa):
                log(f"{self.id} propagando LSA de {lsa.id} para vizinhos")
                self.propagar_lsa(lsa, addr)
                self.recalcular_rotas()

    def propagar_lsa(self, lsa: LSA, origem: Tuple[str, int]):
        for viz in self.vizinhos.values():
            if (viz.ip, PORTA) != origem:
                self.socket.sendto(json.dumps(lsa.to_dict()).encode(), (viz.ip, PORTA))
                log(f"{self.id} propagou LSA de {lsa.id} para {viz.ip}")

    def enviar_periodicamente(self):
        while True:
            self.enviar_lsa()
            time.sleep(10)

    def recalcular_rotas(self):
        grafo = self.lsdb.get_topologia()
        log(f"{self.id} recalculando rotas com topologia: {grafo}")
        tabela = TabelaRotas(grafo, self.id)
        log(f"{self.id} tabela de rotas calculada: {tabela.rotas}")
        self.aplicar_rotas(tabela)

    def aplicar_rotas(self, tabela: TabelaRotas):
        try:
            # Listar as rotas atuais para referência
            rotas_antes = subprocess.run(["ip", "route"], capture_output=True, text=True, check=False).stdout
            log(f"{self.id} rotas antes: {rotas_antes}")
            
            # NÃO limpar a tabela de rotas - isso remove rotas essenciais
            # Apenas adicionar ou modificar rotas conforme necessário
            
            # Adicionar rotas para destinos conhecidos
            for destino, (via, custo) in tabela.rotas.items():
                try:
                    if destino in self.lsdb.lsas and via in self.lsdb.lsas:
                        destino_ip = self.lsdb.lsas[destino].ip
                        via_ip = self.lsdb.lsas[via].ip
                        
                        # Verificar se já existe uma rota para este destino
                        rede_destino = '.'.join(destino_ip.split('.')[:3]) + '.0/24'
                        
                        log(f"{self.id} adicionando rota para {destino} ({rede_destino}) via {via} ({via_ip}) com custo {custo}")
                        
                        # Usar replace em vez de add para evitar erros de rota duplicada
                        # E não adicionar rota direta para nossos vizinhos - Docker já faz isso
                        if not any(viz.ip == destino_ip for viz in self.vizinhos.values()):
                            cmd = ["ip", "route", "replace", rede_destino, "via", via_ip]
                            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                            if result.returncode != 0:
                                log(f"{self.id} erro ao adicionar rota: {result.stderr}")
                            else:
                                log(f"{self.id} rota adicionada com sucesso")
                    else:
                        log(f"{self.id} não pode adicionar rota para {destino} via {via} - informações incompletas")
                except Exception as e:
                    log(f"{self.id} erro ao adicionar rota para {destino}: {e}")
            
            # Listar rotas após as modificações
            rotas_depois = subprocess.run(["ip", "route"], capture_output=True, text=True, check=False).stdout
            log(f"{self.id} rotas depois: {rotas_depois}")
        except Exception as e:
            log(f"{self.id} erro ao configurar rotas: {e}")

if __name__ == "__main__":
    log("Iniciando o roteador...")
    my_id = os.environ["my_name"]
    my_ip = os.environ["my_ip"]
    links = os.environ["router_links"].split(",")

    vizinhos = {}
    for nome in links:
        ip_env = os.environ.get(f"{nome}_ip")
        if ip_env:
            vizinhos[nome] = Vizinho(ip_env, 1)
            log(f"Adicionado vizinho {nome} com IP {ip_env}")
        else:
            log(f"AVISO: IP para {nome} não encontrado nas variáveis de ambiente")

    r = Router(my_id, my_ip, vizinhos)
    # Garantir que o LSA inicial seja enviado imediatamente
    r.enviar_lsa()
    
    while True:
        time.sleep(1)
