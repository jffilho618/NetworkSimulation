import socket
import time
import json
import os
import threading
import subprocess
from typing import Dict, Any, Set, Tuple, List, Optional
import heapq
import re
import random

PORTA = 5000
LOG_BASE_DIR = "/app/logs"

def criar_diretorios_logs():
    os.makedirs(LOG_BASE_DIR, exist_ok=True)

def log(categoria: str, msg: str, origem: str = ""):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_msg = f"{timestamp} - {origem} - {msg}" if origem else f"{timestamp} - {msg}"
    print(log_msg, flush=True)
    
    log_file = f"{LOG_BASE_DIR}/{categoria}.log"
    try:
        with open(log_file, "a") as f:
            f.write(log_msg + "\n")
    except Exception as e:
        print(f"Erro ao salvar log em {log_file}: {e}", flush=True)

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
            if not isinstance(v["peso"], int) or v["peso"] < 1:
                raise ValueError(f"Peso do vizinho '{k}' deve ser um inteiro positivo")
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
            log("lsa", f"LSA atualizado de {lsa.id} com seq {lsa.seq}", lsa.id)
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
            log("dijkstra", f"ERRO: Origem {origem} não existe no grafo", origem)

    def _dijkstra(self, grafo: Dict[str, Dict[str, int]], origem: str):
        for node in grafo:
            for vizinho, peso in grafo[node].items():
                if peso < 0:
                    log("dijkstra", f"ERRO: Peso negativo detectado na conexão {node} -> {vizinho}: {peso}", origem)
                    raise ValueError(f"Peso negativo inválido na conexão {node} -> {vizinho}")

        dist = {n: float('inf') for n in grafo}
        prev = {n: None for n in grafo}
        dist[origem] = 0
        heap = [(0, origem)]
        visitados = set()

        log("dijkstra", f"Iniciando Dijkstra a partir de {origem}", origem)
        log("dijkstra", f"Estado inicial: dist={dist}, heap={[(d, n) for d, n in heap]}", origem)

        while heap:
            d, atual = heapq.heappop(heap)
            if atual in visitados:
                log("dijkstra", f"Ignorando {atual}: já visitado", origem)
                continue
                
            visitados.add(atual)
            log("dijkstra", f"Processando {atual} com distância {d}", origem)
            
            if atual not in grafo:
                log("dijkstra", f"AVISO: {atual} não está no grafo, ignorando", origem)
                continue
                
            for vizinho, peso in grafo[atual].items():
                if vizinho not in grafo:
                    log("dijkstra", f"AVISO: Vizinho {vizinho} de {atual} não está no grafo, ignorando", origem)
                    continue
                    
                alt = dist[atual] + peso
                if vizinho not in dist:
                    dist[vizinho] = float('inf')
                    prev[vizinho] = None
                    
                if alt < dist[vizinho]:
                    dist[vizinho] = alt
                    prev[vizinho] = atual
                    heapq.heappush(heap, (alt, vizinho))
                    log("dijkstra", f"Atualizado: dist[{vizinho}]={alt}, prev[{vizinho}]={atual}", origem)
                else:
                    log("dijkstra", f"Sem atualização: dist[{vizinho}]={dist[vizinho]} é menor ou igual a {alt}", origem)

            log("dijkstra", f"Estado atual: dist={dist}, heap={[(d, n) for d, n in heap]}, visitados={visitados}", origem)

        for destino in grafo:
            if destino != origem and prev[destino] is not None:
                via = destino
                while prev[via] != origem and prev[via] is not None:
                    via = prev[via]
                if prev[via] == origem:
                    self.rotas[destino] = (via, dist[destino])
                    log("rotas", f"Rota calculada: {origem} -> {destino} via {via} com custo {dist[destino]}", origem)

        log("dijkstra", f"Dijkstra concluído. Rotas finais: {self.rotas}", origem)

