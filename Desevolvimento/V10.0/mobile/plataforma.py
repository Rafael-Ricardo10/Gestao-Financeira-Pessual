# -*- coding: utf-8 -*-
"""
plataforma.py - tudo que muda entre Android e desktop.

ARQUIVOS NO ANDROID (sem pedir permissão de armazenamento):
  O app NÃO usa READ/WRITE_EXTERNAL_STORAGE. No Android 10+ isso é inútil
  (armazenamento por escopo) e o Android 11+ ignora. Em vez disso usa o
  seletor de arquivos do sistema (Storage Access Framework): o usuário
  escolhe o arquivo e só aquele arquivo é liberado ao app. Para exportar,
  grava em Downloads pelo MediaStore ou abre a folha de compartilhamento.
  Biblioteca: androidstorage4kivy.
"""
import os
import sys
import time
import shutil
import importlib


def eh_android():
    return 'ANDROID_ARGUMENT' in os.environ or 'ANDROID_STORAGE' in os.environ


# ── escolher arquivo ────────────────────────────────────────────────

_REFS = {}          # mantém o Chooser vivo enquanto a tela do sistema abre


def escolher_arquivo(ao_escolher, ao_erro, mime='*/*'):
    """Abre o seletor de arquivos. Chama ao_escolher(caminho_local) na thread
    da interface. No Android, o arquivo é copiado para a pasta privada do app
    (o usuário não precisa conceder permissão nenhuma)."""
    from kivy.clock import Clock

    if eh_android():
        try:
            from androidstorage4kivy import Chooser, SharedStorage

            def retorno(uris):
                # pode vir da thread de UI do Android: volta para a do Kivy
                def tratar(_dt):
                    try:
                        if not uris:
                            return                      # usuário cancelou
                        caminho = SharedStorage().copy_from_shared(uris[0])
                        if not caminho:
                            raise OSError('não foi possível ler o arquivo')
                        ao_escolher(caminho)
                    except Exception as e:
                        ao_erro(f'Falha ao abrir o arquivo: {e}')
                Clock.schedule_once(tratar, 0)

            _REFS['chooser'] = Chooser(retorno)
            _REFS['chooser'].choose_content(mime)
        except Exception as e:
            ao_erro(f'Seletor de arquivos indisponível: {e}')
        return

    # desktop (testes): janela simples do Kivy
    from kivy.uix.popup import Popup
    from kivy.uix.filechooser import FileChooserListView
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button

    caixa = BoxLayout(orientation='vertical')
    fc = FileChooserListView(path=os.path.expanduser('~'))
    linha = BoxLayout(size_hint_y=None, height=48)
    pop = Popup(title='Escolher arquivo', content=caixa, size_hint=(0.95, 0.9))
    b_ok, b_x = Button(text='Abrir'), Button(text='Cancelar')
    b_x.bind(on_release=lambda *_: pop.dismiss())

    def abrir(*_):
        if fc.selection:
            pop.dismiss()
            ao_escolher(fc.selection[0])
    b_ok.bind(on_release=abrir)
    linha.add_widget(b_x)
    linha.add_widget(b_ok)
    caixa.add_widget(fc)
    caixa.add_widget(linha)
    pop.open()


# ── exportar arquivo ────────────────────────────────────────────────

def salvar_em_downloads(caminho_privado):
    """Copia o arquivo para a pasta Downloads do aparelho. Retorna texto
    descrevendo onde ficou. Levanta exceção se falhar."""
    if eh_android():
        from androidstorage4kivy import SharedStorage
        from jnius import autoclass
        env = autoclass('android.os.Environment')
        try:
            destino = SharedStorage().copy_to_shared(
                caminho_privado, collection=env.DIRECTORY_DOWNLOADS)
        except TypeError:
            destino = SharedStorage().copy_to_shared(caminho_privado)
        if not destino:
            raise OSError('o sistema recusou a gravação em Downloads')
        return 'Downloads/' + os.path.basename(caminho_privado)
    pasta = os.path.join(os.path.expanduser('~'), 'Downloads')
    os.makedirs(pasta, exist_ok=True)
    shutil.copy2(caminho_privado, pasta)
    return os.path.join(pasta, os.path.basename(caminho_privado))


def compartilhar_arquivo(caminho_privado):
    """Abre a folha de compartilhamento (enviar para Drive, e-mail...)."""
    if not eh_android():
        raise OSError('compartilhar só existe no Android')
    from androidstorage4kivy import ShareSheet
    ShareSheet().share_file(caminho_privado)


# ── rede local no Android ───────────────────────────────────────────

_MULTICAST = {}


def adquirir_multicast():
    """O Android descarta pacotes broadcast/multicast para economizar bateria;
    sem este 'lock' a descoberta de aparelhos na rede local não funciona."""
    if not eh_android() or 'lock' in _MULTICAST:
        return
    try:
        from jnius import autoclass
        atividade = autoclass('org.kivy.android.PythonActivity').mActivity
        contexto = autoclass('android.content.Context')
        wifi = atividade.getSystemService(contexto.WIFI_SERVICE)
        lock = wifi.createMulticastLock('rrfs-financas')
        lock.setReferenceCounted(False)
        lock.acquire()
        _MULTICAST['lock'] = lock
    except Exception:
        pass


def liberar_multicast():
    lock = _MULTICAST.pop('lock', None)
    try:
        if lock and lock.isHeld():
            lock.release()
    except Exception:
        pass


# ── diagnóstico (essencial num build que não dá para testar antes) ───

def diagnostico():
    """Lista [(nome, ok, detalhe)] do que o app precisa para funcionar."""
    itens = []

    def passo(nome, fn):
        try:
            itens.append((nome, True, str(fn() or '')))
        except Exception as e:
            itens.append((nome, False, f'{type(e).__name__}: {e}'))

    def sqlc():
        from modulos import bd_seguro
        if not bd_seguro.CRIPTO_REPOUSO:
            raise RuntimeError('SQLCipher ausente: dados SEM cifra própria '
                               '(só a proteção do Android)')
        return 'banco cifrado (AES-256)'

    def tox():
        from modulos.tox_financeiro import carregar_libtoxcore
        carregar_libtoxcore()
        return 'carregada'

    def cripto():
        from modulos import identidade
        t = time.time()
        identidade.derivar('teste', 'senha-teste-1')
        return f'scrypt+HKDF ({time.time() - t:.1f}s)'

    def mods():
        for m in ('modulos.sync_core', 'modulos.backup', 'modulos.csv_parser',
                  'modulos.troca_senha', 'modulos.database', 'modulos.loans',
                  'modulos.rede'):
            importlib.import_module(m)
        return 'todos importam'

    def pasta():
        t = os.path.join('dados', '.teste')
        with open(t, 'w') as f:
            f.write('x')
        os.remove(t)
        return os.path.abspath('dados')

    passo('SQLCipher', sqlc)
    passo('libtoxcore (rede)', tox)
    passo('criptografia', cripto)
    passo('módulos do app', mods)
    passo('pasta de dados', pasta)
    itens.append(('plataforma', True,
                  'Android' if eh_android() else 'desktop (teste)'))
    return itens
