import sys
import os

# Definições para estilizar a saída do console (tons alterados)
class CoresConsole:
    MSG_ERRO =      "\033[1;91m" # Vermelho Brilhante Intenso
    MSG_SUCESSO =   "\033[1;92m" # Verde Brilhante Intenso
    ECO_COMANDO =   "\033[1;93m" # Amarelo Brilhante Intenso
    MSG_INFO =      "\033[1;94m" # Azul Brilhante Intenso
    CABECALHO_SECAO="\033[1;96m" # Ciano Brilhante Intenso
    TEXTO_NEGRITO = "\033[1m"
    REDEFINIR_TUDO ="\033[0m"

def obter_containers_roteador_em_execucao():
    """Busca uma lista de todos os nomes de containers de roteador atualmente em execução."""
    # Usa os.popen para executar o comando docker ps
    saida_docker_ps = os.popen("docker ps --filter \"name=router\" --format \"{{.Names}}\"").read()
    return sorted(saida_docker_ps.splitlines())

def obter_id_numerico_pelo_nome_roteador(nome_container_roteador):
    """Extrai o identificador numérico de um nome de container de roteador.
    Exemplo: projeto-roteador3-1 -> 3
    """
    # Assume uma convenção de nomenclatura como projeto-roteador<ID>-instancia
    try:
        parte_nome = nome_container_roteador.split("-")[1] # ex: roteador3
        # Correção: Usar split para remover o prefixo 'router' e obter apenas o número
        id_numerico = parte_nome.split("router")[1] # ex: 3
        return id_numerico
    except IndexError:
        # Fallback se o nome não corresponder ao padrão esperado
        return nome_container_roteador 

def recuperar_tabela_roteamento_para_container(nome_str_container):
    """Recupera a tabela de roteamento IP de um container Docker especificado."""
    # Constrói e executa o comando para obter a tabela de roteamento
    comando_ip_route = f"docker exec {nome_str_container} ip route"
    print(f"{CoresConsole.ECO_COMANDO}Executando: {comando_ip_route}{CoresConsole.REDEFINIR_TUDO}")
    saida_tabela_roteamento = os.popen(comando_ip_route).read()
    return saida_tabela_roteamento.strip()

def exibir_tabelas_roteamento_roteadores():
    """Função principal para exibir as tabelas de roteamento de todos os roteadores ativos."""
    # Primeiro, obtém a lista de containers de roteadores ativos
    nomes_roteadores_ativos = obter_containers_roteador_em_execucao()
    if not nomes_roteadores_ativos:
        print(f"{CoresConsole.MSG_ERRO}Erro: Nenhum container de roteador está ativo no momento. Por favor, inicie-os (ex: usando \"make up\").{CoresConsole.REDEFINIR_TUDO}")
        sys.exit(1)
    
    print(f"{CoresConsole.MSG_INFO}Encontrado(s) {len(nomes_roteadores_ativos)} roteador(es) ativo(s). Exibindo suas tabelas de roteamento...{CoresConsole.REDEFINIR_TUDO}\n")
    
    # Ordena roteadores pelo ID numérico para saída consistente
    # Isso torna a saída mais fácil de seguir se os números dos roteadores forem sequenciais
    roteadores_ordenados = sorted(nomes_roteadores_ativos, key=lambda nome: (obter_id_numerico_pelo_nome_roteador(nome).isdigit(), int(obter_id_numerico_pelo_nome_roteador(nome)) if obter_id_numerico_pelo_nome_roteador(nome).isdigit() else obter_id_numerico_pelo_nome_roteador(nome)))

    for item_nome_roteador in roteadores_ordenados:
        valor_id_roteador = obter_id_numerico_pelo_nome_roteador(item_nome_roteador)
        print(f"{CoresConsole.TEXTO_NEGRITO}{CoresConsole.CABECALHO_SECAO}=== Tabela de Roteamento do Roteador {valor_id_roteador} (Container: {item_nome_roteador}) ==={CoresConsole.REDEFINIR_TUDO}")
        
        tabela_roteamento_atual = recuperar_tabela_roteamento_para_container(item_nome_roteador)
        
        if tabela_roteamento_atual:
            lista_linhas_tabela = tabela_roteamento_atual.split("\n")
            # Impressão simples de cada linha; poderia ser analisada para formatação mais detalhada
            for item_linha in lista_linhas_tabela:
                print(item_linha)
        else:
            print(f"{CoresConsole.MSG_ERRO}Nenhuma rota encontrada ou erro ao recuperar tabela para {item_nome_roteador}.{CoresConsole.REDEFINIR_TUDO}")
        
        print(f"{CoresConsole.TEXTO_NEGRITO}{CoresConsole.CABECALHO_SECAO}===================================================={CoresConsole.REDEFINIR_TUDO}\n")

if __name__ == "__main__":
    exibir_tabelas_roteamento_roteadores()

