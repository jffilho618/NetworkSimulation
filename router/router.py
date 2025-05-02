import json
import os
import socket
import threading
import time
import subprocess
import netifaces
import ipaddress
from typing import Dict, Tuple
from formater import Formatter
from dycastra import dijkstra

PORTA = 5000
ROTEADOR_IP = os.environ["my_ip"]
ROTEADOR_NAME = os.environ["my_name"]
VIZINHOS = Formatter.formatar_vizinhos(os.environ.get("vizinhos", ""))
LOG_BASE_DIR = "/app/logs"

def log(categoria: str, msg: str, origem: str = ""):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"{timestamp} - {origem} - {msg}"
    print(log_msg)
    with open(f"{LOG_BASE_DIR}/{categoria}.log", "a") as f:
        f.write(log_msg + "\n")

class NetworkUtils:
    @staticmethod
    def _testar_ping(ip: str) -> Tuple[bool, float]:
        init_ping = time.time()
        try:
            result = subprocess.run(
                ["ping", "-c", "5", "-W", "1", ip],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            end_ping = time.time()
            return result.returncode == 0, end_ping - init_ping
        except Exception:
            return False, 0.0

    @staticmethod
    def realizar_pings(vizinhos: Dict[str, Tuple[str, int]]) -> Dict[str, Tuple[str, float]]:
        vizinhos_ativos = {}
        for viz, (ip, _) in vizinhos.items():
            is_alive, tempo_ping = NetworkUtils._testar_ping(ip)
            if is_alive:
                vizinhos_ativos[viz] = (ip, tempo_ping)
            else:
                log("lsa", f"Ping falhou para {viz} ({ip})", ROTEADOR_NAME)
        return vizinhos_ativos

class LSA:
    def __init__(self, id: str, seq: int, vizinhos: Dict[str, Tuple[str, float]]):
        self.id = id
        self.seq = seq
        self.vizinhos = vizinhos

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "seq": self.seq,
            "vizinhos": self.vizinhos
        }

class LSDB:
    def __init__(self):
        self.lsas: Dict[str, LSA] = {}

    def atualizar_lsa(self, lsa: LSA):
        if lsa.id not in self.lsas or lsa.seq > self.lsas[lsa.id].seq:
            self.lsas[lsa.id] = lsa
            log("lsa", f"Atualizou LSA de {lsa.id}, seq={lsa.seq}", ROTEADOR_NAME)
            return True
        return False

