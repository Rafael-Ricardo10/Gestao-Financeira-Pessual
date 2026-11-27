"""
Configuração automática SSL/TLS com certificado auto-assinado
Para produção, substituir por Let's Encrypt
"""

import os
import subprocess
import socket
from pathlib import Path
from modulos.logs import registrar_log

CERT_DIR = Path("dados/ssl")
CERT_FILE = CERT_DIR / "cert.pem"
KEY_FILE = CERT_DIR / "key.pem"

def obter_ip_local() -> str:
    """Obtém IP local da máquina"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def gerar_certificado_ssl():
    """
    Gera certificado SSL auto-assinado com OpenSSL
    Válido por 10 anos, RSA 4096 bits
    """
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    if CERT_FILE.exists() and KEY_FILE.exists():
        print("[SSL] Certificado existente encontrado.")
        return str(CERT_FILE), str(KEY_FILE)

    ip_local = obter_ip_local()
    hostname = socket.gethostname()

    # Configuração OpenSSL
    config_ssl = f"""
[req]
default_bits = 4096
prompt = no
default_md = sha256
distinguished_name = dn
x509_extensions = v3_req

[dn]
C=BR
ST=Brasil
L=Local
O=GestaoFinanceira
OU=Sistema
CN={hostname}

[v3_req]
subjectAltName = @alt_names
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = localhost
DNS.2 = {hostname}
IP.1 = 127.0.0.1
IP.2 = {ip_local}
"""

    config_path = CERT_DIR / "openssl.conf"
    with open(config_path, 'w') as f:
        f.write(config_ssl)

    try:
        subprocess.run([
            'openssl', 'req',
            '-x509',
            '-newkey', 'rsa:4096',
            '-keyout', str(KEY_FILE),
            '-out', str(CERT_FILE),
            '-days', '3650',
            '-nodes',
            '-config', str(config_path)
        ], check=True, capture_output=True)

        # Permissões seguras
        os.chmod(str(KEY_FILE), 0o600)
        os.chmod(str(CERT_FILE), 0o644)

        print(f"[SSL] Certificado gerado com sucesso!")
        print(f"[SSL] Acesse: https://localhost:6300 ou https://{ip_local}:6300")
        return str(CERT_FILE), str(KEY_FILE)

    except subprocess.CalledProcessError as e:
        registrar_log("ssl_config", f"Erro ao gerar certificado SSL: {e}")
        raise RuntimeError(f"Falha ao gerar SSL: {e}")

def configurar_ssl():
    """Configura e retorna contexto SSL"""
    import ssl
    cert, key = gerar_certificado_ssl()

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert, key)

    # Cifras seguras apenas
    context.set_ciphers(
        'ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20'
        ':!aNULL:!eNULL:!EXPORT:!DES:!RC4:!MD5:!PSK:!SRP'
    )

    return context, cert, key
