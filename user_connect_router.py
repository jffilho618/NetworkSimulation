import os
import threading
import time

# Definições de cores para saída no console (tons alterados)
class CoresTerminal:
    FALHA_CRITICA = "\033[1;91m" # Vermelho Brilhante
    SUCESSO_VIVO =  "\033[1;92m" # Verde Brilhante
    INFO_ALERTA =   "\033[1;93m" # Amarelo Brilhante
    CMD_DESTACADO = "\033[1;94m" # Azul Brilhante
    TITULO_SECAO =  "\033[1;96m" # Ciano Brilhante
    RESUMO_DESTAQUE="\033[1;95m" # Magenta Brilhante
    SEM_ESTILO =    "\033[0m"

# Determina um limite prático para threads concorrentes
NUCLEOS_PROCESSADOR = os.cpu_count() or 1
TAMANHO_POOL_THREADS = NUCLEOS_PROCESSADOR * 4

def recuperar_nomes_container_host():
    """Busca nomes de containers de host em execução via os.popen."""
    saida_cmd = os.popen("docker ps --filter \"name=host\" --format \"{{.Names}}\"").read()
    return sorted(saida_cmd.splitlines())

def recuperar_nomes_container_roteador():
    """Busca nomes de containers de roteador em execução via os.popen."""
    saida_cmd = os.popen("docker ps --filter \"name=router\" --format \"{{.Names}}\"").read()
    return sorted(saida_cmd.splitlines())

def obter_id_numerico_roteador(nome_str_container):
    """Extrai a parte numérica de um nome de container de roteador (ex: projeto-roteador1-1 -> 1)."""
    # Assume convenção de nomenclatura como projeto-roteador<NUMERO>-instancia
    parte_nome = nome_str_container.split("-")[1] # ex. roteador1
    # Correção: Usar split para remover o prefixo 'router' e obter apenas o número
    id_numerico_str = parte_nome.split("router")[1] # ex. 1
    return id_numerico_str

def executar_ping_do_container(nome_host_origem, nome_roteador_alvo, ip_roteador_alvo, lista_colecao_resultados, trava_lista_colecao):
    """Thread de trabalho: executa um ping de um host para um IP de roteador e armazena o resultado."""
    inicio_operacao = time.time()
    # Comando para pingar do container do host de origem para o IP do roteador alvo
    cmd_execucao_ping = f"docker exec {nome_host_origem} ping -c 5 -W 0.1 {ip_roteador_alvo} > /dev/null 2>&1"
    print(f"{CoresTerminal.CMD_DESTACADO}Rodando: {cmd_execucao_ping}{CoresTerminal.SEM_ESTILO}")
    
    codigo_retorno = os.system(cmd_execucao_ping)
    duracao_operacao = time.time() - inicio_operacao
    ping_foi_bem_sucedido = (codigo_retorno == 0)
    
    # Adição segura à lista de resultados, protegida por trava
    with trava_lista_colecao:
        lista_colecao_resultados.append((nome_host_origem, nome_roteador_alvo, ping_foi_bem_sucedido, duracao_operacao))

def testar_pings_host_para_roteador():
    """Função principal para testar conectividade de hosts para roteadores."""
    lista_roteadores_ativos = recuperar_nomes_container_roteador()
    if not lista_roteadores_ativos:
        print(f"{CoresTerminal.FALHA_CRITICA}Erro: Nenhum container de roteador encontrado. Por favor, garanta que estão em execução (ex: via \"make up\").{CoresTerminal.SEM_ESTILO}")
        return

    lista_hosts_ativos = recuperar_nomes_container_host()
    if not lista_hosts_ativos:
        print(f"{CoresTerminal.FALHA_CRITICA}Erro: Nenhum container de host encontrado. Por favor, garanta que estão em execução.{CoresTerminal.SEM_ESTILO}")
        return
    
    # Cria uma lista de tarefas de ping: (host_origem, roteador_alvo, ip_roteador_alvo)
    # Assume que IPs de roteador são da forma 172.20.<id_roteador>.3 para a interface voltada aos hosts
    tarefas_ping_a_executar = []
    for container_host in lista_hosts_ativos:
        for container_roteador in lista_roteadores_ativos:
            # Para este script, assumimos que qualquer host pode tentar pingar qualquer IP de gateway de roteador
            valor_id_roteador = obter_id_numerico_roteador(container_roteador)
            ip_interface_roteador = f"172.20.{valor_id_roteador}.3"
            tarefas_ping_a_executar.append((container_host, container_roteador, ip_interface_roteador))
    
    todos_dados_resultados_ping = []
    threads_trabalhadoras_atuais = []
    trava_dados_resultados = threading.Lock()
    
    # Executa tarefas usando um número gerenciado de threads
    for host_origem, roteador_alvo, ip_alvo in tarefas_ping_a_executar:
        # Gerenciamento básico do pool de threads
        while len(threads_trabalhadoras_atuais) >= TAMANHO_POOL_THREADS:
            threads_trabalhadoras_atuais = [t for t in threads_trabalhadoras_atuais if t.is_alive()] # Remove threads concluídas
            if len(threads_trabalhadoras_atuais) >= TAMANHO_POOL_THREADS:
                time.sleep(0.05) # Espera brevemente se o pool ainda estiver cheio

        obj_thread_ping = threading.Thread(target=executar_ping_do_container, 
                                         args=(host_origem, roteador_alvo, ip_alvo, todos_dados_resultados_ping, trava_dados_resultados))
        obj_thread_ping.start()
        threads_trabalhadoras_atuais.append(obj_thread_ping)
    
    # Espera todas as threads finalizarem
    for t_trabalhadora in threads_trabalhadoras_atuais:
        t_trabalhadora.join()
    
    # Compila resultados para relatório
    mapa_resumo_ping = {}
    for origem_h, alvo_r, status_sucesso, tempo_decorrido_s in todos_dados_resultados_ping:
        mapa_resumo_ping.setdefault(origem_h, []).append((alvo_r, status_sucesso, tempo_decorrido_s))
    
    total_pings_bem_sucedidos = 0
    total_pings_tentados = len(todos_dados_resultados_ping)
    
    # Exibe resumo
    print(f"\n{CoresTerminal.RESUMO_DESTAQUE}--- Resumo do Teste de Ping Host-para-Roteador ---{CoresTerminal.SEM_ESTILO}")
    for chave_host_origem in sorted(mapa_resumo_ping.keys()):
        print(f"\n{CoresTerminal.TITULO_SECAO}Pings do Host: {chave_host_origem}{CoresTerminal.SEM_ESTILO}")
        
        for valor_roteador_alvo, esta_ok, duracao_s in mapa_resumo_ping[chave_host_origem]:
            cor_resultado = CoresTerminal.SUCESSO_VIVO if esta_ok else CoresTerminal.FALHA_CRITICA
            texto_resultado = "ALCANÇÁVEL" if esta_ok else "INACALCANÇÁVEL"
            
            print(f"{cor_resultado}{chave_host_origem} -> {valor_roteador_alvo}: {texto_resultado} ({duracao_s:.2f}s){CoresTerminal.SEM_ESTILO}")
            if esta_ok:
                total_pings_bem_sucedidos += 1
            
    print(f"\n{CoresTerminal.RESUMO_DESTAQUE}Geral - Total de Pings: {total_pings_tentados}, Bem-sucedidos: {total_pings_bem_sucedidos}, Falhas: {total_pings_tentados - total_pings_bem_sucedidos}{CoresTerminal.SEM_ESTILO}")

if __name__ == "__main__":
    testar_pings_host_para_roteador()

