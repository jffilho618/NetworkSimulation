import os
import threading
import time

# Estilização para mensagens de saída no terminal (tons alterados)
class EstilosImpressao:
    ERRO_GRAVE =          "\033[1;91m" # Vermelho Brilhante Intenso
    SUCESSO_TOTAL =       "\033[1;92m" # Verde Brilhante Intenso
    AVISO_INFO =          "\033[1;94m" # Azul Brilhante Intenso (usado para informações gerais)
    ALERTA_OPERACAO =     "\033[1;93m" # Amarelo Brilhante Intenso (usado para avisos de operações)
    TITULO_BLOCO =        "\033[1;96m" # Ciano Brilhante Intenso
    DESTAQUE_GERAL =      "\033[1;95m" # Magenta Brilhante Intenso
    SEM_ESTILO_DEFINIDO = "\033[0m"

# Configuração do sistema para concorrência
NUCLEOS_CPU_SISTEMA = os.cpu_count() or 1
MAX_PINGS_PARALELOS = NUCLEOS_CPU_SISTEMA * 4

def descobrir_containers_roteador():
    """Recupera uma lista de nomes de containers de roteador em execução usando os.popen."""
    resultado_comando = os.popen("docker ps --filter \"name=router\" --format \"{{.Names}}\"").read()
    return sorted(resultado_comando.splitlines())

def obter_id_roteador_pelo_nome_container(nome_completo_container):
    """Extrai o ID numérico de uma string de nome de container de roteador.
    Exemplo: meuprojeto-roteador2-1 -> 2
    """
    # Assume um padrão de nomenclatura consistente como projeto-roteador<ID>-instancia
    try:
        segmento_nome = nome_completo_container.split("-")[1] # ex: roteador2
        # Correção: Usar split para remover o prefixo 'router' e obter apenas o número
        id_numerico_roteador = segmento_nome.split("router")[1] # ex: 2
        return id_numerico_roteador
    except IndexError:
        # Fallback se o padrão de nomenclatura for diferente
        return nome_completo_container
        

def realizar_ping_roteador(ctr_roteador_origem, ctr_roteador_alvo, ip_addr_roteador_alvo, lista_saidas_ping, semaforo_lista_saidas):
    """Função da thread de trabalho: executa ping entre roteadores e registra o resultado."""
    tempo_inicio_operacao = time.time()
    # Define o comando docker exec para pingar
    cmd_ping_docker = f"docker exec {ctr_roteador_origem} ping -c 5 -W 0.1 {ip_addr_roteador_alvo} > /dev/null 2>&1"
    print(f"{EstilosImpressao.ALERTA_OPERACAO}Executando: {cmd_ping_docker}{EstilosImpressao.SEM_ESTILO_DEFINIDO}")
    
    codigo_saida_cmd = os.system(cmd_ping_docker)
    tempo_decorrido_operacao = time.time() - tempo_inicio_operacao
    ping_foi_bem_sucedido = (codigo_saida_cmd == 0)
    
    # Adição segura à lista compartilhada de resultados
    with semaforo_lista_saidas:
        lista_saidas_ping.append((ctr_roteador_origem, ctr_roteador_alvo, ping_foi_bem_sucedido, tempo_decorrido_operacao))

