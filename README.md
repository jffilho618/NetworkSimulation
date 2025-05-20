# Simulador de Rede com Roteamento por Estado de Enlace

Este projeto simula uma rede de computadores utilizando Docker e Python, implementando o algoritmo de roteamento por estado de enlace (Link State) nos roteadores.

## Pré-requisitos

*   Docker: [Instruções de instalação](https://docs.docker.com/engine/install/)
*   Docker Compose: [Instruções de instalação](https://docs.docker.com/compose/install/)
*   Python 3.x (para executar os scripts de teste no host)
*   Bibliotecas Python necessárias:
    * Para interação com Docker: `docker`
    * Para o simulador de rede: `netifaces`, `ipaddress`

## Instalação das Dependências

Você pode instalar todas as dependências necessárias usando o arquivo `requirements.txt` fornecido:

```bash
pip install -r requirements.txt
```

Ou instalar manualmente cada biblioteca:

```bash
# Para interação com Docker (necessário para os scripts de teste)
pip install docker

# Para o simulador de rede
pip install netifaces==0.11.0 ipaddress==1.0.23
```

## Execução

1.  **Clone o repositório (ou certifique-se de estar no diretório raiz do projeto):**
    ```bash
    # Exemplo:
    # git clone <url_do_repositorio>
    cd NetworkSimulator
    ```

2.  **Construa e inicie os containers da rede:**
    Execute o seguinte comando no diretório raiz do projeto (onde o `docker-compose.yml` está localizado):
    ```bash
    docker-compose up --build -d
    ```
    Este comando irá construir as imagens Docker para os hosts e roteadores (se ainda não existirem ou se `--build` for usado) e iniciar todos os serviços (containers) em segundo plano (`-d`).

3.  **Aguarde a Convergência da Rede:**
    Após iniciar os containers, aguarde cerca de 1 a 2 minutos para que os roteadores troquem informações de estado de enlace (LSAs) e calculem suas tabelas de roteamento com base nos pesos aleatórios dos enlaces.

4.  **(Opcional) Verifique os Logs:**
    Você pode verificar os logs de um roteador específico para observar o processo de inicialização, envio/recebimento de LSAs e cálculo de rotas:
    ```bash
    docker logs networksimulator-router1-1 -f
    ```
    (Substitua `networksimulator-router1-1` pelo nome do container desejado). Logs específicos da aplicação (como `lsa.log`, `rotas.log`, `pesos_debug.log`, `subnets_debug.log`) estão dentro de cada container de roteador no diretório `/app/logs/`.

5.  **(Opcional) Execute os Scripts de Teste:**
    No seu ambiente host (fora dos containers), você pode executar os scripts Python fornecidos para testar a conectividade:
    ```bash
    # Exemplo (certifique-se de ter as dependências Python instaladas no host):
    python router_show_tables.py
    python router_connect_router.py
    python user_connect_router.py
    python user_connect_user.py
    ```

6.  **Pare e Remova os Containers:**
    Quando terminar, você pode parar e remover os containers e a rede criada:
    ```bash
    docker-compose down
    ```
    Para uma limpeza mais completa (incluindo imagens e redes não utilizadas), você pode usar comandos adicionais como:
    ```bash
    # docker rm -f $(docker ps -a -q)
    # docker network prune -f
    # docker rmi -f $(docker images -q networksimulator-*)
    # docker image prune -a -f
    ```

## Justificativa do Protocolo de Transporte (UDP)

Para a comunicação entre os roteadores (envio e recebimento de Pacotes de Anúncio de Estado de Enlace - LSAs), foi escolhido o protocolo **UDP (User Datagram Protocol)**. A justificativa para essa escolha é a seguinte:

*   **Natureza da Comunicação:** O envio de LSAs é tipicamente um processo de *flooding* (inundação). Os roteadores enviam periodicamente seus LSAs para os vizinhos, e estes os retransmitem. Não há necessidade de uma conexão persistente e orientada à conexão como a oferecida pelo TCP.
*   **Eficiência:** UDP possui um cabeçalho menor e menor sobrecarga (overhead) comparado ao TCP, pois não realiza estabelecimento de conexão (three-way handshake), controle de fluxo ou retransmissão garantida. Para mensagens de controle frequentes como LSAs, essa eficiência é vantajosa.
*   **Tolerância a Perdas:** O algoritmo de estado de enlace é inerentemente robusto a perdas ocasionais de LSAs. Como os LSAs são enviados periodicamente e possuem números de sequência, um LSA perdido será eventualmente substituído por uma versão mais recente. A lógica de atualização do LSDB garante que apenas os LSAs mais novos sejam considerados. A complexidade adicional do TCP para garantir a entrega não é estritamente necessária.
*   **Simplicidade:** A implementação de comunicação via UDP é geralmente mais simples do que TCP, especialmente em um ambiente de simulação onde o foco está na lógica do algoritmo de roteamento em si.

## Construção da Topologia da Rede

A topologia da rede simulada é definida e configurada no arquivo `docker-compose.yml`. A abordagem utilizada é a seguinte:

1.  **Serviços:** Cada componente da rede (roteador ou host) é definido como um `service` distinto no `docker-compose.yml` (ex: `router1`, `host1a`).
2.  **Imagens Docker:** Cada tipo de serviço utiliza uma imagem Docker específica, construída a partir dos `Dockerfile` nos diretórios `router/` e `host/`.
3.  **Redes (Sub-redes):** As sub-redes IP são definidas na seção `networks` (ex: `subnet_1`, `subnet_2`) utilizando o driver `bridge` do Docker. A configuração `ipam` define o range de IPs para cada sub-rede (ex: `172.20.1.0/24`).
4.  **Conectividade e IPs:** A conexão de um container a uma ou mais sub-redes é feita na seção `networks` de cada serviço. Um endereço IP estático (`ipv4_address`) é atribuído a cada interface, garantindo IPs previsíveis.
5.  **Definição de Vizinhança (Roteadores):** As conexões diretas entre roteadores são definidas pela variável de ambiente `vizinhos` em cada roteador (ex: `vizinhos=[routerX, IP_routerX, Custo_Inicial]`). O script `router.py` usa essa informação para identificar vizinhos.
6.  **Pesos dos Enlaces:** Embora um custo inicial seja definido em `vizinhos` no `docker-compose.yml`, o script `router.py` (na versão atual) ignora esse custo inicial. Em vez disso, ele calcula um **peso aleatório simétrico** (entre 1 e 10) para cada enlace ativo entre roteadores, usando a função `get_symmetric_random_weight` que se baseia nos IPs dos roteadores conectados. Esse peso aleatório é então incluído nos LSAs e usado pelo algoritmo de Dijkstra.
7.  **Configuração de Roteamento Inicial:** Os containers de roteadores removem rotas padrão (`ip route del default`) e populam a tabela dinamicamente. Os hosts adicionam uma rota padrão via seu roteador local (`ip route add default via ...`).
8.  **Privilégios:** `cap_add: - NET_ADMIN` concede aos containers a capacidade de manipular a tabela de roteamento.

Essa configuração permite criar uma topologia de rede virtual customizável, onde cada componente opera isoladamente, mas conectado através das redes Docker definidas.

