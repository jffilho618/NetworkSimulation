import socket
import time
import json
import os
import threading
import subprocess
from typing import Dict, Any, Set, Tuple, List, Optional
import heapq

PORTA = 5000
LOG_FILE = f"/app/logs/{os.environ.get('my_name', 'router')}_tests.log"

def log(msg: str):
    print(msg, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    except Exception as e:
        print(f"Erro ao salvar log em {LOG_FILE}: {e}", flush=True)

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
        required_fields = ["id", "ip", "seq", "vizinhos"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Campo obrigatório '{field}' ausente no LSA")
        
        if not isinstance(data["id"], str):
            raise ValueError("Campo 'id' deve ser uma string")
        if not isinstance(data["ip"], str):
            raise ValueError("Campo 'ip' deve ser uma string")
        if not isinstance(data["seq"], int):
            raise ValueError("Campo 'seq' deve ser um inteiro")
        if not isinstance(data["vizinhos"], dict):
            raise ValueError("Campo 'vizinhos' deve ser um dicionário")

        vizinhos = {}
        for k, v in data["vizinhos"].items():
            if not isinstance(k, str):
                raise ValueError(f"Chave de vizinho '{k}' deve ser uma string")
            if not isinstance(v, dict) or "ip" not in v or "peso" not in v:
                raise ValueError(f"Vizinho '{k}' deve ter campos 'ip' e 'peso'")
            if not isinstance(v["ip"], str):
                raise ValueError(f"IP do vizinho '{k}' deve ser uma string")
            if not isinstance(v["peso"], int):
                raise ValueError(f"Peso do vizinho '{k}' deve ser um inteiro")
            vizinhos[k] = Vizinho.from_dict(v)
        
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
        for lsa in self.lsas.values():
            grafo[lsa.id] = {}
            for vizinho_id in lsa.vizinhos:
                if vizinho_id not in grafo:
                    grafo[vizinho_id] = {}
        
        for lsa in self.lsas.values():
            for vizinho_id, vizinho in lsa.vizinhos.items():
                grafo[lsa.id][vizinho_id] = vizinho.peso
                if vizinho_id in grafo and lsa.id not in grafo[vizinho_id]:
                    grafo[vizinho_id][lsa.id] = vizinho.peso
                    
        return grafo

class TabelaRotas:
    def __init__(self, grafo: Dict[str, Dict[str, int]], origem: str):
        self.rotas: Dict[str, Tuple[str, int]] = {}
        if origem in grafo:
            self._dijkstra(grafo, origem)
        else:
            log(f"ERRO: Origem {origem} não existe no grafo")

    def _dijkstra(self, grafo: Dict[str, Dict[str, int]], origem: str):
        for node in grafo:
            for vizinho, peso in grafo[node].items():
                if peso < 0:
                    log(f"ERRO: Peso negativo detectado na conexão {node} -> {vizinho}: {peso}")
                    raise ValueError(f"Peso negativo inválido na conexão {node} -> {vizinho}")

        dist = {n: float('inf') for n in grafo}
        prev = {n: None for n in grafo}
        dist[origem] = 0
        heap = [(0, origem)]
        visitados = set()

        log(f"Iniciando Dijkstra a partir de {origem}")
        log(f"Estado inicial: dist={dist}, heap={[(d, n) for d, n in heap]}")

        while heap:
            d, atual = heapq.heappop(heap)
            if atual in visitados:
                log(f"Ignorando {atual}: já visitado")
                continue
                
            visitados.add(atual)
            log(f"Processando {atual} com distância {d}")
            
            if atual not in grafo:
                log(f"AVISO: {atual} não está no grafo, ignorando")
                continue
                
            for vizinho, peso in grafo[atual].items():
                if vizinho not in grafo:
                    log(f"AVISO: Vizinho {vizinho} de {atual} não está no grafo, ignorando")
                    continue
                    
                alt = dist[atual] + peso
                if vizinho not in dist:
                    dist[vizinho] = float('inf')
                    prev[vizinho] = None
                    
                if alt < dist[vizinho]:
                    dist[vizinho] = alt
                    prev[vizinho] = atual
                    heapq.heappush(heap, (alt, vizinho))
                    log(f"Atualizado: dist[{vizinho}]={alt}, prev[{vizinho}]={atual}")
                else:
                    log(f"Sem atualização: dist[{vizinho}]={dist[vizinho]} é menor ou igual a {alt}")

            log(f"Estado atual: dist={dist}, heap={[(d, n) for d, n in heap]}, visitados={visitados}")

        for destino in grafo:
            if destino != origem and prev[destino] is not None:
                via = destino
                while prev[via] != origem and prev[via] is not None:
                    via = prev[via]
                if prev[via] == origem:
                    self.rotas[destino] = (via, dist[destino])
                    log(f"Rota calculada: {origem} -> {destino} via {via} com custo {dist[destino]}")

        log(f"Dijkstra concluído. Rotas finais: {self.rotas}")

class Router:
    def __init__(self, id: str, ip: str, vizinhos: Dict[str, Vizinho]):
        self.id = id
        self.ip = ip
        self.vizinhos = vizinhos
        self.seq = 0
        self.lsdb = LSDB()
        
        self.lsdb.atualizar_lsa(self.criar_lsa())
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.ip, PORTA))
        log(f"{self.id} ouvindo na porta {PORTA} ({self.ip})")
        
        self._configurar_rotas_iniciais()
        
        self._testar_conectividade_inicial()
        time.sleep(5)
        
        threading.Thread(target=self.escutar_lsa, daemon=True).start()
        threading.Thread(target=self.enviar_periodicamente, daemon=True).start()
    
    def _configurar_rotas_iniciais(self):
        log(f"{self.id} configurando rotas iniciais...")
        interfaces = subprocess.run(["ip", "addr"], capture_output=True, text=True, check=False).stdout
        log(f"{self.id} interfaces: {interfaces}")
        
        rotas = subprocess.run(["ip", "route"], capture_output=True, text=True, check=False).stdout
        log(f"{self.id} rotas iniciais: {rotas}")

    def _testar_conectividade_inicial(self):
        log(f"{self.id} iniciando testes de conectividade inicial...")
        sucessos = 0
        falhas = 0
        
        for viz_id, viz in self.vizinhos.items():
            try:
                result = subprocess.run(
                    ["ping", "-c", "3", viz.ip],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                status = "SUCESSO" if result.returncode == 0 else "FALHA"
                if result.returncode == 0:
                    sucessos += 1
                else:
                    falhas += 1
                log(f"Ping para vizinho {viz_id} ({viz.ip}): {status}\n{result.stdout}\n{result.stderr}")
            except subprocess.TimeoutExpired:
                log(f"Ping para vizinho {viz_id} ({viz.ip}): TIMEOUT")
                falhas += 1
            except Exception as e:
                log(f"Ping para vizinho {viz_id} ({viz.ip}): ERRO - {str(e)}")
                falhas += 1
        
        subrede_principal = {
            "router1": ["172.20.1.10", "172.20.1.11"],
            "router2": ["172.20.2.10", "172.20.2.11"],
            "router3": ["172.20.3.10", "172.20.3.11"]
        }
        
        if self.id in subrede_principal:
            for host_ip in subrede_principal[self.id]:
                try:
                    result = subprocess.run(
                        ["ping", "-c", "3", host_ip],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    status = "SUCESSO" if result.returncode == 0 else "FALHA"
                    if result.returncode == 0:
                        sucessos += 1
                    else:
                        falhas += 1
                    log(f"Ping para host {host_ip} na subrede principal: {status}\n{result.stdout}\n{result.stderr}")
                except subprocess.TimeoutExpired:
                    log(f"Ping para host {host_ip} na subrede principal: TIMEOUT")
                    falhas += 1
                except Exception as e:
                    log(f"Ping para host {host_ip} na subrede principal: ERRO - {str(e)}")
                    falhas += 1
        else:
            log(f"{self.id} não tem subrede principal definida para testar hosts")
        
        log(f"{self.id} resumo de conectividade inicial: {sucessos} SUCESSOS, {falhas} FALHAS")

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
            try:
                data, addr = self.socket.recvfrom(4096)
                lsa_dict = json.loads(data.decode())
                lsa = LSA.from_dict(lsa_dict)
                log(f"{self.id} recebeu LSA de {lsa.id} (seq {lsa.seq}) de {addr}")
                if self.lsdb.atualizar_lsa(lsa):
                    log(f"{self.id} propagando LSA de {lsa.id} para vizinhos")
                    self.propagar_lsa(lsa, addr)
                    self.recalcular_rotas()
            except json.JSONDecodeError as e:
                log(f"{self.id} erro ao decodificar JSON de {addr}: {e}")
            except ValueError as e:
                log(f"{self.id} pacote inválido recebido de {addr}: {e}")
            except Exception as e:
                log(f"{self.id} erro ao processar LSA de {addr}: {e}")

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
        if len(self.lsdb.lsas) < len(self.vizinhos) + 1:
            log(f"{self.id} LSDB incompleto, adiando recálculo de rotas")
            return
        tabela = TabelaRotas(grafo, self.id)
        log(f"{self.id} tabela de rotas calculada: {tabela.rotas}")
        self.aplicar_rotas(tabela)
        
        # Teste de conectividade pós-roteamento
        test_hosts = {
            "router1": ["172.20.2.10", "172.20.2.11", "172.20.3.10", "172.20.3.11"],
            "router2": ["172.20.1.10", "172.20.1.11", "172.20.3.10", "172.20.3.11"],
            "router3": ["172.20.1.10", "172.20.1.11", "172.20.2.10", "172.20.2.11"]
        }
        sucessos = 0
        falhas = 0
        
        if self.id in test_hosts:
            for host_ip in test_hosts[self.id]:
                try:
                    result = subprocess.run(
                        ["ping", "-c", "3", host_ip],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    status = "SUCESSO" if result.returncode == 0 else "FALHA"
                    if result.returncode == 0:
                        sucessos += 1
                    else:
                        falhas += 1
                    log(f"Ping pós-roteamento para {host_ip}: {status}\n{result.stdout}\n{result.stderr}")
                except subprocess.TimeoutExpired:
                    log(f"Ping pós-roteamento para {host_ip}: TIMEOUT")
                    falhas += 1
                except Exception as e:
                    log(f"Ping pós-roteamento para {host_ip}: ERRO - {str(e)}")
                    falhas += 1
        
        log(f"{self.id} resumo de conectividade pós-roteamento: {sucessos} SUCESSOS, {falhas} FALHAS")

    def aplicar_rotas(self, tabela: TabelaRotas):
        try:
            rotas_antes = subprocess.run(["ip", "route"], capture_output=True, text=True, check=False).stdout
            log(f"{self.id} rotas antes: {rotas_antes}")
            
            for destino, (via, custo) in tabela.rotas.items():
                try:
                    destino_ip = self.lsdb.lsas.get(destino, LSA(destino, "0.0.0.0", 0, {})).ip
                    via_ip = self.lsdb.lsas.get(via, LSA(via, "0.0.0.0", 0, {})).ip
                    
                    if destino_ip == "0.0.0.0" or via_ip == "0.0.0.0":
                        log(f"{self.id} não pode adicionar rota para {destino} via {via} - IPs desconhecidos")
                        continue
                    
                    rede_destino = '.'.join(destino_ip.split('.')[:3]) + '.0/24'
                    
                    log(f"{self.id} adicionando rota para {destino} ({rede_destino}) via {via} ({via_ip}) com custo {custo}")
                    
                    if not any(viz.ip == destino_ip for viz in self.vizinhos.values()):
                        cmd = ["ip", "route", "replace", rede_destino, "via", via_ip]
                        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                        if result.returncode != 0:
                            log(f"{self.id} erro ao adicionar rota: {result.stderr}")
                        else:
                            log(f"{self.id} rota adicionada com sucesso")
                    else:
                        log(f"{self.id} rota para {destino} ({rede_destino}) ignorada - destino é vizinho direto")
                except Exception as e:
                    log(f"{self.id} erro ao adicionar rota para {destino}: {e}")
            
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
    r.enviar_lsa()
    
    while True:
        time.sleep(1)