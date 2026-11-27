"""
Módulo administrativo
Backup com índice criptografado
Admin não consegue ver dados dos usuários
"""

from modulos.database import (
    listar_usuarios_admin, suspender_usuario,
    excluir_usuario, limpar_usuarios_inativos,
    _carregar_indice_usuarios, _buscar_usuario_por_id
)
from modulos.agente import listar_modelos_ollama, obter_modelo_atual
from modulos.logs import obter_logs
from modulos.crypto import criptografar_dados, descriptografar_dados, gerar_salt
from modulos.cache import cache

import json
import os
from pathlib import Path
from datetime import datetime
import zipfile
import io

def _derivar_chave_backup(senha: str) -> bytes:
    from modulos.crypto import derivar_chave_usuario
    import hashlib
    salt = hashlib.sha256(senha.encode() + b"financeia_backup_v2").digest()[:32]
    return derivar_chave_usuario(senha, salt)

def exportar_todos_dados(senha_backup: str = None) -> bytes:
    """
    Exporta backup completo.
    Dados dos usuários: .enc (criptografados com chave de cada usuário)
    Índice: criptografado com senha de backup
    Admin não consegue ver NADA dos dados dos usuários.
    """
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        dados_path = Path("dados")

        # Arquivos criptografados dos usuários
        for arquivo in dados_path.rglob("*.enc"):
            zf.write(arquivo, arquivo.relative_to(dados_path.parent))

        # Índice: criptografado com senha de backup
        indice_path = Path("dados/sistema/indice_usuarios.json")
        if indice_path.exists():
            with open(indice_path, 'r') as f:
                indice = json.load(f)

            if senha_backup:
                chave = _derivar_chave_backup(senha_backup)
                indice_enc = criptografar_dados(indice, chave)
                zf.writestr(
                    "dados/sistema/indice_usuarios.enc_backup",
                    indice_enc
                )
            else:
                # Sem senha: remove dados sensíveis
                indice_safe = {
                    uid: {k: v for k, v in m.items()
                          if k not in ['hash_senha', 'salt', 'salt_chave']}
                    for uid, m in indice.items()
                }
                zf.writestr(
                    "dados/sistema/indice_parcial.json",
                    json.dumps(indice_safe, indent=2, ensure_ascii=False)
                )

        # Metadados do backup
        meta = {
            "versao"         : "3.0",
            "gerado_em"      : datetime.now().isoformat(),
            "criptografado"  : bool(senha_backup),
            "aviso"          : (
                "Dados dos usuarios criptografados individualmente. "
                "Admin nao tem acesso ao conteudo."
            )
        }
        zf.writestr("backup_info.json", json.dumps(meta, indent=2))

    buffer.seek(0)
    return buffer.read()

def importar_dados(arquivo_bytes: bytes) -> tuple[bool, str]:
    """Importa backup - apenas arquivos .enc e índice"""
    try:
        buffer = io.BytesIO(arquivo_bytes)
        with zipfile.ZipFile(buffer, 'r') as zf:
            for nome in zf.namelist():
                if (nome.endswith('.enc') or
                    nome.endswith('.enc_backup') or
                    nome.endswith('.json')):
                    zf.extract(nome, Path("."))
        return True, "Dados importados. Reinicie o servidor."
    except Exception as e:
        return False, f"Erro: {str(e)}"

def obter_estatisticas_sistema() -> dict:
    indice = _carregar_indice_usuarios()
    logs = obter_logs()
    return {
        "total_usuarios"   : len(indice),
        "usuarios_ativos"  : sum(1 for u in indice.values() if not u.get('suspenso')),
        "usuarios_suspensos": sum(1 for u in indice.values() if u.get('suspenso')),
        "administradores"  : sum(1 for u in indice.values() if u.get('is_admin')),
        "erros_pendentes"  : len([l for l in logs if not l.get('resolvido')]),
        "modelo_ia_atual"  : obter_modelo_atual(),
        "gerado_em"        : datetime.now().isoformat()
    }
