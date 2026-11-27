"""
RRFS Gestão Financeira - App Desktop
Bandeja do sistema + CustomTkinter
Duplo clique no ícone $ abre a janela
"""

import sys
import os
import threading
import time

# Adiciona o diretório pai ao path (para importar core/)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
from PIL import Image
import pystray
from pystray import MenuItem as item

from config import APP_NOME, APP_VERSAO, APP_ICONE
from core.conexao import conexao, TipoConexao
from core.tor_manager import tor
from core.cache_local import cache_local
from core.sessao import sessao
from core.sync import sync
from ui.janela_login import JanelaLogin
from ui.janela_principal import JanelaPrincipal

# Tema escuro
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ==================== APP PRINCIPAL ====================

class AppRRFS:
    def __init__(self):
        self.root           = None
        self.janela_atual   = None
        self.icone_bandeja  = None
        self._visivel       = False
        self._iniciado      = False
        self._lock_janela   = threading.Lock()

    def iniciar(self):
        """Ponto de entrada principal"""
        print(f"[APP] Iniciando {APP_NOME} v{APP_VERSAO}")

        # Inicia Tor em background
        print("[APP] Iniciando Tor em background...")
        tor.iniciar_em_thread(callback_concluido=self._tor_pronto)

        # Testa conexão
        threading.Thread(target=self._iniciar_conexao, daemon=True).start()

        # Cria janela principal tkinter (necessário para pystray no Linux)
        self.root = ctk.CTk()
        self.root.withdraw()  # Esconde inicialmente
        self.root.title(APP_NOME)
        self.root.protocol("WM_DELETE_WINDOW", self._minimizar)

        # Inicia bandeja do sistema
        threading.Thread(target=self._criar_bandeja, daemon=True).start()

        # Mostra tela de login (ou principal se sessão salva)
        self.root.after(500, self._abrir_janela_inicial)

        # Loop principal
        self.root.mainloop()

    def _iniciar_conexao(self):
        """Inicia conexão em background"""
        tipo = conexao.conectar()
        print(f"[APP] Conexão: {tipo.value}")

    def _tor_pronto(self, sucesso: bool):
        print(f"[APP] Tor: {'✅ OK' if sucesso else '❌ Falhou'}")

    def _abrir_janela_inicial(self):
        """Abre login ou dashboard baseado na sessão"""
        self._abrir_login()

    def _abrir_login(self):
        """Abre tela de login"""
        with self._lock_janela:
            if self.janela_atual:
                try:
                    self.janela_atual.destroy()
                except Exception:
                    pass

            self.janela_atual = JanelaLogin(
                self.root,
                callback_login_ok=self._login_realizado
            )
            self._mostrar_janela()

    def _login_realizado(self, dados_sessao: dict):
        """Chamado após login bem-sucedido"""
        print(f"[APP] Login: {dados_sessao.get('username')}")

        # Inicia sync automático
        sync.iniciar_sync_automatico()

        with self._lock_janela:
            if self.janela_atual:
                try:
                    self.janela_atual.destroy()
                except Exception:
                    pass

            self.janela_atual = JanelaPrincipal(
                self.root,
                callback_logout=self._logout
            )
            self._mostrar_janela()

    def _logout(self):
        """Chamado ao fazer logout"""
        sessao.logout()
        sync.parar_sync()
        self._abrir_login()

    # ==================== BANDEJA ====================

    def _criar_icone_bandeja(self):
        """Cria ícone $ para a bandeja do sistema"""
        from PIL import Image, ImageDraw, ImageFont
        import io

        # Cria imagem 64x64 com $ verde
        img  = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Fundo circular escuro
        draw.ellipse([2, 2, 62, 62], fill=(22, 27, 34, 255))

        # Borda verde
        draw.ellipse([2, 2, 62, 62], outline=(35, 134, 54, 255), width=3)

        # Símbolo $
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        except Exception:
            font = ImageFont.load_default()

        draw.text((15, 10), "$", fill=(35, 134, 54, 255), font=font)

        return img

    def _criar_bandeja(self):
        """Cria ícone na bandeja do sistema"""
        icone_img = self._criar_icone_bandeja()

        menu = pystray.Menu(
            item('Abrir RRFS',    self._mostrar_janela_bandeja, default=True),
            item('Status',         self._status_conexao),
            pystray.Menu.SEPARATOR,
            item('Sair',           self._sair_app)
        )

        self.icone_bandeja = pystray.Icon(
            name    = "rrfs_financeiro",
            icon    = icone_img,
            title   = APP_NOME,
            menu    = menu
        )

        # Duplo clique abre a janela
        self.icone_bandeja.run_detached()
        print("[APP] Bandeja do sistema criada")

    def _mostrar_janela_bandeja(self, icon=None, item=None):
        """Chamado pelo ícone da bandeja"""
        if self.root:
            self.root.after(0, self._mostrar_janela)

    def _status_conexao(self, icon=None, item=None):
        """Mostra status da conexão no título"""
        tipo = conexao.tipo_atual
        msgs = {
            TipoConexao.DIRETA    : "✅ Conexão Direta",
            TipoConexao.TOR       : "🧅 Conectado via Tor",
            TipoConexao.OFFLINE   : "❌ Sem Conexão",
            TipoConexao.CONECTANDO: "⏳ Conectando..."
        }
        if self.icone_bandeja:
            self.icone_bandeja.title = f"{APP_NOME} - {msgs.get(tipo, '')}"

    def _sair_app(self, icon=None, item=None):
        """Encerra o app completamente"""
        print("[APP] Encerrando...")
        tor.parar()
        cache_local.fechar()
        if self.icone_bandeja:
            self.icone_bandeja.stop()
        if self.root:
            self.root.after(0, self.root.destroy)

    def _minimizar(self):
        """Minimiza para bandeja ao fechar janela"""
        if self.root:
            self.root.withdraw()
        self._visivel = False

    def _mostrar_janela(self):
        """Mostra/maximiza a janela"""
        if self.root:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.root.state('zoomed') if sys.platform == 'win32' else \
            self.root.attributes('-zoomed', True)
        self._visivel = True


# ==================== ENTRADA ====================
def main():
    app = AppRRFS()
    app.iniciar()

if __name__ == '__main__':
    main()