def executar_testes_ping_inter_roteadores():
    """Função principal para gerenciar e relatar testes de ping entre todos os containers de roteador ativos."""
    nomes_containers_roteadores_ativos = descobrir_containers_roteador()
    if not nomes_containers_roteadores_ativos:
        print(f"{EstilosImpressao.ERRO_GRAVE}Erro Crítico: Nenhum container de roteador está ativo no momento. Por favor, inicie-os (ex: com \"make up\").{EstilosImpressao.SEM_ESTILO_DEFINIDO}")
        return

    # Prepara lista de operações de ping: (roteador_origem, roteador_alvo, ip_roteador_alvo)
    # Assume que IPs de roteador alvo são como 172.20.<id_roteador>.3
    lista_trabalhos_ping_roteador = []
    for nome_r_origem in nomes_containers_roteadores_ativos:
        for nome_r_alvo in nomes_containers_roteadores_ativos:
            if nome_r_origem == nome_r_alvo: # Pula auto-ping
                continue
            id_r_alvo = obter_id_roteador_pelo_nome_container(nome_r_alvo)
            ip_alvo_assumido_para_ping = f"172.20.{id_r_alvo}.3"
            lista_trabalhos_ping_roteador.append((nome_r_origem, nome_r_alvo, ip_alvo_assumido_para_ping))
    
    print(f"{EstilosImpressao.DESTAQUE_GERAL}Iniciando {len(lista_trabalhos_ping_roteador)} pings inter-roteadores usando até {MAX_PINGS_PARALELOS} threads paralelas...{EstilosImpressao.SEM_ESTILO_DEFINIDO}")
    
    dados_ping_coletados = []
    pool_threads_ativas = []
    trava_coleta_dados = threading.Lock()

    # Despacha tarefas de ping para threads de trabalho
    for roteador_origem, roteador_alvo, val_ip_alvo in lista_trabalhos_ping_roteador:
        # Mecanismo simples para limitar threads concorrentes
        while len(pool_threads_ativas) >= MAX_PINGS_PARALELOS:
            pool_threads_ativas = [item_th for item_th in pool_threads_ativas if item_th.is_alive()] # Limpa threads finalizadas
            if len(pool_threads_ativas) >= MAX_PINGS_PARALELOS:
                time.sleep(0.05) # Pequeno atraso se o pool ainda estiver cheio

        obj_thread = threading.Thread(target=realizar_ping_roteador, 
                                      args=(roteador_origem, roteador_alvo, val_ip_alvo, dados_ping_coletados, trava_coleta_dados))
        obj_thread.start()
        pool_threads_ativas.append(obj_thread)

    # Espera todas as threads completarem sua execução
    for instancia_t in pool_threads_ativas:
        instancia_t.join()

    # Agrega resultados para um resumo estruturado
    resultados_ping_por_origem = {}
    for res_roteador_origem, res_roteador_alvo, res_ok, res_tempo_s in dados_ping_coletados:
        resultados_ping_por_origem.setdefault(res_roteador_origem, []).append((res_roteador_alvo, res_ok, res_tempo_s))

    total_conexoes_bem_sucedidas = 0
    total_tentativas_ping = len(dados_ping_coletados)

    # Exibe o resumo final de todas as operações de ping
    print(f"\n{EstilosImpressao.TITULO_BLOCO}=== Resumo do Teste de Conectividade Inter-Roteadores ==={EstilosImpressao.SEM_ESTILO_DEFINIDO}")
    for chave_roteador_origem in sorted(resultados_ping_por_origem.keys()):
        print(f"\n{EstilosImpressao.AVISO_INFO}Conectividade do Roteador: {chave_roteador_origem}{EstilosImpressao.SEM_ESTILO_DEFINIDO}")
        
        for valor_roteador_alvo_disp, sucesso_disp, tempo_decorrido_disp in resultados_ping_por_origem[chave_roteador_origem]:
            cor_impressao_status = EstilosImpressao.SUCESSO_TOTAL if sucesso_disp else EstilosImpressao.ERRO_GRAVE
            msg_texto_status = "OK" if sucesso_disp else "FALHOU"
            
            print(f"{cor_impressao_status}{chave_roteador_origem} -> {valor_roteador_alvo_disp}: {msg_texto_status} (Tempo: {tempo_decorrido_disp:.2f}s){EstilosImpressao.SEM_ESTILO_DEFINIDO}")
            if sucesso_disp:
                 total_conexoes_bem_sucedidas +=1 # Incrementa se bem-sucedido

    print(f"\n{EstilosImpressao.DESTAQUE_GERAL}Resumo Geral - Tentativas Totais: {total_tentativas_ping}, Pings Bem-sucedidos: {total_conexoes_bem_sucedidas}, Pings Falhados: {total_tentativas_ping - total_conexoes_bem_sucedidas}{EstilosImpressao.SEM_ESTILO_DEFINIDO}")

if __name__ == "__main__":
    executar_testes_ping_inter_roteadores()

