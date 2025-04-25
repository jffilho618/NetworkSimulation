import os
import subprocess
import sys
import time

def run_ping(target: str) -> str:
    """Executa um comando ping e retorna o resultado formatado."""
    try:
        # Limitar a 3 tentativas para não atrasar a inicialização
        result = subprocess.run(
            ["ping", "-c", "3", target],
            capture_output=True,
            text=True,
            timeout=10
        )
        status = "SUCESSO" if result.returncode == 0 else "FALHA"
        return f"Ping para {target}: {status}\n{result.stdout}\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return f"Ping para {target}: TIMEOUT"
    except Exception as e:
        return f"Ping para {target}: ERRO - {str(e)}"

if "--test" in sys.argv:
    print("Iniciando testes de conectividade...", flush=True)
    # Os argumentos após --test são os comandos de ping (ex.: "ping 172.20.1.3")
    tests = [arg for arg in sys.argv[2:] if arg.startswith("ping ")]
    for test in tests:
        target = test.split()[1]  # Extrai o IP (ex.: "ping 172.20.1.3" -> "172.20.1.3")
        result = run_ping(target)
        print(result, flush=True)
else:
    print("Hello, World!", flush=True)

while True:  # Mantém o container ativo
    time.sleep(1)