# -*- coding: utf-8 -*-
"""
RRFS Finanças - versão mobile (Android) em Kivy.

Reaproveita TODA a pasta modulos/ do desktop (identidade, banco cifrado,
sincronização, rede Tox, backup, leitor de CSV, troca de senha). Só a
interface é nova. Funciona offline e sincroniza com os outros aparelhos
enquanto o app está aberto.
"""
import os
import sys
import json
import threading
from datetime import date, datetime

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

try:                                    # gerado por build_android.sh
    import config_build
    SEM_SQLCIPHER = bool(getattr(config_build, 'SEM_SQLCIPHER', False))
except ImportError:
    SEM_SQLCIPHER = False
if SEM_SQLCIPHER:
    os.environ['RRFS_PERMITIR_SEM_CRIPTO'] = '1'

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.factory import Factory
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition

import plataforma

VERDE, VERMELHO, AZUL, CINZA = '#2ecc71', '#e74c3c', '#3498db', '#95a5a6'


def brl(v):
    s = f'{abs(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-' if v < 0 else '') + 'R$ ' + s


def data_br(iso):
    return f'{iso[8:10]}/{iso[5:7]}/{iso[:4]}' if iso and len(iso) >= 10 \
        else (iso or '')


MESES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho',
         'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

KV = '''
#:import dp kivy.metrics.dp

<Botao@Button>:
    size_hint_y: None
    height: dp(48)
    background_normal: ''
    background_color: 0.20, 0.55, 0.85, 1
    color: 1, 1, 1, 1
    bold: True

<BotaoSec@Button>:
    size_hint_y: None
    height: dp(44)
    background_normal: ''
    background_color: 0.25, 0.30, 0.35, 1
    color: 1, 1, 1, 1

<Campo@TextInput>:
    size_hint_y: None
    height: dp(46)
    multiline: False
    padding: dp(12), dp(12)
    background_color: 0.17, 0.20, 0.23, 1
    foreground_color: 1, 1, 1, 1
    hint_text_color: 0.6, 0.65, 0.7, 1
    cursor_color: 1, 1, 1, 1

<Texto@Label>:
    size_hint_y: None
    text_size: self.width, None
    height: self.texture_size[1] + dp(6)
    halign: 'left'
    markup: True

<LoginTela>:
    name: 'login'
    ScrollView:
        BoxLayout:
            orientation: 'vertical'
            size_hint_y: None
            height: self.minimum_height
            padding: dp(24)
            spacing: dp(10)
            Label:
                text: 'RRFS Finanças'
                font_size: dp(28)
                bold: True
                size_hint_y: None
                height: dp(70)
            Texto:
                text: 'Entre com seu usuário e senha. Funciona offline e sincroniza com seus outros aparelhos.'
                halign: 'center'
                color: 0.65, 0.7, 0.75, 1
            Campo:
                id: usuario
                hint_text: 'Usuário'
            Campo:
                id: senha
                hint_text: 'Senha'
                password: True
            Campo:
                id: confirma
                hint_text: 'Confirme a senha'
                password: True
                opacity: 1 if root.pedir_confirma else 0
                disabled: not root.pedir_confirma
                height: dp(46) if root.pedir_confirma else 0
            Texto:
                text: root.info
                color: 0.95, 0.61, 0.07, 1
            BoxLayout:
                size_hint_y: None
                height: dp(40)
                CheckBox:
                    id: manter
                    active: True
                    size_hint_x: None
                    width: dp(40)
                Texto:
                    text: 'Manter conectado neste aparelho'
                    valign: 'middle'
                    height: dp(40)
            Botao:
                id: entrar
                text: 'Continuar' if root.pedir_confirma else 'Entrar'
                disabled: root.ocupado
                on_release: app.tentar_login(usuario.text, senha.text, confirma.text, manter.active)
            BotaoSec:
                text: 'Tenho um backup (.rrfs)'
                on_release: app.escolher_backup_login()
            Texto:
                text: root.cripto
                font_size: dp(12)
                color: 0.6, 0.65, 0.7, 1

<HomeTela>:
    name: 'home'
    BoxLayout:
        orientation: 'vertical'
        ScreenManager:
            id: abas
            transition: root.sem_transicao
            Screen:
                name: 'resumo'
                BoxLayout:
                    orientation: 'vertical'
                    padding: dp(14)
                    spacing: dp(8)
                    BoxLayout:
                        size_hint_y: None
                        height: dp(44)
                        BotaoSec:
                            text: '<'
                            size_hint_x: None
                            width: dp(52)
                            on_release: app.mudar_mes(-1)
                        Label:
                            id: l_mes
                            font_size: dp(18)
                            bold: True
                        BotaoSec:
                            text: '>'
                            size_hint_x: None
                            width: dp(52)
                            on_release: app.mudar_mes(1)
                    Texto:
                        id: l_cards
                        font_size: dp(20)
                        height: dp(110)
                    Label:
                        text: 'Maiores gastos do mês'
                        size_hint_y: None
                        height: dp(28)
                        bold: True
                        halign: 'left'
                        text_size: self.size
                    ScrollView:
                        Texto:
                            id: l_cats
                            font_size: dp(15)
                    Texto:
                        id: l_sync_resumo
                        font_size: dp(12)
                        color: 0.6, 0.65, 0.7, 1
            Screen:
                name: 'lancamentos'
                BoxLayout:
                    orientation: 'vertical'
                    padding: dp(10)
                    spacing: dp(6)
                    Botao:
                        text: '+ Novo lançamento'
                        on_release: app.abrir_novo_lancamento()
                    ScrollView:
                        GridLayout:
                            id: lista
                            cols: 1
                            size_hint_y: None
                            height: self.minimum_height
                            spacing: dp(3)
            Screen:
                name: 'dados'
                ScrollView:
                    BoxLayout:
                        orientation: 'vertical'
                        size_hint_y: None
                        height: self.minimum_height
                        padding: dp(16)
                        spacing: dp(10)
                        Texto:
                            text: '[b]Importar extrato (CSV)[/b]\\nEscolha o arquivo CSV do seu banco. O app descobre as colunas sozinho. Só o arquivo escolhido é lido: não é preciso liberar acesso às suas pastas.'
                        Botao:
                            text: 'Importar extrato CSV'
                            on_release: app.importar_extrato()
                        Texto:
                            text: 'Extratos em PDF: importe no computador; eles chegam aqui pela sincronização.'
                            font_size: dp(12)
                            color: 0.6, 0.65, 0.7, 1
                        Texto:
                            text: '[b]Backup[/b]\\nO arquivo é cifrado com a frase que você escolher. Pode guardar na nuvem sem risco.'
                        Botao:
                            text: 'Exportar backup'
                            on_release: app.exportar_backup()
                        BotaoSec:
                            text: 'Importar backup'
                            on_release: app.importar_backup()
            Screen:
                name: 'conta'
                ScrollView:
                    BoxLayout:
                        orientation: 'vertical'
                        size_hint_y: None
                        height: self.minimum_height
                        padding: dp(16)
                        spacing: dp(10)
                        Texto:
                            id: l_conta
                        Texto:
                            id: l_rede
                            font_size: dp(14)
                        BotaoSec:
                            text: 'Sincronizar agora'
                            on_release: app.sincronizar_agora()
                        BotaoSec:
                            text: 'Alterar senha'
                            on_release: app.abrir_alterar_senha()
                        BotaoSec:
                            text: 'Transparência'
                            on_release: app.mostrar_transparencia()
                        BotaoSec:
                            text: 'Diagnóstico'
                            on_release: app.mostrar_diagnostico()
                        Botao:
                            text: 'Sair desta conta'
                            background_color: 0.75, 0.25, 0.22, 1
                            on_release: app.confirmar_sair()
        BoxLayout:
            id: barra
            size_hint_y: None
            height: dp(54)
            canvas.before:
                Color:
                    rgba: 0.09, 0.11, 0.13, 1
                Rectangle:
                    pos: self.pos
                    size: self.size
            BotaoAba:
                text: 'Resumo'
                state: 'down'
                aba: 'resumo'
                on_release: app.ir_aba('resumo')
            BotaoAba:
                text: 'Lançamentos'
                aba: 'lancamentos'
                on_release: app.ir_aba('lancamentos')
            BotaoAba:
                text: 'Dados'
                aba: 'dados'
                on_release: app.ir_aba('dados')
            BotaoAba:
                text: 'Conta'
                aba: 'conta'
                on_release: app.ir_aba('conta')

<BotaoAba@ToggleButton>:
    group: 'abas'
    allow_no_selection: False
    background_normal: ''
    background_down: ''
    background_color: (0.20, 0.55, 0.85, 1) if self.state == 'down' else (0.13, 0.16, 0.19, 1)
    color: 1, 1, 1, 1
'''


