import os
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

if __name__ == "__main__":
    criar_diretorios_logs()
    host_id = os.environ.get("my_name", "host")
    log("conectividade", "Hello, World!", host_id)

    while True:  # Mantém o container ativo
        time.sleep(1)