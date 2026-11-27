"""
Troca de senha PRESERVANDO os dados.

A senha gera todas as chaves da conta (nome da rede, chave do banco, chaves
de rede). Trocar a senha = migrar a conta para chaves novas:

  1. confere a senha atual;
  2. copia o banco inteiro para um arquivo NOVO cifrado com a chave nova
     (sqlcipher_export: tabelas, índices, triggers e preferências);
  3. confere que a cópia abre e tem as mesmas contagens de registros;
  4. só então atualiza a lista de contas, a sessão e a configuração de rede
     e apaga os arquivos da conta antiga.

Qualquer falha antes do passo 4 deixa a conta antiga INTACTA.

Os outros aparelhos NÃO são alterados daqui (a nova senha nunca trafega pela
rede antiga: quem tivesse a senha antiga a veria). Em cada um deles, use
"Alterar senha" com a mesma senha nova, ou saia da conta e entre com a nova
(os dados chegam por sincronização).
"""
import os
import re
import json
import shutil

from modulos import identidade, bd_seguro

_HEX64 = re.compile(r'^[0-9a-fA-F]{64}$')


class ErroTroca(Exception):
    """Mensagem pronta para o usuário."""


def _contas_json(pasta):
    return os.path.join(pasta, 'contas.json')


def _tabelas(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def _contagens(conn):
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            for t in _tabelas(conn)}


def _apagar_banco(caminho):
    for suf in ('', '-wal', '-shm', '-journal'):
        try:
            os.remove(caminho + suf)
        except OSError:
            pass


def _copiar_banco(antigo, chave_antiga, novo, chave_nova):
    """Cria `novo` (cifrado com chave_nova) com todo o conteúdo de `antigo`."""
    if not _HEX64.match(chave_nova or ''):
        raise ErroTroca('Chave inválida.')
    c = bd_seguro.conectar(antigo, chave_antiga)
    try:
        try:
            c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception:
            pass
        uv = c.execute('PRAGMA user_version').fetchone()[0]
        if bd_seguro.CRIPTO_REPOUSO:
            c.execute(f"ATTACH DATABASE ? AS novo KEY \"x'{chave_nova}'\"",
                      (novo,))
            try:
                c.execute("SELECT sqlcipher_export('novo')")
                c.execute(f'PRAGMA novo.user_version = {int(uv)}')
                c.commit()
            finally:
                c.execute('DETACH DATABASE novo')
        else:                                   # sem SQLCipher: banco comum
            c.close()
            shutil.copy2(antigo, novo)
            return
    finally:
        try:
            c.close()
        except Exception:
            pass


def _conferir(novo, chave_nova, contagem_antiga):
    c = bd_seguro.conectar(novo, chave_nova)
    try:
        ok = c.execute('PRAGMA integrity_check').fetchone()[0]
        if str(ok).lower() != 'ok':
            raise ErroTroca('A cópia do banco não passou na verificação.')
        if _contagens(c) != contagem_antiga:
            raise ErroTroca('A cópia do banco não confere com o original.')
    finally:
        c.close()


def trocar_senha(pasta, usuario, senha_atual, senha_nova):
    """Migra a conta `usuario` para `senha_nova`. Chamar com o banco da conta
    FECHADO e a rede PARADA. Retorna as novas Chaves.
    Levanta ErroTroca (mensagem para o usuário) se algo falhar."""
    if senha_atual == senha_nova:
        raise ErroTroca('A nova senha precisa ser diferente da atual.')
    erro = identidade.validar(usuario, senha_nova)
    if erro:
        raise ErroTroca(erro)

    velhas = identidade.derivar(usuario, senha_atual)
    novas = identidade.derivar(usuario, senha_nova)
    db_velho = os.path.join(pasta, f'{velhas.net_id}.db')
    db_novo = os.path.join(pasta, f'{novas.net_id}.db')
    if not os.path.exists(db_velho):
        raise ErroTroca('Senha atual incorreta.')
    if os.path.exists(db_novo):
        raise ErroTroca('Já existe neste aparelho uma conta com essa senha '
                        'nova. Escolha outra.')

    # contagem do original (também confirma que a chave abre o banco)
    try:
        c = bd_seguro.conectar(db_velho, velhas.chave_bd)
    except PermissionError:
        raise ErroTroca('Senha atual incorreta.')
    try:
        antes = _contagens(c)
    finally:
        c.close()

    # 2-3) copia e confere; falha = remove a cópia e deixa tudo como estava
    try:
        _copiar_banco(db_velho, velhas.chave_bd, db_novo, novas.chave_bd)
        _conferir(db_novo, novas.chave_bd, antes)
    except Exception as e:
        _apagar_banco(db_novo)
        if isinstance(e, ErroTroca):
            raise
        raise ErroTroca(f'Não foi possível migrar os dados: {e}')

    # 4) a cópia está boa: passa a conta para as chaves novas
    rede_velha = os.path.join(pasta, 'redes', velhas.net_id)
    rede_nova = os.path.join(pasta, 'redes', novas.net_id)
    try:                                      # mantém o nome do aparelho
        with open(os.path.join(rede_velha, 'config.json'),
                  encoding='utf-8') as f:
            cfg = json.load(f)
        os.makedirs(rede_nova, exist_ok=True)
        with open(os.path.join(rede_nova, 'config.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({k: cfg[k] for k in ('nome', 'nos_extra') if k in cfg}, f)
    except Exception:
        pass

    try:                                      # lista de contas do aparelho
        try:
            with open(_contas_json(pasta), encoding='utf-8') as f:
                contas = json.load(f)
        except Exception:
            contas = {}
        contas[identidade.normalizar_usuario(usuario)] = novas.net_id
        with open(_contas_json(pasta), 'w', encoding='utf-8') as f:
            json.dump(contas, f)
    except Exception as e:
        _apagar_banco(db_novo)
        raise ErroTroca(f'Não foi possível atualizar a lista de contas: {e}')

    if identidade.carregar_sessao(pasta) is not None:   # "manter conectado"
        identidade.guardar_sessao(pasta, novas)

    # a conta antiga (cifrada com a senha antiga) não deve ficar no disco
    _apagar_banco(db_velho)
    shutil.rmtree(rede_velha, ignore_errors=True)
    return novas