class LoginTela(Screen):
    info = StringProperty('')
    cripto = StringProperty('')
    pedir_confirma = BooleanProperty(False)
    ocupado = BooleanProperty(False)


class HomeTela(Screen):
    sem_transicao = NoTransition()


class RRFSApp(App):
    title = 'RRFS Finanças'

    # ══ ciclo de vida ═══════════════════════════════════════════════

    def build(self):
        Window.clearcolor = (0.10, 0.12, 0.14, 1)
        Window.softinput_mode = 'below_target'
        Window.bind(on_keyboard=self._tecla)
        self.pasta = self.user_data_dir
        os.makedirs(os.path.join(self.pasta, 'dados'), exist_ok=True)
        os.chdir(self.pasta)               # o resto dos módulos usa 'dados/'
        Builder.load_string(KV)
        self.sm = ScreenManager(transition=NoTransition())
        self.login = LoginTela()
        self.home = HomeTela()
        self.sm.add_widget(self.login)
        self.sm.add_widget(self.home)

        self.chaves = self.db = self.rede = None
        self.user_id = None
        self._backup_login = None
        hoje = date.today()
        self.mes, self.ano = hoje.month, hoje.year
        self._csv_bytes = None
        self._modulos_ok = self._carregar_modulos()
        if self._modulos_ok:
            Clock.schedule_once(lambda dt: self._iniciar_sessao(), 0.1)
        return self.sm

    def _carregar_modulos(self):
        try:
            global identidade, bd_seguro, backup, sync_core, troca_senha
            global processar_csv_extrato, parse_data, parse_valor
            from modulos import identidade, bd_seguro, backup, sync_core
            from modulos import troca_senha
            from modulos.csv_parser import (processar_csv_extrato, parse_data,
                                            parse_valor)
            self.login.cripto = (
                'Dados em disco cifrados (AES-256).' if bd_seguro.CRIPTO_REPOUSO
                else 'ATENÇÃO: esta versão não tem SQLCipher; os dados ficam '
                     'protegidos só pelo armazenamento privado do Android.')
            return True
        except Exception as e:
            self.sm.current = 'login'
            self.login.info = f'Falha ao carregar módulos: {e}'
            return False

    def on_pause(self):
        return True                         # não encerra ao ir para segundo plano

    def on_resume(self):
        if self.db:
            self._atualizar_tudo()

    def on_stop(self):
        self._encerrar_conta()

    def _tecla(self, _win, tecla, *_):
        if tecla == 27 and self.sm.current == 'home':       # botão voltar
            atual = self.home.ids.abas.current
            if atual != 'resumo':
                self.ir_aba('resumo')
                return True
        return False

    # ══ utilidades de interface ═════════════════════════════════════

    def _texto(self, txt, **kw):
        lb = Label(text=txt, markup=True, size_hint_y=None, halign='left',
                   valign='top', **kw)
        lb.bind(width=lambda w, v: setattr(w, 'text_size', (v, None)))
        lb.bind(texture_size=lambda w, v: setattr(w, 'height', v[1] + dp(8)))
        return lb

    def _popup(self, titulo, corpo, botoes, altura=0.7):
        """botoes: [(texto, funcao_ou_None)]; fecha o popup ao tocar."""
        caixa = BoxLayout(orientation='vertical', spacing=dp(8),
                          padding=dp(10))
        rolagem = ScrollView()
        rolagem.add_widget(corpo)
        caixa.add_widget(rolagem)
        linha = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        pop = Popup(title=titulo, content=caixa, size_hint=(0.94, altura),
                    auto_dismiss=False)
        for txt, fn in botoes:
            b = Button(text=txt, background_normal='',
                       background_color=(0.20, 0.55, 0.85, 1))

            def tocar(_b, fn=fn):
                pop.dismiss()
                if fn:
                    Clock.schedule_once(lambda dt: fn(), 0)
            b.bind(on_release=tocar)
            linha.add_widget(b)
        caixa.add_widget(linha)
        pop.open()
        return pop

    def aviso(self, titulo, texto):
        corpo = BoxLayout(orientation='vertical', size_hint_y=None)
        t = self._texto(texto)
        corpo.add_widget(t)
        corpo.bind(minimum_height=corpo.setter('height'))
        self._popup(titulo, corpo, [('OK', None)], altura=0.55)

    def confirmar(self, titulo, texto, ao_sim, sim='Continuar'):
        corpo = BoxLayout(orientation='vertical', size_hint_y=None)
        corpo.add_widget(self._texto(texto))
        corpo.bind(minimum_height=corpo.setter('height'))
        self._popup(titulo, corpo, [('Cancelar', None), (sim, ao_sim)],
                    altura=0.6)

    def pedir_texto(self, titulo, dica, ao_ok, senha=True, texto=''):
        corpo = BoxLayout(orientation='vertical', size_hint_y=None,
                          spacing=dp(8))
        corpo.add_widget(self._texto(texto))
        campo = Factory.Campo(hint_text=dica, password=senha, multiline=False,
                          size_hint_y=None, height=dp(46))
        corpo.add_widget(campo)
        corpo.bind(minimum_height=corpo.setter('height'))
        self._popup(titulo, corpo, [('Cancelar', None),
                                    ('OK', lambda: ao_ok(campo.text))],
                    altura=0.55)

    # ══ login / conta ═══════════════════════════════════════════════

    def _contas_path(self):
        return os.path.join('dados', 'contas.json')

    def _contas_locais(self):
        try:
            with open(self._contas_path(), encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _lembrar_conta(self, chaves):
        d = self._contas_locais()
        d[identidade.normalizar_usuario(chaves.usuario)] = chaves.net_id
        with open(self._contas_path(), 'w', encoding='utf-8') as f:
            json.dump(d, f)

    def _iniciar_sessao(self):
        chaves = identidade.carregar_sessao('dados')
        if chaves is not None and not os.path.exists(
                os.path.join('dados', f'{chaves.net_id}.db')):
            chaves = None
        if chaves is not None:
            self.abrir_conta(chaves, False, None)
            return
        self.sm.current = 'login'
        users = list(self._contas_locais())
        if users:
            self.login.ids.usuario.text = users[-1]

    def tentar_login(self, usuario, senha, confirma, manter):
        usuario, senha = (usuario or '').strip(), senha or ''
        if not usuario or not senha:
            self.login.info = 'Informe usuário e senha.'
            return
        self.login.ocupado = True
        self.login.info = 'Verificando...'

        def trabalho():
            try:
                ch = identidade.derivar(usuario, senha)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._login_erro(str(e)), 0)
                return
            Clock.schedule_once(
                lambda dt: self._login_derivado(ch, usuario, senha, confirma,
                                                manter), 0)
        threading.Thread(target=trabalho, daemon=True).start()

    def _login_erro(self, msg):
        self.login.ocupado = False
        self.login.info = msg

    def _login_derivado(self, ch, usuario, senha, confirma, manter):
        self.login.ocupado = False
        self.login.info = ''
        if os.path.exists(os.path.join('dados', f'{ch.net_id}.db')):
            return self._concluir_login(ch, False, manter)
        conhecida = self._contas_locais().get(
            identidade.normalizar_usuario(usuario))
        if conhecida and conhecida != ch.net_id:
            self.login.info = 'Senha incorreta.'
            return
        erro = identidade.validar(usuario, senha)
        if erro:
            self.login.info = erro
            return
        if not self.login.pedir_confirma:
            self.login.pedir_confirma = True
            self.login.info = (
                'Primeiro acesso neste aparelho. Confirme a senha.\n'
                'Se você já tem conta em outro aparelho, use o MESMO usuário '
                'e senha: os dados chegam por sincronização.\n'
                'Não existe recuperação de senha: guarde-a e faça backup. '
                'Use uma senha LONGA (frase de 4 palavras ou '
                f'{identidade.MIN_SENHA}+ caracteres).')
            return
        if confirma != senha:
            self.login.info = 'As senhas não conferem.'
            return
        self._concluir_login(ch, True, manter)

    def _concluir_login(self, ch, novo, manter):
        if manter:
            identidade.guardar_sessao('dados', ch)
        else:
            identidade.esquecer_sessao('dados')
        self._lembrar_conta(ch)
        self.login.pedir_confirma = False
        self.login.ids.senha.text = self.login.ids.confirma.text = ''
        bk, self._backup_login = self._backup_login, None
        self.abrir_conta(ch, novo, bk)

    def escolher_backup_login(self):
        plataforma.escolher_arquivo(self._backup_login_escolhido,
                                    lambda m: self.aviso('Backup', m))

    def _backup_login_escolhido(self, caminho):
        def com_frase(frase):
            try:
                with open(caminho, 'rb') as f:
                    blob = f.read()
                identidade.abrir_backup(blob, frase)          # valida agora
            except Exception as e:
                self.aviso('Backup', str(e))
                return
            self._backup_login = (blob, frase)
            self.login.info = ('Backup carregado: será importado ao entrar. '
                               'Use o usuário e a senha que quiser.')
        self.pedir_texto('Backup', 'Frase do backup', com_frase)

    def _forcar_colunas(self):
        """Mesmas colunas que o desktop garante (bancos antigos)."""
        for tabela, col, tipo in (
                ('categories', 'is_savings_goal', 'INTEGER DEFAULT 0'),
                ('categories', 'is_hidden', 'INTEGER DEFAULT 0'),
                ('categories', 'year', f'INTEGER DEFAULT {date.today().year}'),
                ('transactions', 'savings_category_id', 'INTEGER'),
                ('transactions', 'is_saving_transaction',
                 'INTEGER DEFAULT 0')):
            existe = self.db.execute(
                f"SELECT COUNT(*) FROM pragma_table_info('{tabela}') "
                f"WHERE name='{col}'").fetchone()[0] > 0
            if not existe:
                self.db.execute(f'ALTER TABLE {tabela} ADD COLUMN {col} {tipo}')
        self.db.commit()

    def abrir_conta(self, chaves, novo=False, bk=None):
        try:
            from modulos.database import DBManager, DBUpdater
            from modulos.rede import RedeConta
            net = chaves.net_id
            db_path = os.path.join('dados', f'{net}.db')
            mgr = DBManager(net, chaves.chave_bd)
            self.db = mgr.connect()
            bd_seguro.definir_ativo(db_path, chaves.chave_bd)
            mgr.create_tables()
            if not DBUpdater.check_and_update(self.db, net):
                raise RuntimeError('não foi possível atualizar o banco')
            self._forcar_colunas()
            u = self.db.execute(
                'SELECT * FROM users ORDER BY id LIMIT 1').fetchone()
            if not u:
                self.db.execute('INSERT INTO users(username,password) '
                                'VALUES(?,?)', (chaves.usuario, '-'))
                self.db.commit()
                u = self.db.execute(
                    'SELECT * FROM users ORDER BY id LIMIT 1').fetchone()
            self.user_id = u['id']
            sync_core.preparar(self.db)
            if bk:
                try:
                    backup.importar(self.db, bk[0], bk[1])
                except Exception as e:
                    self.aviso('Backup', f'Falha ao importar: {e}')
            self.chaves = chaves
            plataforma.adquirir_multicast()
            self.rede = RedeConta(
                os.getcwd(), chaves, db_path,
                ao_alterar=lambda: Clock.schedule_once(
                    lambda dt: self._atualizar_tudo(), 0),
                ao_estado=lambda: Clock.schedule_once(
                    lambda dt: self._atualizar_conta(), 0),
                ao_sair=lambda quem: Clock.schedule_once(
                    lambda dt: self._sair_remoto(quem), 0))
            r = self.rede.iniciar()
            if not r.get('sucesso'):
                self.home.ids.l_sync_resumo.text = r.get('erro', '')
        except PermissionError as e:
            identidade.esquecer_sessao('dados')
            self._encerrar_conta()
            self.sm.current = 'login'
            self.login.info = str(e)
            return
        except Exception as e:
            self._encerrar_conta()
            self.sm.current = 'login'
            self.login.info = f'Erro ao abrir a conta: {e}'
            return
        self.sm.current = 'home'
        self.ir_aba('resumo')
        self._atualizar_tudo()
        if getattr(self, '_timer', None) is None:
            self._timer = Clock.schedule_interval(
                lambda dt: self._atualizar_conta(), 5)

    def _encerrar_conta(self):
        if getattr(self, '_timer', None):
            self._timer.cancel()
            self._timer = None
        try:
            if self.rede:
                self.rede.parar()
        except Exception:
            pass
        plataforma.liberar_multicast()
        try:
            if self.db:
                self.db.close()
        except Exception:
            pass
        self.rede = self.db = self.chaves = self.user_id = None

    def sair_da_conta(self, aviso=''):
        identidade.esquecer_sessao('dados')
        self._encerrar_conta()
        self.sm.current = 'login'
        self.login.info = aviso

    def confirmar_sair(self):
        self.confirmar('Sair da conta',
                       'Sair desta conta neste aparelho?\n\nOs dados continuam '
                       'cifrados no aparelho e voltam ao entrar de novo.',
                       self.sair_da_conta, sim='Sair')

    def _sair_remoto(self, quem):
        self.sair_da_conta(f'Este aparelho foi desconectado por {quem}. '
                           'Entre novamente com usuário e senha.')

    # ══ navegação e telas ═══════════════════════════════════════════

    def ir_aba(self, nome):
        self.home.ids.abas.current = nome
        for b in self.home.ids.barra.children:      # destaque da aba atual
            b.state = 'down' if b.aba == nome else 'normal'
        self._atualizar_tudo()

    def mudar_mes(self, d):
        m = self.mes + d
        self.ano += (m - 1) // 12
        self.mes = (m - 1) % 12 + 1
        self._atualizar_tudo()

    def _intervalo_mes(self):
        ini = f'{self.ano:04d}-{self.mes:02d}-01'
        a, m = (self.ano + 1, 1) if self.mes == 12 else (self.ano,
                                                         self.mes + 1)
        return ini, f'{a:04d}-{m:02d}-01'

    def _atualizar_tudo(self):
        if not self.db:
            return
        try:
            self._atualizar_resumo()
            self._atualizar_lista()
            self._atualizar_conta()
        except Exception as e:
            self.home.ids.l_sync_resumo.text = f'Erro ao atualizar: {e}'

    def _atualizar_resumo(self):
        ids = self.home.ids
        ini, fim = self._intervalo_mes()
        ids.l_mes.text = f'{MESES[self.mes - 1]} de {self.ano}'
        tot = {r['t']: r['s'] for r in self.db.execute(
            'SELECT transaction_type t, COALESCE(SUM(amount),0) s '
            'FROM transactions WHERE user_id=? AND date>=? AND date<? '
            'GROUP BY transaction_type', (self.user_id, ini, fim))}
        ent, sai = tot.get('entrada', 0.0), tot.get('saida', 0.0)
        saldo = ent - sai
        cor = VERDE if saldo >= 0 else VERMELHO
        ids.l_cards.text = (
            f'[color={VERDE}]Entradas  {brl(ent)}[/color]\n'
            f'[color={VERMELHO}]Saídas  {brl(sai)}[/color]\n'
            f'[color={cor}][b]Saldo  {brl(saldo)}[/b][/color]')
        linhas = []
        for r in self.db.execute(
                "SELECT COALESCE(c.name,'Sem categoria') n, SUM(t.amount) s "
                'FROM transactions t LEFT JOIN categories c '
                'ON c.id=t.category_id WHERE t.user_id=? AND '
                "t.transaction_type='saida' AND t.date>=? AND t.date<? "
                'GROUP BY n ORDER BY s DESC LIMIT 8',
                (self.user_id, ini, fim)):
            linhas.append(f'{r["n"]}   [b]{brl(r["s"])}[/b]')
        ids.l_cats.text = '\n'.join(linhas) or 'Nenhuma saída neste mês.'

    def _atualizar_lista(self):
        lista = self.home.ids.lista
        lista.clear_widgets()
        ini, fim = self._intervalo_mes()
        for r in self.db.execute(
                'SELECT id, date, description, amount, transaction_type tipo '
                'FROM transactions WHERE user_id=? AND date>=? AND date<? '
                'ORDER BY date DESC, id DESC LIMIT 300',
                (self.user_id, ini, fim)):
            ent = r['tipo'] == 'entrada'
            cor = '2ecc71' if ent else 'e74c3c'
            b = Button(
                text=(f'{data_br(r["date"])}  {r["description"][:34]}\n'
                      f'[color={cor}]{"+" if ent else "-"} '
                      f'{brl(r["amount"])}[/color]'),
                markup=True, size_hint_y=None, height=dp(62),
                halign='left', valign='middle', background_normal='',
                background_color=(0.16, 0.19, 0.22, 1))
            b.bind(size=lambda w, s: setattr(w, 'text_size', (s[0] - dp(20),
                                                              s[1])))
            b.bind(on_release=lambda _b, rid=r['id'], d=r['description']:
                   self._opcoes_lancamento(rid, d))
            lista.add_widget(b)
        if not lista.children:
            lista.add_widget(self._texto('Nenhum lançamento neste mês.'))

    def _atualizar_conta(self):
        if not self.rede:
            return
        ids = self.home.ids
        ids.l_conta.text = f'[b]Conta:[/b] {self.chaves.usuario}'
        try:
            e = self.rede.estado()
            pend = e.get('pendentes') or 0
            nomes = ', '.join(
                f'{d["nome"]} ({"online" if d["online"] else "offline"})'
                for d in e.get('dispositivos', [])) or 'nenhum ainda'
            txt = (f'[b]Rede:[/b] {e.get("rede", "—")}\n'
                   f'[b]Aparelhos:[/b] {nomes}\n'
                   f'[b]Pendências:[/b] {pend}')
            ids.l_rede.text = txt
            on = e.get('pares_online') or 0
            ids.l_sync_resumo.text = (
                f'Sincronização: {on} aparelho(s) online'
                + (f' · {pend} pendente(s)' if pend else ' · em dia'))
        except Exception as ex:
            ids.l_rede.text = f'Rede indisponível: {ex}'

    def sincronizar_agora(self):
        try:
            self.rede.sincronizar_agora()
            self.aviso('Sincronização', 'Pedido enviado aos outros aparelhos.')
        except Exception as e:
            self.aviso('Sincronização', f'Não foi possível: {e}')

    # ══ lançamentos ═════════════════════════════════════════════════

    def _pos_mudanca(self):
        try:
            from modulos import loans
            for r in self.db.execute('SELECT id FROM loans').fetchall():
                loans.sync_loan_payments(self.db, r['id'])
        except Exception:
            pass                           # sem empréstimos / módulo ausente
        self._atualizar_tudo()
        try:
            self.rede.sincronizar_agora()
        except Exception:
            pass

    def abrir_novo_lancamento(self):
        corpo = BoxLayout(orientation='vertical', size_hint_y=None,
                          spacing=dp(8))
        corpo.bind(minimum_height=corpo.setter('height'))
        tipo = BoxLayout(size_hint_y=None, height=dp(44))
        t_sai = ToggleButton(text='Saída', group='tipo_tx', state='down',
                             allow_no_selection=False)
        t_ent = ToggleButton(text='Entrada', group='tipo_tx',
                             allow_no_selection=False)
        tipo.add_widget(t_sai)
        tipo.add_widget(t_ent)
        valor = Factory.Campo(hint_text='Valor (ex.: 25,90)', multiline=False,
                          input_filter=None, size_hint_y=None, height=dp(46))
        desc = Factory.Campo(hint_text='Descrição', multiline=False,
                         size_hint_y=None, height=dp(46))
        data = Factory.Campo(text=date.today().strftime('%d/%m/%Y'),
                         hint_text='Data (dd/mm/aaaa)', multiline=False,
                         size_hint_y=None, height=dp(46))
        cats = self.db.execute(
            'SELECT id, name FROM categories WHERE user_id=? AND '
            'COALESCE(is_hidden,0)=0 AND year=? ORDER BY name',
            (self.user_id, date.today().year)).fetchall()
        mapa = {'Sem categoria': None}
        mapa.update({c['name']: c['id'] for c in cats})
        spin = Spinner(text='Sem categoria', values=list(mapa),
                       size_hint_y=None, height=dp(46))
        for w in (tipo, valor, desc, data, spin):
            corpo.add_widget(w)

        def salvar():
            v = parse_valor(valor.text)
            d = parse_data(data.text)
            if v is None or abs(v) < 0.005:
                return self.aviso('Lançamento', 'Informe um valor válido.')
            if not d:
                return self.aviso('Lançamento', 'Data inválida (dd/mm/aaaa).')
            if not desc.text.strip():
                return self.aviso('Lançamento', 'Informe a descrição.')
            self.db.execute(
                'INSERT INTO transactions(user_id, amount, description, '
                'transaction_type, date, category_id) VALUES(?,?,?,?,?,?)',
                (self.user_id, round(abs(v), 2), desc.text.strip()[:200],
                 'entrada' if t_ent.state == 'down' else 'saida', d,
                 mapa.get(spin.text)))
            self.db.commit()
            self._pos_mudanca()
        self._popup('Novo lançamento', corpo,
                    [('Cancelar', None), ('Salvar', salvar)], altura=0.85)

    def _opcoes_lancamento(self, rid, descricao):
        self.confirmar('Lançamento', f'{descricao}\n\nExcluir este lançamento?',
                       lambda: self._excluir(rid), sim='Excluir')

    def _excluir(self, rid):
        self.db.execute('DELETE FROM transactions WHERE id=? AND user_id=?',
                        (rid, self.user_id))
        self.db.commit()
        self._pos_mudanca()

    # ══ importar extrato (CSV) ══════════════════════════════════════

    def importar_extrato(self):
        plataforma.escolher_arquivo(self._csv_escolhido,
                                    lambda m: self.aviso('Importar', m))

    def _csv_escolhido(self, caminho):
        try:
            with open(caminho, 'rb') as f:
                self._csv_bytes = f.read()
        except Exception as e:
            return self.aviso('Importar', f'Não consegui ler o arquivo: {e}')
        self._previa_csv(False)

    def _eh_duplicada(self, t):
        return self.db.execute(
            'SELECT 1 FROM transactions WHERE user_id=? AND date=? AND '
            'transaction_type=? AND ABS(amount-?)<0.005 AND '
            'lower(description)=lower(?) LIMIT 1',
            (self.user_id, t['data'], t['tipo'], t['valor'],
             t['descricao'])).fetchone() is not None

    def _previa_csv(self, inverter):
        ok, txs, msg = processar_csv_extrato(self._csv_bytes, inverter)
        if not ok:
            return self.aviso('Importar extrato', msg)
        novas = [t for t in txs if not self._eh_duplicada(t)]
        exemplo = '\n'.join(
            f'{data_br(t["data"])}  {t["descricao"][:28]}  '
            f'{"+" if t["tipo"] == "entrada" else "-"}{brl(t["valor"])}'
            for t in novas[:6]) or '(nenhuma nova)'
        texto = (f'{msg}\n\n[b]{len(novas)}[/b] nova(s) · '
                 f'{len(txs) - len(novas)} já existente(s) (serão ignoradas)'
                 f'\n\n{exemplo}')
        corpo = BoxLayout(orientation='vertical', size_hint_y=None)
        corpo.add_widget(self._texto(texto))
        corpo.bind(minimum_height=corpo.setter('height'))
        self._popup(
            'Importar extrato', corpo,
            [('Cancelar', None),
             ('Inverter entrada/saída', lambda: self._previa_csv(not inverter)),
             (f'Importar {len(novas)}',
              (lambda: self._gravar_importacao(novas)) if novas else None)],
            altura=0.8)

    def _gravar_importacao(self, novas):
        try:
            for t in novas:
                self.db.execute(
                    'INSERT INTO transactions(user_id, amount, description, '
                    'transaction_type, date, category_id) '
                    'VALUES(?,?,?,?,?,NULL)',
                    (self.user_id, t['valor'], t['descricao'], t['tipo'],
                     t['data']))
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            return self.aviso('Importar extrato', f'Erro ao gravar: {e}')
        self._csv_bytes = None
        self._pos_mudanca()
        self.aviso('Importar extrato', f'{len(novas)} lançamento(s) '
                   'importado(s). Eles chegam sem categoria: categorize no '
                   'computador (a sincronização traz tudo de volta).')

    # ══ backup ══════════════════════════════════════════════════════

    def exportar_backup(self):
        def com_frase(frase):
            try:
                blob, n = backup.exportar(self.db, frase)
            except ValueError as e:
                return self.aviso('Backup', str(e))
            nome = f'rrfs-backup-{datetime.now():%Y%m%d-%H%M}.rrfs'
            pasta = os.path.join(self.pasta, 'exportados')
            os.makedirs(pasta, exist_ok=True)
            caminho = os.path.join(pasta, nome)
            with open(caminho, 'wb') as f:
                f.write(blob)
            self._oferecer_saida(caminho, n)
        self.pedir_texto(
            'Exportar backup', 'Frase do backup', com_frase,
            texto=f'Escolha uma frase (mín. {identidade.MIN_FRASE} caracteres) '
                  'para cifrar o backup. Sem ela o arquivo não abre.')

    def _oferecer_saida(self, caminho, n):
        corpo = BoxLayout(orientation='vertical', size_hint_y=None)
        corpo.add_widget(self._texto(
            f'Backup criado ({n} registros).\n\nGuarde o arquivo em outro '
            'lugar. Se perder todos os aparelhos, crie um login e use '
            '"Tenho um backup" na tela de entrada.'))
        corpo.bind(minimum_height=corpo.setter('height'))

        def baixar():
            try:
                onde = plataforma.salvar_em_downloads(caminho)
                self.aviso('Backup', f'Salvo em: {onde}')
            except Exception as e:
                self.aviso('Backup', f'Não foi possível salvar: {e}')

        def enviar():
            try:
                plataforma.compartilhar_arquivo(caminho)
            except Exception as e:
                self.aviso('Backup', f'Não foi possível compartilhar: {e}')
        self._popup('Backup pronto', corpo,
                    [('Fechar', None), ('Compartilhar', enviar),
                     ('Salvar em Downloads', baixar)], altura=0.65)

    def importar_backup(self):
        plataforma.escolher_arquivo(self._backup_escolhido,
                                    lambda m: self.aviso('Backup', m))

    def _backup_escolhido(self, caminho):
        def com_frase(frase):
            try:
                with open(caminho, 'rb') as f:
                    n = backup.importar(self.db, f.read(), frase)
            except Exception as e:
                return self.aviso('Backup', str(e))
            self._pos_mudanca()
            self.aviso('Backup', f'Backup importado ({n} registros).')
        self.pedir_texto('Importar backup', 'Frase do backup', com_frase)

    # ══ alterar senha ═══════════════════════════════════════════════

    def abrir_alterar_senha(self):
        corpo = BoxLayout(orientation='vertical', size_hint_y=None,
                          spacing=dp(8))
        corpo.bind(minimum_height=corpo.setter('height'))
        corpo.add_widget(self._texto(
            'Seus dados são mantidos. Os OUTROS aparelhos não mudam sozinhos '
            '(a senha nova nunca viaja pela rede antiga): neles, use '
            '"Alterar senha" com a mesma senha nova, ou saia da conta e '
            'entre com a nova.'))
        campos = []
        for dica in ('Senha atual', 'Senha nova', 'Confirmar senha nova'):
            c = Factory.Campo(hint_text=dica, password=True, multiline=False,
                          size_hint_y=None, height=dp(46))
            corpo.add_widget(c)
            campos.append(c)

        def ok():
            atual, nova, conf = (c.text for c in campos)
            if not atual or not nova:
                return self.aviso('Alterar senha', 'Preencha os campos.')
            if nova != conf:
                return self.aviso('Alterar senha', 'A confirmação não confere.')
            erro = identidade.validar(self.chaves.usuario, nova)
            if erro:
                return self.aviso('Alterar senha', erro)
            self._trocar_senha(atual, nova)
        self._popup('Alterar senha', corpo,
                    [('Cancelar', None), ('Alterar', ok)], altura=0.85)

    def _trocar_senha(self, atual, nova):
        usuario = self.chaves.usuario
        tinha_sessao = identidade.carregar_sessao('dados') is not None
        corpo = BoxLayout(orientation='vertical', size_hint_y=None)
        corpo.add_widget(self._texto('Migrando seus dados... aguarde.'))
        corpo.bind(minimum_height=corpo.setter('height'))
        # sem botões: fecha sozinho quando a migração termina
        self._pop_troca = self._popup('Alterar senha', corpo, [], altura=0.4)
        self._encerrar_conta()                 # fecha rede e banco

        def trabalho():
            try:
                novas = troca_senha.trocar_senha('dados', usuario, atual, nova)
                msg, erro = None, None
            except troca_senha.ErroTroca as e:
                novas, erro = None, f'{e}\n\nSeus dados não foram alterados.'
            except Exception as e:
                novas, erro = None, f'Erro inesperado: {e}'
            Clock.schedule_once(lambda dt: self._fim_troca(
                usuario, atual, novas, erro, tinha_sessao), 0)
        threading.Thread(target=trabalho, daemon=True).start()

    def _fim_troca(self, usuario, atual, novas, erro, tinha_sessao):
        pop = getattr(self, '_pop_troca', None)
        if pop is not None:
            pop.dismiss()
            self._pop_troca = None
        if novas is not None:
            self.abrir_conta(novas, False, None)
            self.aviso('Alterar senha',
                       'Senha alterada. Nos outros aparelhos, use "Alterar '
                       'senha" com a mesma senha nova (ou saia da conta e '
                       'entre com ela).')
        else:
            # a conta antiga continua intacta: reabre com a senha atual
            try:
                self.abrir_conta(identidade.derivar(usuario, atual), False,
                                 None)
            except Exception:
                self.sm.current = 'login'
            self.aviso('Alterar senha', erro or 'Não foi possível alterar.')

    # ══ transparência e diagnóstico ═════════════════════════════════

    def mostrar_transparencia(self):
        cripto = ('Seu banco de dados fica [b]cifrado em disco[/b] (AES-256).'
                  if bd_seguro.CRIPTO_REPOUSO else
                  'Nesta versão o banco NÃO tem cifra própria: os dados ficam '
                  'no armazenamento privado do app, protegido pelo Android.')
        texto = (
            '[b]Transparência[/b]\n\n'
            'O RRFS Finanças é um sistema de gestão financeira pessoal. Não '
            'existe servidor do desenvolvedor: seus dados ficam [b]só nos '
            'seus aparelhos[/b], que conversam entre si.\n\n'
            '[b]Sincronização[/b]: funciona offline; aparelhos na mesma rede '
            'se encontram sozinhos; pela internet se sincronizam à distância, '
            'sem servidor central. Para se reconhecerem, basta o mesmo '
            'usuário e senha. [b]Neste celular a sincronização acontece '
            'enquanto o app está aberto.[/b]\n\n'
            '[b]Criptografia[/b]: toda a comunicação entre seus aparelhos é '
            'cifrada de ponta a ponta. As chaves nascem do seu usuário e '
            'senha e não saem dos aparelhos. Por isso não existe recuperação '
            'de senha.\n\n'
            f'{cripto}\n\n'
            '[b]Backup[/b]: exporte e guarde o arquivo (cifrado com a sua '
            'frase) em local seguro; use também mais de um aparelho.\n\n'
            '[b]Arquivos[/b]: o app não pede acesso às suas pastas. Só lê o '
            'arquivo que você escolher e só grava o backup que você mandar '
            'exportar.\n\n'
            '[b]O que NÃO coletamos[/b]: nenhum dado dos seus aparelhos nem '
            'dos seus lançamentos. Sem anúncios, sem rastreamento.\n\n'
            '[b]Portas[/b]: a rede Tox usa UDP e, quando bloqueado, relays '
            'TCP (inclusive porta 443). Isso dificulta bloqueios, mas não '
            'garante contra censura.')
        corpo = BoxLayout(orientation='vertical', size_hint_y=None)
        corpo.add_widget(self._texto(texto))
        corpo.bind(minimum_height=corpo.setter('height'))
        self._popup('Transparência', corpo, [('Fechar', None)], altura=0.92)

    def mostrar_diagnostico(self):
        linhas = []
        for nome, ok, det in plataforma.diagnostico():
            cor = VERDE if ok else VERMELHO
            linhas.append(f'[color={cor}]{"OK " if ok else "FALHA "}[/color]'
                          f'[b]{nome}[/b]  {det}')
        corpo = BoxLayout(orientation='vertical', size_hint_y=None)
        corpo.add_widget(self._texto('\n\n'.join(linhas)))
        corpo.bind(minimum_height=corpo.setter('height'))
        self._popup('Diagnóstico', corpo, [('Fechar', None)], altura=0.85)


if __name__ == '__main__':
    RRFSApp().run()
