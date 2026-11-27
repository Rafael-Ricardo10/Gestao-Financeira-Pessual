"""
Diagnóstico de conectividade: internet, firewall e portas do Tox.

Portas usadas pelo app:
    UDP 33700-33799  rede Tox (cifrada ponta a ponta)
    UDP+TCP 33698    descoberta e enlace direto (cifrados com a chave da conta)
"""
import re
import shutil
import socket
import subprocess
import sys

from modulos import recursos

PORTAS_TOX = '33700-33799'
PORTA_LAN = '33698'


def tem_internet(timeout=3.0):
    for host, porta in (('1.1.1.1', 443), ('8.8.8.8', 53), ('9.9.9.9', 443)):
        try:
            socket.create_connection((host, porta), timeout).close()
            return True
        except OSError:
            continue
    return False


def _run(cmd, timeout=5):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, env=recursos.env_limpo())
        return (r.stdout or '') + (r.stderr or '')
    except Exception:
        return ''


def firewall():
    """('ativo'|'inativo'|'desconhecido', nome)."""
    try:
        if sys.platform.startswith('linux'):
            if shutil.which('ufw'):
                s = _run(['ufw', 'status']).lower()
                if 'status: active' in s:
                    return 'ativo', 'ufw'
                if 'status: inactive' in s:
                    return 'inativo', 'ufw'
                if _run(['systemctl', 'is-active', 'ufw']).strip() == 'active':
                    return 'ativo', 'ufw'
            if shutil.which('firewall-cmd') or shutil.which('systemctl'):
                if _run(['systemctl', 'is-active',
                         'firewalld']).strip() == 'active':
                    return 'ativo', 'firewalld'
        elif sys.platform == 'win32':
            s = _run(['netsh', 'advfirewall', 'show', 'currentprofile',
                      'state'])
            if re.search(r'\b(ON|ATIVADO|LIGADO|HABILITADO)\b', s, re.I):
                return 'ativo', 'Firewall do Windows'
            if re.search(r'\b(OFF|DESATIVADO|DESLIGADO)\b', s, re.I):
                return 'inativo', 'Firewall do Windows'
    except Exception:
        pass
    return 'desconhecido', ''


def comando_liberar(nome_fw=''):
    if sys.platform == 'win32':
        return ('netsh advfirewall firewall add rule name="RRFS Financas" '
                f'dir=in action=allow protocol=ANY localport={PORTA_LAN},'
                f'{PORTAS_TOX}   (execute como Administrador)')
    if nome_fw == 'firewalld':
        return (f'sudo firewall-cmd --permanent --add-port={PORTAS_TOX}/udp '
                f'--add-port={PORTA_LAN}/udp --add-port={PORTA_LAN}/tcp && '
                f'sudo firewall-cmd --reload')
    return (f'sudo ufw allow {PORTAS_TOX.replace("-", ":")}/udp && '
            f'sudo ufw allow {PORTA_LAN}')


def avaliar(status_rede, internet, fw, porta_tox, segundos, pares_online,
            pares_conhecidos, tem_interface):
    """Devolve {'nivel': ok|info|aviso, 'titulo', 'texto', 'comando'}."""
    estado, nome_fw = fw

    def r(nivel, titulo, texto, cmd=''):
        return {'nivel': nivel, 'titulo': titulo, 'texto': texto,
                'comando': cmd}

    if not tem_interface:
        return r('aviso', 'Sem conexão de rede',
                 'Nenhuma interface de rede ativa (cabo/Wi-Fi desconectado). '
                 'O app continua offline e sincroniza quando a rede voltar.')
    if not porta_tox:
        return r('aviso', 'Portas do Tox indisponíveis',
                 f'Nenhuma porta UDP livre em {PORTAS_TOX}. Feche outra '
                 'cópia do aplicativo ou libere essas portas.',
                 comando_liberar(nome_fw))
    if status_rede > 0:
        if pares_online:
            extra = ('' if status_rede == 2 else
                     ' (via relé TCP: UDP bloqueado ou NAT restrito; '
                     f'libere UDP {PORTAS_TOX} para melhor desempenho)')
            return r('ok', 'Conectado', f'{pares_online} aparelho(s) online'
                     + extra)
        txt = 'Conectado à rede Tox; aguardando seus outros aparelhos.'
        if segundos > 600 and not pares_conhecidos:
            txt += (' Se você tem outro aparelho ligado e ele não aparece, '
                    'os dois podem ter sorteado a mesma identidade (1 chance '
                    'em 40): use "Trocar identidade deste aparelho".')
        return r('info', 'Aguardando outros aparelhos', txt)
    # Tox offline
    if segundos < 45:
        return r('info', 'Iniciando', 'Conectando à rede…')
    if internet:
        if segundos < 90:
            return r('info', 'Conectando', 'Conectando à rede Tox…')
        extra = (f' O firewall ({nome_fw}) está ativo.'
                 if estado == 'ativo' else '')
        return r('aviso', 'Porta provavelmente bloqueada',
                 'Há internet, mas o app não conseguiu entrar na rede Tox. '
                 f'Abra a porta UDP {PORTAS_TOX} (entrada e saída) no '
                 'firewall do computador e do roteador.' + extra,
                 comando_liberar(nome_fw))
    # sem internet
    if estado == 'ativo':
        return r('aviso', 'Firewall ativo, sem internet',
                 'Sem internet o app acha os aparelhos pela rede local. Para '
                 f'isso o firewall precisa liberar UDP e TCP {PORTA_LAN} e UDP '
                 f'{PORTAS_TOX}. Se já liberou, apenas aguarde.',
                 comando_liberar(nome_fw))
    return r('info', 'Sem internet: aguardando a rede local',
             'Tudo certo: o app está procurando seus aparelhos na rede local '
             'e nas sub-redes. Assim que outro aparelho da conta aparecer, a '
             'sincronização acontece sozinha.')
