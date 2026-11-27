"""
Módulo administrativo
"""

from modulos.database import (
    listar_usuarios_admin, suspender_usuario,
    excluir_usuario, limpar_usuarios_inativos
)
from modulos.agente import listar_modelos_ollama, definir_modelo, obter_modelo_atual
from modulos.logs import obter_logs, marcar_resolvido
from modulos.cache import cache
import json
from pathlib import Path
from datetime import datetime
import shutil
import zipfile
import io

def exportar_todos_dados() -> bytes:
    """
    Exporta dados para backup (dados ainda criptografados)
    Admin não pode ver conteúdo - apenas move arquivos
    """
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        dados_path = Path("dados")

        for arquivo in dados_path.rglob("*.enc"):
            # Inclui apenas arquivos criptografados
            zf.write(arquivo, arquivo.relative_to(dados_path.parent))

        # Inclui índice (sem dados sensíveis)
        indice_path = Path("dados/sistema/indice_usuarios.json")
        if indice_path.exists():
            zf.write(indice_path, "dados/sistema/indice_usuarios.json")

    buffer.seek(0)
    return buffer.read()

def importar_dados(arquivo_bytes: bytes) -> tuple[bool, str]:
    """Importa backup de dados"""
    try:
        buffer = io.BytesIO(arquivo_bytes)
        with zipfile.ZipFile(buffer, 'r') as zf:
            zf.extractall(Path("."))
        return True, "Dados importados com sucesso"
    except Exception as e:
        return False, f"Erro ao importar: {str(e)}"

def obter_estatisticas_sistema() -> dict:
    """Estatísticas gerais do sistema para o admin"""
    from modulos.database import _carregar_indice_usuarios

    indice = _carregar_indice_usuarios()
    total = len(indice)
    ativos = sum(1 for u in indice.values() if not u.get('suspenso'))
    suspensos = sum(1 for u in indice.values() if u.get('suspenso'))
    admins = sum(1 for u in indice.values() if u.get('is_admin'))

    logs = obter_logs()

    return {
        "total_usuarios": total,
        "usuarios_ativos": ativos,
        "usuarios_suspensos": suspensos,
        "administradores": admins,
        "erros_pendentes": len([l for l in logs if not l.get('resolvido')]),
        "modelo_ia_atual": obter_modelo_atual(),
        "gerado_em": datetime.now().isoformat()
    }
