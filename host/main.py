import os
import subprocess
import sys
import time

if "--test" in sys.argv:
    target = sys.argv[2]  # Ex: "ping 172.20.3.10"
    result = subprocess.run(target.split(), capture_output=True, text=True)
    print(f"TESTE {target}:\n{result.stdout}")
else:
    print("Hello, World!")

while True:  # Mantém o container ativo
    time.sleep(1)