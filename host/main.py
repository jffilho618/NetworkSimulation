import os
import subprocess
import sys
import time

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

def run_ping(target: str, origem: str) -> tuple[str, bool]:
    """Executa um comando ping e retorna o resultado formatado e o status de sucesso."""
    try:
        result = subprocess.run(
            ["ping", "-c", "3", target],
            capture_output=True,
            text=True,
            timeout=10
        )
        status = "SUCESSO" if result.returncode == 0 else "FALHA"
        return f"Ping para {target}: {status}\n{result.stdout}\n{result.stderr}", result.returncode == 0
    except subprocess.TimeoutExpired:
        return f"Ping para {target}: TIMEOUT", False
    except Exception as e:
        return f"Ping para {target}: ERRO - {str(e)}", False

def configure_gateway(router_ip: str, origem: str) -> tuple[str, bool]:
    """Configura o gateway padrão e retorna o resultado formatado e o status de sucesso."""
    try:
        # Primeiro, remove qualquer rota padrão existente
        subprocess.run(
            ["ip", "route", "del", "default"],
            capture_output=True,
            text=True
        )
        # Agora adiciona a nova rota padrão
        result = subprocess.run(
            ["ip", "route", "add", "default", "via", router_ip],
            capture_output=True,
            text=True
        )
        status = "SUCESSO" if result.returncode == 0 else "FALHA"
        return f"Configuração de gateway {router_ip}: {status}\n{result.stdout}\n{result.stderr}", result.returncode == 0
    except Exception as e:
        return f"Configuração de gateway {router_ip}: ERRO - {str(e)}", False

if __name__ == "__main__":
    criar_diretorios_logs()
    host_id = os.environ.get("my_name", "host")
    
    if "--test" in sys.argv:
        log("testes_iniciais", "Iniciando configuração e testes de conectividade...", host_id)
        
        # Determinar o IP do roteador com base na subrede
        my_ip = os.environ.get("my_ip", "")
        router_ip = (
            "172.20.1.3" if "172.20.1" in my_ip else
            "172.20.2.3" if "172.20.2" in my_ip else
            "172.20.3.3" if "172.20.3" in my_ip else
            "172.20.4.3" if "172.20.4" in my_ip else
            "172.20.5.3"
        )
        
        # Configurar gateway
        gateway_result, gateway_success = configure_gateway(router_ip, host_id)
        log("conectividade", gateway_result, host_id)
        
        # Executar testes de ping
        tests = [arg for arg in sys.argv[2:] if arg.startswith("ping ")]
        successes = 0
        failures = 0
        
        for test in tests:
            target = test.split()[1]
            result, success = run_ping(target, host_id)
            log("testes_iniciais", result, host_id)
            if success:
                successes += 1
            else:
                failures += 1
        
        # Resumo dos testes
        log("testes_iniciais", f"Resumo de testes de conectividade: {successes} SUCESSOS, {failures} FALHAS", host_id)
    else:
        log("conectividade", "Hello, World!", host_id)

    while True:  # Mantém o container ativo
        time.sleep(1)