class NetworkInterface:
    @staticmethod
    def get_connected_subnets() -> set:
        """Retorna as sub-redes diretamente conectadas ao roteador."""
        subnets = set()
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr['addr']
                    mask = addr['netmask']
                    subnet = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
                    subnets.add(str(subnet))
        return subnets

    @staticmethod
    def obter_rotas_existentes(rotas: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
        rotas_existentes = {}
        rotas_adicionar = {}
        rotas_remover = {}
        rotas_replase = {}
        connected_subnets = NetworkInterface.get_connected_subnets()
        for destino, proximo_salto in rotas.items():
            if destino in connected_subnets:
                log("rotas", f"Sub-rede {destino} já está diretamente conectada, ignorando rota.", ROTEADOR_NAME)
                continue
            rotas_adicionar[destino] = proximo_salto
        try:
            resultado = subprocess.run(
                ["ip", "route", "show"],
                capture_output=True,
                text=True,
                check=True
            )
            for linha in resultado.stdout.splitlines():
                partes = linha.split()
                if partes[0] != "default" and partes[1] == "via":
                    rede = partes[0]
                    proximo_salto = partes[2]
                    rotas_existentes[rede] = proximo_salto
            for rede, proximo_salto in rotas_adicionar.items():
                if (rede in rotas_existentes) and (rotas_adicionar[rede] != rotas_existentes[rede]):
                    rotas_replase[rede] = proximo_salto
            for rede, proximo_salto in rotas_adicionar.items():
                if (rede not in rotas_existentes) and (rede not in rotas_replase):
                    rotas_adicionar[rede] = proximo_salto
            for rede, proximo_salto in rotas_existentes.items():
                if (rede not in rotas_adicionar) and (rede not in connected_subnets):
                    rotas_remover[rede] = proximo_salto
            return rotas_adicionar, rotas_remover, rotas_replase
        except Exception as e:
            log("erros", f"Erro ao obter rotas existentes: {e}", ROTEADOR_NAME)
            return {}, {}, {}

    @staticmethod
    def adicionar_interface(destino: str, proximo_salto: str) -> bool:
        try:
            subprocess.run(
                ["ip", "route", "add", destino, "via", proximo_salto],
                check=True
            )
            log("rotas", f"Rota adicionada: {destino} via {proximo_salto}", ROTEADOR_NAME)
            return True
        except subprocess.CalledProcessError as e:
            log("erros", f"Erro ao adicionar rota: {e}", ROTEADOR_NAME)
            return False

    @staticmethod
    def remover_interfaces(destino: str) -> bool:
        try:
            subprocess.run(
                ["ip", "route", "del", destino],
                check=True
            )
            log("rotas", f"Rota removida: {destino}", ROTEADOR_NAME)
            return True
        except subprocess.CalledProcessError as e:
            log("erros", f"Erro ao remover rota: {e}", ROTEADOR_NAME)
            return False

    @staticmethod
    def replase_interface(destino: str, proximo_salto: str) -> bool:
        try:
            subprocess.run(
                ["ip", "route", "replace", destino, "via", proximo_salto],
                check=True
            )
            log("rotas", f"Rota substituída: {destino} via {proximo_salto}", ROTEADOR_NAME)
            return True
        except subprocess.CalledProcessError as e:
            log("erros", f"Erro ao substituir rota: {e}", ROTEADOR_NAME)
            return False

    @staticmethod
    def salvar_lsdb_rotas_arquivo(lsdb: Dict[str, Dict], rotas: Dict[str, str]):
        try:
            with open("lsdb.json", "w") as f:
                json.dump(lsdb, f, indent=4)
            with open("rotas.json", "w") as f:
                json.dump(rotas, f, indent=4)
            log("rotas", "LSDB e rotas salvos em lsdb.json e rotas.json", ROTEADOR_NAME)
        except Exception as e:
            log("erros", f"Erro ao salvar LSDB/rotas: {e}", ROTEADOR_NAME)

class Router:
    def __init__(self):
        self.id = ROTEADOR_NAME
        self.ip = ROTEADOR_IP
        self.vizinhos = VIZINHOS
        self.lsdb = LSDB()
        self.seq = 0
        self.lsa_send_lock = threading.Lock()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        os.makedirs(LOG_BASE_DIR, exist_ok=True)
        log("init", f"Roteador inicializado com IP: {self.ip}, Vizinhos: {self.vizinhos}", self.id)

    def criar_lsa(self, vizinhos_ativos: Dict[str, Tuple[str, float]]) -> LSA:
        self.seq += 1
        lsa = LSA(self.ip, self.seq, vizinhos_ativos)
        log("lsa", f"Criou LSA seq={self.seq}, vizinhos={vizinhos_ativos}", self.id)
        return lsa

    def enviar_lsa(self):
        with self.lsa_send_lock:
            vizinhos_ativos = NetworkUtils.realizar_pings(self.vizinhos)
            if not vizinhos_ativos:
                log("lsa", "Nenhum vizinho ativo", self.id)
                return
            lsa = self.criar_lsa(vizinhos_ativos)
            lsa_json = json.dumps(lsa.to_dict()).encode()
            for viz_id, (ip, _) in vizinhos_ativos.items():
                try:
                    self.socket.sendto(lsa_json, (ip, PORTA))
                    log("lsa", f"Enviou LSA para {viz_id} ({ip})", self.id)
                except Exception as e:
                    log("erros", f"Erro ao enviar LSA para {viz_id}: {e}", self.id)
            self.lsdb.atualizar_lsa(lsa)
            self.vizinhos = vizinhos_ativos
            self.recalcular_rotas()

    def propagar_lsa(self, lsa_data: bytes, origem_ip: str):
        try:
            lsa_dict = json.loads(lsa_data.decode())
            lsa = LSA(lsa_dict["id"], lsa_dict["seq"], lsa_dict["vizinhos"])
            if self.lsdb.atualizar_lsa(lsa):
                for viz_id, (ip, _) in self.vizinhos.items():
                    if ip != origem_ip:
                        try:
                            self.socket.sendto(lsa_data, (ip, PORTA))
                            log("lsa", f"Propagou LSA de {lsa.id} para {viz_id}", self.id)
                        except Exception as e:
                            log("erros", f"Erro ao propagar LSA para {viz_id}: {e}", self.id)
                self.recalcular_rotas()
        except json.JSONDecodeError:
            log("erros", "Erro ao decodificar LSA recebido", self.id)
        except Exception as e:
            log("erros", f"Erro ao processar LSA: {e}", self.id)

    def recalcular_rotas(self):
        lsdb_formatted = {lsa.id: {"id": lsa.id, "vizinhos": lsa.vizinhos, "seq": lsa.seq} for lsa in self.lsdb.lsas.values()}
        rotas = dijkstra(self.ip, lsdb_formatted)
        rotas_validas = {}
        for destino, proximo_salto in rotas.items():
            for viz, (ip, _) in self.vizinhos.items():
                if proximo_salto == ip:
                    rotas_validas[destino] = proximo_salto
                    break
        NetworkInterface.salvar_lsdb_rotas_arquivo(lsdb_formatted, rotas_validas)
        rotas_adicionar, rotas_remover, rotas_replase = NetworkInterface.obter_rotas_existentes(rotas_validas)
        for destino in rotas_remover:
            NetworkInterface.remover_interfaces(destino)
        for destino, proximo_salto in rotas_adicionar.items():
            NetworkInterface.adicionar_interface(destino, proximo_salto)
        for destino, proximo_salto in rotas_replase.items():
            NetworkInterface.replase_interface(destino, proximo_salto)
        log("dijkstra", f"Rotas recalculadas: {rotas_validas}", self.id)

    def escutar_lsa(self):
        self.socket.bind(("0.0.0.0", PORTA))
        while True:
            try:
                data, addr = self.socket.recvfrom(4096)
                log("lsa", f"Recebeu LSA de {addr[0]}", self.id)
                self.propagar_lsa(data, addr[0])
            except Exception as e:
                log("erros", f"Erro ao receber LSA: {e}", self.id)

    def enviar_periodicamente(self):
        while True:
            self.enviar_lsa()
            time.sleep(5)

    def iniciar(self):
        threads = [
            threading.Thread(target=self.escutar_lsa, daemon=True, name="escutar_lsa"),
            threading.Thread(target=self.enviar_periodicamente, daemon=True, name="enviar_lsa")
        ]
        for t in threads:
            t.start()
        threading.Event().wait()

if __name__ == "__main__":
    router = Router()
    router.iniciar()