import os
import threading
import time

# Definições de cores para saída no console (tons alterados)
class CoresSaida:
    VERMELHO_VIVO =   "\033[1;31m" # Vermelho mais brilhante
    VERDE_LIMA =    "\033[1;32m" # Verde mais brilhante
    AZUL_CELESTE =  "\033[1;34m" # Azul mais brilhante
    AMARELO_OURO =  "\033[1;33m" # Amarelo mais brilhante
    CIANO_CLARO =   "\033[1;36m" # Ciano mais brilhante
    ROXO_VIOLETA =  "\033[1;35m" # Magenta/Roxo mais brilhante
    SEM_COR =       "\033[0m"

# Determina um número razoável de threads de trabalho concorrentes
CPUS_DISPONIVEIS = os.cpu_count() or 1
MAX_THREADS_CONCORRENTES = CPUS_DISPONIVEIS * 4 # Um multiplicador comum para tarefas limitadas por E/S

# Mapeamento de nomes curtos de hosts para seus respectivos endereços IP
IPS_HOSTS_ALVO = {
    "host1a": "172.20.1.10",
    "host1b": "172.20.1.11",
    "host2a": "172.20.2.10",
    "host2b": "172.20.2.11",
    "host3a": "172.20.3.10",
    "host3b": "172.20.3.11",
    "host4a": "172.20.4.10",
    "host4b": "172.20.4.11",
    "host5a": "172.20.5.10",
    "host5b": "172.20.5.11"
}

def buscar_containers_usuario_ativos():
    """Lê os nomes dos containers de host ativos usando os.popen e docker ps."""
    saida_docker = os.popen("docker ps --filter \"name=host\" --format \"{{.Names}}\"").read()
    return sorted(saida_docker.splitlines())

def executar_ping_para_host(nome_container_origem, rotulo_host_alvo, endereco_ip_alvo, lista_resultados_ping, trava_lista_resultados):
    """Função da thread de trabalho: executa um comando de ping e armazena o resultado."""
    inicio_ping = time.time()
    # Constrói o comando de ping a ser executado dentro do container de origem
    string_comando_ping = f"docker exec {nome_container_origem} ping -c 5 -W 0.1 {endereco_ip_alvo} > /dev/null 2>&1"
    print(f"{CoresSaida.AMARELO_OURO}Executando: {string_comando_ping}{CoresSaida.SEM_COR}")

    status_saida = os.system(string_comando_ping)
    duracao_ping = time.time() - inicio_ping
    foi_bem_sucedido = (status_saida == 0)

    # Adiciona o resultado à lista compartilhada de forma segura
    with trava_lista_resultados:
        lista_resultados_ping.append((nome_container_origem, rotulo_host_alvo, foi_bem_sucedido, duracao_ping))

def realizar_teste_conectividade_entre_hosts():
    """Função principal para orquestrar testes de ping entre todos os hosts de usuário ativos e conhecidos."""
    lista_usuarios_ativos = buscar_containers_usuario_ativos()
    if not lista_usuarios_ativos:
        print(f"{CoresSaida.VERMELHO_VIVO}Erro: Nenhum container de host está atualmente em execução. Por favor, execute \"make up\" ou inicie-os manualmente.{CoresSaida.SEM_COR}")
        return
    
    # Filtra a lista de usuários ativos para incluir apenas aqueles definidos em IPS_HOSTS_ALVO
    hosts_conhecidos_e_ativos = [container_usuario for container_usuario in lista_usuarios_ativos if container_usuario.split("-")[1] in IPS_HOSTS_ALVO]
    
    # Prepara uma lista de tarefas de ping (host_origem, rotulo_host_alvo, ip_alvo)
    definicoes_trabalhos_ping = []
    for container_host_origem in hosts_conhecidos_e_ativos:
        for container_host_alvo in hosts_conhecidos_e_ativos:
            if container_host_origem == container_host_alvo: # Evita pingar a si mesmo
                continue
            nome_curto_host_alvo = container_host_alvo.split("-")[1]
            if nome_curto_host_alvo in IPS_HOSTS_ALVO:
                 definicoes_trabalhos_ping.append((container_host_origem, container_host_alvo, IPS_HOSTS_ALVO[nome_curto_host_alvo]))
    
    todos_resultados_ping = []
    threads_ping_ativas = []
    trava_lista_saida = threading.Lock()
    
    # Executa tarefas de ping usando um pool de threads
    for nome_h_origem, nome_h_alvo, ip_h_alvo in definicoes_trabalhos_ping:
        # Gerenciamento simples do pool de threads: espera se muitas threads estiverem ativa
        while len(threads_ping_ativas) >= MAX_THREADS_CONCORRENTES:
            threads_ping_ativas = [th for th in threads_ping_ativas if th.is_alive()] # Remove threads concluídas
            if len(threads_ping_ativas) >= MAX_THREADS_CONCORRENTES:
                time.sleep(0.05) # Breve pausa antes de verificar novamente

        thread_trabalhadora = threading.Thread(target=executar_ping_para_host, 
                                       args=(nome_h_origem, nome_h_alvo, ip_h_alvo, todos_resultados_ping, trava_lista_saida))
        thread_trabalhadora.start()
        threads_ping_ativas.append(thread_trabalhadora)
    
    # Espera todas as threads despachadas concluírem
    for item_thread_ping in threads_ping_ativas:
        item_thread_ping.join()
    
    # Agrega resultados para o resumo
    resumo_resultados_por_origem = {}
    for nome_origem, nome_alvo, sucesso, valor_tempo in todos_resultados_ping:
        resumo_resultados_por_origem.setdefault(nome_origem, []).append((nome_alvo, sucesso, valor_tempo))
    
    contagem_sucesso_geral = 0
    contagem_total_tentativas = len(todos_resultados_ping)
    
    # Imprime resumo dos resultados
    print(f"\n{CoresSaida.ROXO_VIOLETA}--- Resumo do Teste de Ping ---{CoresSaida.SEM_COR}")
    for chave_nome_host_origem in sorted(resumo_resultados_por_origem.keys()):
        print(f"\n{CoresSaida.CIANO_CLARO}Resultados do Host: {chave_nome_host_origem}{CoresSaida.SEM_COR}")
        
        for valor_nome_host_alvo, ping_bem_sucedido, valor_tempo_decorrido in resumo_resultados_por_origem[chave_nome_host_origem]:
            codigo_cor_status = CoresSaida.VERDE_LIMA if ping_bem_sucedido else CoresSaida.VERMELHO_VIVO
            mensagem_status = "SUCESSO" if ping_bem_sucedido else "FALHA"
            
            print(f"{codigo_cor_status}{chave_nome_host_origem} -> {valor_nome_host_alvo}: {mensagem_status} ({valor_tempo_decorrido:.2f}s){CoresSaida.SEM_COR}")
            if ping_bem_sucedido:
                contagem_sucesso_geral += 1
            
    print(f"\n{CoresSaida.ROXO_VIOLETA}Estatísticas Gerais - Total de Pings: {contagem_total_tentativas}, Bem-sucedidos: {contagem_sucesso_geral}, Falhas: {contagem_total_tentativas - contagem_sucesso_geral}{CoresSaida.SEM_COR}")

if __name__ == "__main__":
    realizar_teste_conectividade_entre_hosts()