class Router:
    def __init__(self, id: str, ip: str, vizinhos: Dict[str, Vizinho]):
        criar_diretorios_logs()
        self.id = id
        self.ip = ip
        self.vizinhos = vizinhos
        self.seq = 0
        self.lsdb = LSDB()
        self.lsa_hist: Set[Tuple[str, int]] = set()
        self.lsa_hist_lock = threading.Lock()
        self.lsa_send_lock = threading.Lock()
        self.last_connectivity_test = 0
        self.connectivity_test_interval = 30
        
        self.lsdb.atualizar_lsa(self.criar_lsa())
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.ip, PORTA))
        log("conectividade", f"Ouvindo na porta {PORTA} ({self.ip})", self.id)
        
        self._configurar_rotas_iniciais()
        
        self._testar_conectividade_inicial()
        time.sleep(5)
        
        threading.Thread(target=self.escutar_lsa, daemon=True).start()
        threading.Thread(target=self.enviar_periodicamente, daemon=True).start()
    
    def _configurar_rotas_iniciais(self):
        log("rotas", "Configurando rotas iniciais...", self.id)
        interfaces = subprocess.run(["ip", "addr"], capture_output=True, text=True, check=False).stdout
        log("conectividade", f"Interfaces: {interfaces}", self.id)
        
        rotas = subprocess.run(["ip", "route"], capture_output=True, text=True, check=False).stdout
        log("rotas", f"Rotas iniciais: {rotas}", self.id)

    def _testar_conectividade_inicial(self):
        log("testes_iniciais", "Iniciando testes de conectividade inicial...", self.id)
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
                packet_loss = self._get_packet_loss(result.stdout)
                if result.returncode == 0 and packet_loss == 0:
                    status = "SUCESSO"
                    sucessos += 1
                else:
                    status = f"FALHA (perda de pacotes: {packet_loss}%)"
                    falhas += 1
                log("testes_iniciais", f"Ping para vizinho {viz_id} ({viz.ip}): {status}\n{result.stdout}\n{result.stderr}", self.id)
            except subprocess.TimeoutExpired:
                log("testes_iniciais", f"Ping para vizinho {viz_id} ({viz.ip}): TIMEOUT", self.id)
                falhas += 1
            except Exception as e:
                log("testes_iniciais", f"Ping para vizinho {viz_id} ({viz.ip}): ERRO - {str(e)}", self.id)
                falhas += 1
        
        subrede_principal = {
            "router1": ["172.20.1.10", "172.20.1.11"],
            "router2": ["172.20.2.10", "172.20.2.11"],
            "router3": ["172.20.3.10", "172.20.3.11"],
            "router4": ["172.20.4.10", "172.20.4.11"],
            "router5": ["172.20.5.10", "172.20.5.11"]
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
                    packet_loss = self._get_packet_loss(result.stdout)
                    if result.returncode == 0 and packet_loss == 0:
                        status = "SUCESSO"
                        sucessos += 1
                    else:
                        status = f"FALHA (perda de pacotes: {packet_loss}%)"
                        falhas += 1
                    log("testes_iniciais", f"Ping para host {host_ip} na subrede principal: {status}\n{result.stdout}\n{result.stderr}", self.id)
                except subprocess.TimeoutExpired:
                    log("testes_iniciais", f"Ping para host {host_ip} na subrede principal: TIMEOUT", self.id)
                    falhas += 1
                except Exception as e:
                    log("testes_iniciais", f"Ping para host {host_ip} na subrede principal: ERRO - {str(e)}", self.id)
                    falhas += 1
        else:
            log("testes_iniciais", f"Não tem subrede principal definida para testar hosts", self.id)
        
        log("testes_iniciais", f"Resumo de conectividade inicial: {sucessos} SUCESSOS, {falhas} FALHAS", self.id)

    def _get_packet_loss(self, ping_output: str) -> float:
        match = re.search(r"(\d+\.?\d*)% packet loss", ping_output)
        if match:
            return float(match.group(1))
        return 100.0

    def criar_lsa(self) -> LSA:
        self.seq += 1
        return LSA(self.id, self.ip, self.seq, self.vizinhos)

    def enviar_lsa(self):
        with self.lsa_send_lock:
            if not self.vizinhos:
                log("lsa", f"Não tem vizinhos para enviar LSA", self.id)
                return
                
            lsa = self.criar_lsa()
            lsa_json = json.dumps(lsa.to_dict()).encode()
            
            enviados = []
            for viz_id, viz in self.vizinhos.items():
                try:
                    self.socket.sendto(lsa_json, (viz.ip, PORTA))
                    enviados.append(f"{viz_id}({viz.ip})")
                except Exception as e:
                    log("lsa", f"Erro ao enviar LSA para {viz_id}: {e}", self.id)
            
            if enviados:
                log("lsa", f"Enviou LSA (seq {lsa.seq}) para: {', '.join(enviados)}", self.id)
            else:
                log("lsa", f"Falhou ao enviar LSA para qualquer vizinho", self.id)

    def escutar_lsa(self):
        while True:
            try:
                data, addr = self.socket.recvfrom(4096)
                lsa_dict = json.loads(data.decode())
                lsa = LSA.from_dict(lsa_dict)
                log("lsa", f"Recebeu LSA de {lsa.id} (seq {lsa.seq}) de {addr}", self.id)
                if self.lsdb.atualizar_lsa(lsa):
                    log("lsa", f"Propagando LSA de {lsa.id} para vizinhos", self.id)
                    self.propagar_lsa(lsa, addr)
                self.recalcular_rotas()
            except json.JSONDecodeError as e:
                log("erros", f"Erro ao decodificar JSON de {addr}: {e}", self.id)
            except ValueError as e:
                log("erros", f"Pacote inválido recebido de {addr}: {e}", self.id)
            except Exception as e:
                log("erros", f"Erro ao processar LSA de {addr}: {e}", self.id)

    def propagar_lsa(self, lsa: LSA, remetente: Tuple[str, int]):
        try:
            remetente_ip = remetente[0]
            with self.lsa_hist_lock:
                lsa_id = f"{lsa.id}:{lsa.seq}"
                if lsa_id in self.lsa_hist:
                    log("lsa", f"Descartando LSA {lsa.id} (seq {lsa.seq}) - já propagado", self.id)
                    return
                self.lsa_hist.add(lsa_id)
                log("lsa", f"Adicionou LSA {lsa.id} (seq {lsa.seq}) ao histórico", self.id)
            
            lsa_json = json.dumps(lsa.to_dict()).encode()
            for viz_id, vizinho in self.vizinhos.items():
                if vizinho.ip != remetente_ip:
                    try:
                        self.socket.sendto(lsa_json, (vizinho.ip, PORTA))
                        log("lsa", f"Propagou LSA de {lsa.id} (seq {lsa.seq}) para {viz_id} ({vizinho.ip})", self.id)
                    except Exception as e:
                        log("lsa", f"Erro ao propagar LSA de {lsa.id} para {viz_id} ({vizinho.ip}): {e}", self.id)
        except Exception as e:
            log("erros", f"Erro geral ao propagar LSA {lsa.id} (seq {lsa.seq}): {e}", self.id)

    def enviar_periodicamente(self):
        while True:
            self.enviar_lsa()
            time.sleep(30)

    def recalcular_rotas(self):
        grafo = self.lsdb.get_topologia()
        log("rotas", f"Recalculando rotas com topologia: {grafo}", self.id)
        if len(self.lsdb.lsas) < len(self.vizinhos) + 1:
            log("rotas", f"LSDB incompleto, adiando recálculo de rotas", self.id)
            return
        tabela = TabelaRotas(grafo, self.id)
        log("rotas", f"Tabela de rotas calculada: {tabela.rotas}", self.id)
        self.aplicar_rotas(tabela)
        
        current_time = time.time()
        if current_time - self.last_connectivity_test < self.connectivity_test_interval:
            log("testes_pos_roteamento", f"Adiando teste de conectividade - intervalo mínimo não atingido", self.id)
            return
        self.last_connectivity_test = current_time

        test_hosts = {
            "router1": ["172.20.2.10", "172.20.2.11", "172.20.3.10", "172.20.3.11", "172.20.4.10", "172.20.4.11", "172.20.5.10", "172.20.5.11"],
            "router2": ["172.20.1.10", "172.20.1.11", "172.20.3.10", "172.20.3.11", "172.20.4.10", "172.20.4.11", "172.20.5.10", "172.20.5.11"],
            "router3": ["172.20.1.10", "172.20.1.11", "172.20.2.10", "172.20.2.11", "172.20.4.10", "172.20.4.11", "172.20.5.10", "172.20.5.11"],
            "router4": ["172.20.1.10", "172.20.1.11", "172.20.2.10", "172.20.2.11", "172.20.3.10", "172.20.3.11", "172.20.5.10", "172.20.5.11"],
            "router5": ["172.20.1.10", "172.20.1.11", "172.20.2.10", "172.20.2.11", "172.20.3.10", "172.20.3.11", "172.20.4.10", "172.20.4.11"]
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
                    packet_loss = self._get_packet_loss(result.stdout)
                    if result.returncode == 0 and packet_loss == 0:
                        status = "SUCESSO"
                        sucessos += 1
                    else:
                        status = f"FALHA (perda de pacotes: {packet_loss}%)"
                        falhas += 1
                    log("testes_pos_roteamento", f"Ping pós-roteamento para {host_ip}: {status}\n{result.stdout}\n{result.stderr}", self.id)
                except subprocess.TimeoutExpired:
                    log("testes_pos_roteamento", f"Ping pós-roteamento para {host_ip}: TIMEOUT", self.id)
                    falhas += 1
                except Exception as e:
                    log("testes_pos_roteamento", f"Ping pós-roteamento para {host_ip}: ERRO - {str(e)}", self.id)
                    falhas += 1
        
        log("testes_pos_roteamento", f"Resumo de conectividade pós-roteamento: {sucessos} SUCESSOS, {falhas} FALHAS", self.id)

    def aplicar_rotas(self, tabela: TabelaRotas):
        try:
            rotas_antes = subprocess.run(["ip", "route"], capture_output=True, text=True, check=False).stdout
            log("rotas", f"Rotas antes: {rotas_antes}", self.id)
            
            for destino, (via, custo) in tabela.rotas.items():
                try:
                    destino_ip = self.lsdb.lsas.get(destino, LSA(destino, "0.0.0.0", 0, {})).ip
                    via_ip = self.lsdb.lsas.get(via, LSA(via, "0.0.0.0", 0, {})).ip
                    
                    if destino_ip == "0.0.0.0" or via_ip == "0.0.0.0":
                        log("rotas", f"Não pode adicionar rota para {destino} via {via} - IPs desconhecidos", self.id)
                        continue
                    
                    rede_destino = '.'.join(destino_ip.split('.')[:3]) + '.0/24'
                    
                    log("rotas", f"Adicionando rota para {destino} ({rede_destino}) via {via} ({via_ip}) com custo {custo}", self.id)
                    
                    if not any(viz.ip == destino_ip for viz in self.vizinhos.values()):
                        cmd = ["ip", "route", "replace", rede_destino, "via", via_ip]
                        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
                        if result.returncode != 0:
                            log("rotas", f"Erro ao adicionar rota: {result.stderr}", self.id)
                        else:
                            log("rotas", f"Rota adicionada com sucesso", self.id)
                    else:
                        log("rotas", f"Rota para {destino} ({rede_destino}) ignorada - destino é vizinho direto", self.id)
                except Exception as e:
                    log("erros", f"Erro ao adicionar rota para {destino}: {e}", self.id)
            
            rotas_depois = subprocess.run(["ip", "route"], capture_output=True, text=True, check=False).stdout
            log("rotas", f"Rotas depois: {rotas_depois}", self.id)
        except Exception as e:
            log("erros", f"Erro ao configurar rotas: {e}", self.id)

if __name__ == "__main__":
    criar_diretorios_logs()
    log("inicializacao", "Iniciando o roteador...")
    my_id = os.environ["my_name"]
    my_ip = os.environ["my_ip"]
    links = os.environ["router_links"].split(",")

    vizinhos = {}
    for nome in links:
        ip_env = os.environ.get(f"{nome}_ip")
        if ip_env:
            # Gerar um peso aleatório entre 1 e 10, usando semente determinística
            seed = hash(f"{min(my_id, nome)}:{max(my_id, nome)}") % 2**32
            random.seed(seed)
            peso = random.randint(1, 10)
            vizinhos[nome] = Vizinho(ip_env, peso)
            log("conectividade", f"Adicionado vizinho {nome} com IP {ip_env} e peso {peso}", my_id)
        else:
            log("erros", f"AVISO: IP para {nome} não encontrado nas variáveis de ambiente", my_id)

    r = Router(my_id, my_ip, vizinhos)
    
    while True:
        time.sleep(1)