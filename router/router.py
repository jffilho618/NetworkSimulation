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
    def __init__(self, id: str, seq: int, vizinhos: Dict[str, Tuple[str, float]], subnets: set):
        self.id = id
        self.seq = seq
        self.vizinhos = vizinhos
        self.subnets = subnets  # Sub-redes diretamente conectadas

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "seq": self.seq,
            "vizinhos": self.vizinhos,
            "subnets": list(self.subnets)  # Converte o set para lista para serialização JSON
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
        """Retorna APENAS a sub-rede local principal do roteador."""
        subnets = set()
        my_main_ip = ROTEADOR_IP # IP principal do roteador
        log("subnets_debug", f"[get_subnets] Iniciando busca pela sub-rede de {my_main_ip}", ROTEADOR_NAME)
        for iface in netifaces.interfaces():
            log("subnets_debug", f"[get_subnets] Verificando interface: {iface}", ROTEADOR_NAME)
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get("addr")
                    mask = addr.get("netmask")
                    log("subnets_debug", f"[get_subnets]   - Encontrado IP: {ip}, Máscara: {mask}", ROTEADOR_NAME)
                    if ip == my_main_ip:
                        log("subnets_debug", f"[get_subnets]   - IP {ip} corresponde ao IP principal!", ROTEADOR_NAME)
                        # Ignora loopback e endereços link-local (redundante, mas seguro)
                        if ip.startswith("127.") or ip.startswith("169.254."):
                            log("subnets_debug", f"[get_subnets]   - Ignorando IP de loopback/link-local.", ROTEADOR_NAME)
                            continue
                        if not mask:
                            log("erros", f"[get_subnets] IP principal {ip} encontrado sem máscara na interface {iface}. Pulando.", ROTEADOR_NAME)
                            continue
                        try:
                            # Calcula a rede usando o IP principal e sua máscara
                            subnet = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
                            subnet_str = str(subnet)
                            log("subnets_debug", f"[get_subnets]   - Sub-rede calculada: {subnet_str}", ROTEADOR_NAME)
                            subnets.add(subnet_str)
                            # Encontrou a sub-rede principal, pode parar a busca
                            log("subnets_debug", f"[get_subnets] Sub-rede principal {subnet_str} encontrada e adicionada. Finalizando busca.", ROTEADOR_NAME)
                            return subnets
                        except ValueError:
                            log("erros", f"[get_subnets] Endereço IP/Máscara inválido encontrado para IP principal: {ip}/{mask}", ROTEADOR_NAME)
                        except Exception as e:
                            log("erros", f"[get_subnets] Erro inesperado ao calcular sub-rede para {ip}/{mask}: {e}", ROTEADOR_NAME)
                    # else: # Log opcional para IPs que não são o principal
                    #    log("subnets_debug", f"[get_subnets]   - IP {ip} não é o principal ({my_main_ip}). Ignorando.", ROTEADOR_NAME)

        if not subnets:
            log("erros", f"[get_subnets] ATENÇÃO: Nenhuma sub-rede correspondente ao IP principal {my_main_ip} foi encontrada! Retornando conjunto vazio.", ROTEADOR_NAME)
        return subnets

    @staticmethod
    def obter_rotas_existentes(rotas_calculadas: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
        rotas_existentes_kernel = {}
        rotas_adicionar = {}
        rotas_remover = {}
        rotas_substituir = {}
        connected_subnets = NetworkInterface.get_connected_subnets()
        log("rotas_debug", f"Sub-redes conectadas: {connected_subnets}", ROTEADOR_NAME)
        log("rotas_debug", f"Rotas calculadas por Dijkstra (válidas): {rotas_calculadas}", ROTEADOR_NAME)

        # 1. Obter rotas atuais do kernel
        try:
            resultado = subprocess.run(
                ["ip", "route", "show"],
                capture_output=True,
                text=True,
                check=True
            )
            for linha in resultado.stdout.splitlines():
                partes = linha.split()
                # Ignora rotas default, rotas diretamente conectadas (sem 'via'), rotas de link local
                if partes[0] == "default" or "via" not in partes or partes[0].startswith("169.254"):
                    continue
                rede = partes[0]
                proximo_salto = partes[partes.index("via") + 1]
                rotas_existentes_kernel[rede] = proximo_salto
            log("rotas_debug", f"Rotas existentes no kernel (filtradas): {rotas_existentes_kernel}", ROTEADOR_NAME)
        except Exception as e:
            log("erros", f"Erro ao obter rotas existentes do kernel: {e}", ROTEADOR_NAME)
            return {}, {}, {}

        # 2. Comparar rotas calculadas com as existentes
        for destino_calc, prox_salto_calc in rotas_calculadas.items():
            # Ignora rotas para sub-redes diretamente conectadas
            if destino_calc in connected_subnets:
                log("rotas_debug", f"Ignorando rota calculada para sub-rede conectada: {destino_calc}", ROTEADOR_NAME)
                continue

            if destino_calc in rotas_existentes_kernel:
                prox_salto_kernel = rotas_existentes_kernel[destino_calc]
                if prox_salto_kernel != prox_salto_calc:
                    # Rota existe, mas próximo salto é diferente -> Substituir
                    rotas_substituir[destino_calc] = prox_salto_calc
                    log("rotas_debug", f"Marcando para SUBSTITUIR: {destino_calc} via {prox_salto_calc} (era via {prox_salto_kernel})", ROTEADOR_NAME)
                # else: Rota já existe e está correta -> Não fazer nada
                #    log("rotas_debug", f"Rota para {destino_calc} via {prox_salto_calc} já existe e está correta.", ROTEADOR_NAME)
            else:
                # Rota não existe no kernel -> Adicionar
                rotas_adicionar[destino_calc] = prox_salto_calc
                log("rotas_debug", f"Marcando para ADICIONAR: {destino_calc} via {prox_salto_calc}", ROTEADOR_NAME)

        # 3. Identificar rotas a remover (existem no kernel, mas não nas calculadas)
        for destino_kernel, prox_salto_kernel in rotas_existentes_kernel.items():
            if destino_kernel not in rotas_calculadas:
                # Rota existe no kernel, mas não foi calculada (e não é conectada) -> Remover
                if destino_kernel not in connected_subnets:
                     rotas_remover[destino_kernel] = prox_salto_kernel # Guardamos o prox_salto só por log
                     log("rotas_debug", f"Marcando para REMOVER: {destino_kernel} via {prox_salto_kernel} (não calculada)", ROTEADOR_NAME)

        return rotas_adicionar, rotas_remover, rotas_substituir

    @staticmethod
    def adicionar_interface(destino: str, proximo_salto: str) -> bool:
        comando = ["ip", "route", "add", destino, "via", proximo_salto]
        log("rotas_cmd", f"Executando comando: {' '.join(comando)}", ROTEADOR_NAME) # LOG ADICIONADO
        try:
            resultado = subprocess.run(
                comando,
                check=True,
                capture_output=True, # Captura stdout/stderr
                text=True # Decodifica stdout/stderr
            )
            log("rotas", f"Rota adicionada: {destino} via {proximo_salto}", ROTEADOR_NAME)
            return True
        except subprocess.CalledProcessError as e:
            # Log mais detalhado do erro
            log("erros", f"Erro ao adicionar rota {destino} via {proximo_salto}. Comando: {' '.join(comando)}. Erro: {e.stderr.strip()}", ROTEADOR_NAME)
            return False
        except Exception as e:
            log("erros", f"Erro inesperado ao adicionar rota {destino} via {proximo_salto}: {e}", ROTEADOR_NAME)
            return False

    @staticmethod
    def remover_interfaces(destino: str) -> bool:
        comando = ["ip", "route", "del", destino]
        log("rotas_cmd", f"Executando comando: {' '.join(comando)}", ROTEADOR_NAME) # LOG ADICIONADO
        try:
            resultado = subprocess.run(
                comando,
                check=True,
                capture_output=True, # Captura stdout/stderr
                text=True # Decodifica stdout/stderr
            )
            log("rotas", f"Rota removida: {destino}", ROTEADOR_NAME)
            return True
        except subprocess.CalledProcessError as e:
            # Log mais detalhado do erro, verifica se a rota já não existe
            if "No such process" in e.stderr or "Network is unreachable" in e.stderr or "Cannot find device" in e.stderr:
                 log("rotas_debug", f"Tentativa de remover rota inexistente {destino}. Ignorando erro.", ROTEADOR_NAME)
                 return True # Considera sucesso se a rota já não existe
            log("erros", f"Erro ao remover rota {destino}. Comando: {' '.join(comando)}. Erro: {e.stderr.strip()}", ROTEADOR_NAME)
            return False
        except Exception as e:
            log("erros", f"Erro inesperado ao remover rota {destino}: {e}", ROTEADOR_NAME)
            return False

    @staticmethod
    def replase_interface(destino: str, proximo_salto: str) -> bool:
        comando = ["ip", "route", "replace", destino, "via", proximo_salto]
        log("rotas_cmd", f"Executando comando: {' '.join(comando)}", ROTEADOR_NAME) # LOG ADICIONADO
        try:
            resultado = subprocess.run(
                comando,
                check=True,
                capture_output=True, # Captura stdout/stderr
                text=True # Decodifica stdout/stderr
            )
            log("rotas", f"Rota substituída/adicionada: {destino} via {proximo_salto}", ROTEADOR_NAME)
            return True
        except subprocess.CalledProcessError as e:
            # Log mais detalhado do erro
            log("erros", f"Erro ao substituir/adicionar rota {destino} via {proximo_salto}. Comando: {' '.join(comando)}. Erro: {e.stderr.strip()}", ROTEADOR_NAME)
            return False
        except Exception as e:
            log("erros", f"Erro inesperado ao substituir/adicionar rota {destino} via {proximo_salto}: {e}", ROTEADOR_NAME)
            return False

    @staticmethod
    def salvar_lsdb_rotas_arquivo(lsdb: Dict[str, Dict], rotas: Dict[str, str]):
        try:
            with open(f"{LOG_BASE_DIR}/lsdb_latest.json", "w") as f:
                json.dump(lsdb, f, indent=4)
            with open(f"{LOG_BASE_DIR}/rotas_latest.json", "w") as f:
                json.dump(rotas, f, indent=4)
            # log("rotas", "LSDB e rotas salvos em arquivos JSON", ROTEADOR_NAME)
        except Exception as e:
            log("erros", f"Erro ao salvar LSDB/rotas em JSON: {e}", ROTEADOR_NAME)

class Router:
    def __init__(self):
        self.id = ROTEADOR_NAME
        self.ip = ROTEADOR_IP
        self.vizinhos = VIZINHOS # Vizinhos configurados inicialmente
        self.vizinhos_ativos = {} # Vizinhos que responderam ao último ping
        self.lsdb = LSDB()
        self.seq = 0
        self.lsa_send_lock = threading.Lock()
        self.route_calc_lock = threading.Lock()
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.last_lsdb_hash = None
        os.makedirs(LOG_BASE_DIR, exist_ok=True)
        log("init", f"Roteador inicializado com IP: {self.ip}, Vizinhos Config: {self.vizinhos}", self.id)

    def criar_lsa(self) -> LSA:
        self.seq += 1
        connected_subnets = NetworkInterface.get_connected_subnets()
        # Usa self.vizinhos_ativos (resultado do ping) para o LSA
        lsa = LSA(self.ip, self.seq, self.vizinhos_ativos, connected_subnets)
        log("lsa", f"Criou LSA seq={self.seq}, vizinhos_ativos={self.vizinhos_ativos}, subnets={connected_subnets}", self.id)
        return lsa

    def enviar_lsa(self):
        with self.lsa_send_lock:
            # Atualiza a lista de vizinhos ativos ANTES de criar o LSA
            self.vizinhos_ativos = NetworkUtils.realizar_pings(self.vizinhos)
            if not self.vizinhos_ativos:
                log("lsa", "Nenhum vizinho ativo detectado por ping", self.id)
                # Mesmo sem vizinhos ativos, cria e envia LSA com subnets locais
                # return # Não retorna mais, envia LSA mesmo sem vizinhos

            lsa = self.criar_lsa() # Agora usa self.vizinhos_ativos
            lsa_json = json.dumps(lsa.to_dict()).encode()

            # Envia para TODOS os vizinhos configurados inicialmente
            # Isso garante que mesmo vizinhos temporariamente inativos recebam o LSA quando voltarem
            for viz_id, (ip, _) in self.vizinhos.items():
                try:
                    self.socket.sendto(lsa_json, (ip, PORTA))
                    log("lsa", f"Enviou LSA para vizinho configurado {viz_id} ({ip})", self.id)
                except Exception as e:
                    log("erros", f"Erro ao enviar LSA para {viz_id}: {e}", self.id)

            # Atualiza o próprio LSDB com o LSA recém-criado
            if self.lsdb.atualizar_lsa(lsa):
                 self.recalcular_rotas() # Recalcula rotas se o próprio LSA mudou

    def propagar_lsa(self, lsa_data: bytes, origem_ip: str):
        try:
            lsa_dict = json.loads(lsa_data.decode())
            subnets = set(lsa_dict.get("subnets", []))
            # Recria vizinhos como dicionário para consistência
            vizinhos_lsa = lsa_dict.get("vizinhos", {})
            lsa = LSA(lsa_dict["id"], lsa_dict["seq"], vizinhos_lsa, subnets)

            # Atualiza LSDB e verifica se houve mudança
            if self.lsdb.atualizar_lsa(lsa):
                log("lsa", f"LSDB atualizado com LSA de {lsa.id} (seq {lsa.seq}) vindo de {origem_ip}", self.id)
                # Propaga para vizinhos ativos, exceto a origem do LSA
                for viz_id, (ip, _) in self.vizinhos_ativos.items():
                    if ip != origem_ip:
                        try:
                            self.socket.sendto(lsa_data, (ip, PORTA))
                            log("lsa", f"Propagou LSA de {lsa.id} para vizinho ativo {viz_id} ({ip})", self.id)
                        except Exception as e:
                            log("erros", f"Erro ao propagar LSA para {viz_id}: {e}", self.id)
                # Recalcula rotas APÓS atualizar LSDB
                self.recalcular_rotas()
            # else: # Opcional: Logar se LSA recebido for antigo/duplicado
            #    log("lsa_debug", f"LSA de {lsa.id} (seq {lsa.seq}) vindo de {origem_ip} ignorado (antigo ou duplicado).", self.id)

        except json.JSONDecodeError:
            log("erros", f"Erro ao decodificar LSA JSON recebido de {origem_ip}", self.id)
        except KeyError as e:
             log("erros", f"Campo faltando no LSA recebido de {origem_ip}: {e}", self.id)
        except Exception as e:
            log("erros", f"Erro geral ao processar/propagar LSA de {origem_ip}: {e}", self.id)

    def recalcular_rotas(self):
        with self.route_calc_lock:
            log("rotas", "Iniciando recálculo de rotas...", self.id)
            # Formata o LSDB para o Dijkstra (incluindo subnets)
            lsdb_formatted = {lsa.id: lsa.to_dict() for lsa in self.lsdb.lsas.values()}

            # Verifica se o LSDB mudou desde a última execução
            lsdb_hash = json.dumps(lsdb_formatted, sort_keys=True)
            if self.last_lsdb_hash == lsdb_hash:
                log("rotas", "LSDB não mudou, pulando recálculo.", self.id)
                return
            self.last_lsdb_hash = lsdb_hash
            log("rotas_debug", f"LSDB mudou. Hash: {hash(lsdb_hash)}", self.id)

            # Salva o LSDB atual em arquivo para depuração
            NetworkInterface.salvar_lsdb_rotas_arquivo(lsdb_formatted, {}) # Salva LSDB antes de Dijkstra

            log("dijkstra_debug", f"Chamando Dijkstra com origem={self.ip} e LSDB:", self.id)
            log("dijkstra_debug", json.dumps(lsdb_formatted, indent=2), self.id) # Log do LSDB completo

            try:
                # Executa Dijkstra
                rotas_calculadas = dijkstra(self.ip, lsdb_formatted)
                log("dijkstra_debug", f"Dijkstra retornou: {rotas_calculadas}", self.id)
            except Exception as e:
                log("erros", f"Erro durante execução do Dijkstra: {e}", self.id)
                return # Aborta se Dijkstra falhar

            # Filtra rotas para garantir que o próximo salto seja um vizinho ativo
            # (Esta lógica parece redundante se Dijkstra já faz isso, mas mantemos por segurança)
            rotas_validas = {}
            for destino, proximo_salto in rotas_calculadas.items():
                is_valid_next_hop = False
                # Verifica se proximo_salto é o IP de algum vizinho ATIVO
                for viz_ip, _ in self.vizinhos_ativos.values():
                    if proximo_salto == viz_ip:
                        rotas_validas[destino] = proximo_salto
                        is_valid_next_hop = True
                        break
                if not is_valid_next_hop:
                     log("rotas_debug", f"Rota para {destino} via {proximo_salto} descartada (próximo salto não é vizinho ativo: {list(self.vizinhos_ativos.values())})", self.id)

            log("rotas", f"Rotas válidas após filtro de vizinhos ativos: {rotas_validas}", self.id)
            # Salva as rotas válidas calculadas
            NetworkInterface.salvar_lsdb_rotas_arquivo(lsdb_formatted, rotas_validas)

            # Compara com rotas do kernel e determina ações
            rotas_adicionar, rotas_remover, rotas_substituir = NetworkInterface.obter_rotas_existentes(rotas_validas)

            # Aplica as mudanças na tabela de roteamento do kernel
            log("rotas", f"Aplicando mudanças: ADD={list(rotas_adicionar.keys())}, REMOVE={list(rotas_remover.keys())}, REPLACE={list(rotas_substituir.keys())}", self.id)
            erros_aplicacao = 0
            for destino in rotas_remover:
                if not NetworkInterface.remover_interfaces(destino):
                    erros_aplicacao += 1
            for destino, proximo_salto in rotas_adicionar.items():
                if not NetworkInterface.adicionar_interface(destino, proximo_salto):
                     erros_aplicacao += 1
            for destino, proximo_salto in rotas_substituir.items():
                if not NetworkInterface.replase_interface(destino, proximo_salto):
                     erros_aplicacao += 1

            if erros_aplicacao > 0:
                 log("erros", f"{erros_aplicacao} erro(s) ao aplicar rotas no kernel.", self.id)
            else:
                 log("rotas", "Todas as mudanças de rota aplicadas com sucesso.", self.id)

    def escutar_lsa(self):
        try:
            self.socket.bind(("0.0.0.0", PORTA))
            log("init", f"Socket vinculado a 0.0.0.0:{PORTA}", self.id)
        except Exception as e:
            log("erros", f"Falha ao vincular socket: {e}", self.id)
            return # Não pode continuar sem socket

        while True:
            try:
                data, addr = self.socket.recvfrom(4096)
                log("lsa", f"Recebeu {len(data)} bytes de {addr[0]}", self.id)
                # Inicia processamento em nova thread para não bloquear o recebimento
                threading.Thread(target=self.propagar_lsa, args=(data, addr[0]), daemon=True).start()
            except Exception as e:
                log("erros", f"Erro no loop de recebimento de LSA: {e}", self.id)
                time.sleep(1) # Evita busy-loop em caso de erro contínuo

    def enviar_periodicamente(self):
        # Espera inicial para permitir que a rede estabilize um pouco
        time.sleep(5)
        while True:
            try:
                self.enviar_lsa()
            except Exception as e:
                log("erros", f"Erro no loop de envio periódico de LSA: {e}", self.id)
            # Intervalo de envio periódico
            time.sleep(15) # Aumentado para 15 segundos

    def iniciar(self):
        log("init", "Iniciando threads do roteador...", self.id)
        threads = [
            threading.Thread(target=self.escutar_lsa, daemon=True, name="escutar_lsa"),
            threading.Thread(target=self.enviar_periodicamente, daemon=True, name="enviar_lsa")
        ]
        for t in threads:
            t.start()
        log("init", "Threads iniciadas. Roteador em execução.", self.id)
        # Mantém a thread principal viva
        try:
            while True:
                time.sleep(3600) # Dorme por uma hora, efetivamente esperando para sempre
        except KeyboardInterrupt:
            log("init", "Recebido sinal de interrupção. Encerrando...", self.id)
            # Aqui poderiam ser adicionadas lógicas de cleanup, se necessário

if __name__ == "__main__":
    router = Router()
    router.iniciar()

