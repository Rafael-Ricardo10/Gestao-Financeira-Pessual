"""
Widget do Assistente de IA Financeiro
Agente Financeiro Inteligente com Engenharia de Prompt Avançada
"""
import json
import re
from datetime import datetime, timedelta

import requests
import urllib3

urllib3.disable_warnings()

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QMessageBox, QDialog,
    QApplication
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QShortcut

from interface.dialogs.ai_dialogs import ApiConfigDialog

# ============================================================
# ENDPOINTS — importados de financial_ai para evitar duplicata
# ============================================================
from modulos.financial_ai import (
    LOCAL_URL, LOCAL_IP, LOCAL_PORT,
    ONION_URL
)


# ============================================================
# AGENTE FINANCEIRO LOCAL - MOTOR DE INTELIGÊNCIA
# ============================================================

class AgenteFinanceiroLocal:
    """
    Agente financeiro local que:
    1. Responde perguntas simples LOCALMENTE (zero tokens)
    2. Para perguntas complexas, monta prompt MÍNIMO e PRECISO
    3. Coleta apenas os dados NECESSÁRIOS para cada pergunta
    4. Garante respostas rápidas no servidor local
    """

    # ── Padrões respondidos localmente (sem servidor) ────────
    PADROES_LOCAIS = {
        # Saldo
        'saldo':               '_resp_saldo',
        'quanto tenho':        '_resp_saldo',
        'meu dinheiro':        '_resp_saldo',
        'situação financeira': '_resp_saldo',
        'quanto sobrou':       '_resp_saldo',
        'disponível':          '_resp_saldo',
        'quanto posso gastar': '_resp_saldo',

        # Transações recentes
        'transações recentes': '_resp_recentes',
        'transacoes recentes': '_resp_recentes',
        'últimos gastos':      '_resp_recentes',
        'ultimos gastos':      '_resp_recentes',
        'última compra':       '_resp_recentes',
        'ultima compra':       '_resp_recentes',
        'movimentações':       '_resp_recentes',
        'movimentacoes':       '_resp_recentes',
        'o que gastei':        '_resp_recentes',

        # Metas
        'minhas metas':        '_resp_metas',
        'metas de economia':   '_resp_metas',
        'poupança':            '_resp_metas',
        'poupanca':            '_resp_metas',
        'economizando':        '_resp_metas',
        'objetivos':           '_resp_metas',
        'meta de':             '_resp_metas',

        # Categorias
        'categorias':          '_resp_categorias',
        'gastos por categoria':'_resp_categorias',
        'onde gasto mais':     '_resp_categorias',
        'por categoria':       '_resp_categorias',

        # Maiores gastos
        'maior gasto':         '_resp_maiores',
        'maiores gastos':      '_resp_maiores',
        'mais gastei':         '_resp_maiores',
        'mais caro':           '_resp_maiores',
        'maior despesa':       '_resp_maiores',

        # Empréstimos
        'empréstimos':         '_resp_emprestimos',
        'emprestimos':         '_resp_emprestimos',
        'meus empréstimos':    '_resp_emprestimos',
        'dívidas':             '_resp_emprestimos',
        'dividas':             '_resp_emprestimos',
        'parcelas':            '_resp_emprestimos',
        'quanto devo':         '_resp_emprestimos',
        'devo':                '_resp_emprestimos',
        'empréstimo':          '_resp_emprestimos',
        'emprestimo':          '_resp_emprestimos',

        # Balanço do mês
        'balanço':             '_resp_balanco_mes',
        'balanco':             '_resp_balanco_mes',
        'balanço do mês':      '_resp_balanco_mes',
        'resumo do mês':       '_resp_balanco_mes',
        'resumo mensal':       '_resp_balanco_mes',
        'esse mês':            '_resp_balanco_mes',
        'este mês':            '_resp_balanco_mes',
        'mês atual':           '_resp_balanco_mes',

        # Orçamento
        'orçamento':           '_resp_orcamento',
        'orcamento':           '_resp_orcamento',
        'budget':              '_resp_orcamento',
        'limite de gasto':     '_resp_orcamento',
    }

    # ── Intenções para prompt inteligente ───────────────────
    # Mapeia palavras-chave para o tipo de contexto necessário
    INTENCOES = {
        'previsão':     'previsao',
        'previsao':     'previsao',
        'projeção':     'previsao',
        'projecao':     'previsao',
        'próximo mês':  'previsao',
        'proximo mes':  'previsao',
        'tendência':    'tendencia',
        'tendencia':    'tendencia',
        'crescendo':    'tendencia',
        'aumentando':   'tendencia',
        'comparar':     'comparativo',
        'comparativo':  'comparativo',
        'comparação':   'comparativo',
        'comparacao':   'comparativo',
        'conselho':     'conselho',
        'dica':         'conselho',
        'sugestão':     'conselho',
        'sugestao':     'conselho',
        'como economizar': 'conselho',
        'me ajuda':     'conselho',
        'cortar gastos':'conselho',
    }

    def __init__(self, db_connection, user_id):
        self.db  = db_connection
        self.uid = user_id

    # ── API Principal ────────────────────────────────────────

    def processar(self, texto):
        """
        Processa a mensagem do usuário.

        Fluxo:
        1. Tenta resposta local (zero tokens)
        2. Detecta intenção para montar prompt mínimo
        3. Retorna prompt otimizado para o servidor

        Returns:
            dict:
            - respondido (bool)
            - resposta (str)
            - prompt_servidor (str)
        """
        texto_lower = texto.lower().strip()

        # ── Tentar resposta local ─────────────────────────────
        for padrao, metodo in self.PADROES_LOCAIS.items():
            if padrao in texto_lower:
                try:
                    resposta = getattr(self, metodo)()
                    if resposta:
                        return {
                            'respondido':      True,
                            'resposta':        resposta,
                            'prompt_servidor': ''
                        }
                except Exception as e:
                    print(f"[Agente] Erro local ({metodo}): {e}")

        # ── Detectar intenção e montar prompt mínimo ──────────
        intencao = self._detectar_intencao(texto_lower)
        prompt   = self._montar_prompt_minimo(texto, intencao)

        return {
            'respondido':      False,
            'resposta':        '',
            'prompt_servidor': prompt
        }

    # ── Detecção de Intenção ─────────────────────────────────

    def _detectar_intencao(self, texto_lower: str) -> str:
        """
        Detecta a intenção da pergunta para coletar
        apenas os dados necessários.
        """
        for padrao, intencao in self.INTENCOES.items():
            if padrao in texto_lower:
                return intencao
        return 'geral'

    # ── Coleta de Dados SELETIVA ─────────────────────────────

    def _coletar_saldo(self) -> dict:
        """Coleta apenas dados de saldo — mínimo de queries"""
        try:
            rows = self.db.execute(
                """SELECT transaction_type, SUM(amount) as total
                   FROM transactions WHERE user_id = ?
                   GROUP BY transaction_type""",
                (self.uid,)
            ).fetchall()

            entradas = saidas = 0
            for r in rows:
                if r['transaction_type'] == 'entrada':
                    entradas = r['total'] or 0
                else:
                    saidas = r['total'] or 0

            saldo = entradas - saidas

            guardado = self.db.execute(
                """SELECT COALESCE(SUM(current_amount), 0) as total
                   FROM savings_goals WHERE user_id = ?""",
                (self.uid,)
            ).fetchone()['total']

            return {
                'entradas':  entradas,
                'saidas':    saidas,
                'saldo':     saldo,
                'guardado':  guardado,
                'disponivel': saldo - guardado
            }
        except Exception as e:
            print(f"[Agente] Erro _coletar_saldo: {e}")
            return {
                'entradas': 0, 'saidas': 0,
                'saldo': 0, 'guardado': 0, 'disponivel': 0
            }

    def _coletar_mes_atual(self) -> dict:
        """Coleta resumo do mês atual — 2 queries"""
        hoje     = datetime.now()
        ini_mes  = hoje.replace(day=1).strftime('%Y-%m-%d')
        fim_mes  = hoje.strftime('%Y-%m-%d')

        try:
            # Entradas e saídas do mês
            rows = self.db.execute(
                """SELECT transaction_type, SUM(amount) as total
                   FROM transactions
                   WHERE user_id = ?
                   AND date BETWEEN ? AND ?
                   GROUP BY transaction_type""",
                (self.uid, ini_mes, fim_mes)
            ).fetchall()

            entradas = saidas = 0
            for r in rows:
                if r['transaction_type'] == 'entrada':
                    entradas = r['total'] or 0
                else:
                    saidas = r['total'] or 0

            # Top 3 categorias de gasto do mês
            cats = self.db.execute(
                """SELECT c.name, SUM(t.amount) as total
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   GROUP BY c.name
                   ORDER BY total DESC
                   LIMIT 3""",
                (self.uid, ini_mes, fim_mes)
            ).fetchall()

            return {
                'entradas':   entradas,
                'saidas':     saidas,
                'saldo':      entradas - saidas,
                'categorias': [
                    {
                        'nome':  r['name'] or 'Sem categoria',
                        'total': r['total']
                    }
                    for r in cats
                ],
                'inicio': ini_mes,
                'fim':    fim_mes,
            }
        except Exception as e:
            print(f"[Agente] Erro _coletar_mes_atual: {e}")
            return {
                'entradas': 0, 'saidas': 0,
                'saldo': 0, 'categorias': []
            }

    def _coletar_categorias_mes(self) -> list:
        """Coleta todas categorias com gastos do mês — 1 query"""
        hoje    = datetime.now()
        ini_mes = hoje.replace(day=1).strftime('%Y-%m-%d')
        fim_mes = hoje.strftime('%Y-%m-%d')

        try:
            rows = self.db.execute(
                """SELECT c.name, SUM(t.amount) as total
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   GROUP BY c.name
                   ORDER BY total DESC""",
                (self.uid, ini_mes, fim_mes)
            ).fetchall()

            return [
                {
                    'nome':  r['name'] or 'Sem categoria',
                    'total': r['total']
                }
                for r in rows
            ]
        except Exception as e:
            print(f"[Agente] Erro _coletar_categorias_mes: {e}")
            return []

    def _coletar_recentes(self, limite: int = 8) -> list:
        """Coleta transações recentes — 1 query"""
        try:
            rows = self.db.execute(
                """SELECT t.amount, t.description,
                          t.transaction_type, t.date,
                          c.name as categoria
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   ORDER BY t.date DESC, t.id DESC
                   LIMIT ?""",
                (self.uid, limite)
            ).fetchall()

            return [
                {
                    'valor':     r['amount'],
                    'descricao': r['description'],
                    'tipo':      r['transaction_type'],
                    'data':      r['date'],
                    'categoria': r['categoria'],
                }
                for r in rows
            ]
        except Exception as e:
            print(f"[Agente] Erro _coletar_recentes: {e}")
            return []

    def _coletar_metas(self) -> list:
        """Coleta metas de economia — 1 query"""
        try:
            rows = self.db.execute(
                """SELECT name, target_amount,
                          current_amount, deadline
                   FROM savings_goals
                   WHERE user_id = ?
                   ORDER BY deadline""",
                (self.uid,)
            ).fetchall()

            return [
                {
                    'nome':   r['name'],
                    'meta':   r['target_amount'],
                    'atual':  r['current_amount'],
                    'pct':    (
                        r['current_amount'] /
                        r['target_amount'] * 100
                        if r['target_amount'] > 0 else 0
                    ),
                    'prazo':  r['deadline'],
                    'falta':  r['target_amount'] - r['current_amount']
                }
                for r in rows
            ]
        except Exception as e:
            print(f"[Agente] Erro _coletar_metas: {e}")
            return []

    def _coletar_emprestimos(self) -> list:
        """Coleta empréstimos ativos — 1 query"""
        try:
            tabela_existe = self.db.execute(
                """SELECT COUNT(*) FROM sqlite_master
                   WHERE type='table' AND name='loans'"""
            ).fetchone()[0] > 0

            if not tabela_existe:
                return []

            rows = self.db.execute(
                """SELECT l.name, l.final_amount,
                          l.installment_amount,
                          l.num_installments, l.status,
                          COALESCE(
                              (SELECT SUM(lp.amount)
                               FROM loan_payments lp
                               WHERE lp.loan_id = l.id),
                              0
                          ) as total_pago
                   FROM loans l
                   WHERE l.user_id = ?
                   ORDER BY l.status ASC, l.name ASC""",
                (self.uid,)
            ).fetchall()

            return [
                {
                    'nome':       r['name'],
                    'total':      r['final_amount'],
                    'pago':       r['total_pago'],
                    'restante':   r['final_amount'] - r['total_pago'],
                    'parcela':    r['installment_amount'],
                    'status':     r['status'],
                    'pct':        (
                        r['total_pago'] /
                        r['final_amount'] * 100
                        if r['final_amount'] > 0 else 0
                    ),
                }
                for r in rows
            ]
        except Exception as e:
            print(f"[Agente] Erro _coletar_emprestimos: {e}")
            return []

    def _coletar_orcamento_mes(self) -> list:
        """Coleta orçamentos do mês atual — 1 query"""
        hoje = datetime.now()
        try:
            rows = self.db.execute(
                """SELECT cb.amount as orcado,
                          c.name,
                          COALESCE(
                              (SELECT SUM(t.amount)
                               FROM transactions t
                               WHERE t.user_id = cb.user_id
                               AND t.category_id = cb.category_id
                               AND t.transaction_type = 'saida'
                               AND strftime('%Y-%m', t.date) = ?),
                              0
                          ) as gasto
                   FROM category_budgets cb
                   JOIN categories c ON cb.category_id = c.id
                   WHERE cb.user_id = ?
                   AND cb.month = ?
                   AND cb.year = ?""",
                (
                    hoje.strftime('%Y-%m'),
                    self.uid,
                    hoje.month,
                    hoje.year
                )
            ).fetchall()

            return [
                {
                    'nome':     r['name'],
                    'orcado':   r['orcado'],
                    'gasto':    r['gasto'],
                    'restante': r['orcado'] - r['gasto'],
                    'pct':      (
                        r['gasto'] / r['orcado'] * 100
                        if r['orcado'] > 0 else 0
                    ),
                }
                for r in rows
            ]
        except Exception as e:
            print(f"[Agente] Erro _coletar_orcamento_mes: {e}")
            return []

    def _coletar_historico_mensal(self, meses: int = 3) -> list:
        """
        Coleta histórico de N meses para previsão/tendência.
        1 query apenas.
        """
        try:
            hoje = datetime.now()
            inicio = (
                hoje.replace(day=1) -
                timedelta(days=meses * 31)
            ).strftime('%Y-%m-%d')

            rows = self.db.execute(
                """SELECT strftime('%Y-%m', date) as mes,
                          SUM(CASE WHEN transaction_type='entrada'
                              THEN amount ELSE 0 END) as entradas,
                          SUM(CASE WHEN transaction_type='saida'
                              THEN amount ELSE 0 END) as saidas
                   FROM transactions
                   WHERE user_id = ? AND date >= ?
                   GROUP BY mes
                   ORDER BY mes""",
                (self.uid, inicio)
            ).fetchall()

            return [
                {
                    'mes':      r['mes'],
                    'entradas': r['entradas'],
                    'saidas':   r['saidas'],
                    'saldo':    r['entradas'] - r['saidas']
                }
                for r in rows
            ]
        except Exception as e:
            print(f"[Agente] Erro _coletar_historico: {e}")
            return []

    # ── Respostas Locais (zero tokens) ───────────────────────

    def _resp_saldo(self):
        """Responde sobre saldo — sem servidor"""
        s = self._coletar_saldo()
        m = self._coletar_mes_atual()

        r  = "💰 **Resumo Financeiro**\n\n"
        r += f"• Saldo total: **R$ {s['saldo']:,.2f}**\n"

        if s['guardado'] > 0:
            r += f"• Guardado em metas: R$ {s['guardado']:,.2f}\n"
            r += f"• **Disponível: R$ {s['disponivel']:,.2f}**\n"

        if m['entradas'] > 0 or m['saidas'] > 0:
            r += f"\n📅 **Este mês:**\n"
            r += f"• Receitas:  R$ {m['entradas']:,.2f}\n"
            r += f"• Despesas:  R$ {m['saidas']:,.2f}\n"
            saldo_mes = m['saldo']
            emoji = "✅" if saldo_mes >= 0 else "⚠️"
            r += f"• Saldo mês: {emoji} R$ {saldo_mes:,.2f}\n"

        return r

    def _resp_recentes(self):
        """Lista transações recentes — sem servidor"""
        trans = self._coletar_recentes(8)

        if not trans:
            return "Não há transações registradas ainda."

        r = "📋 **Últimas Transações:**\n\n"
        for t in trans:
            emoji = "💚" if t['tipo'] == 'entrada' else "🔴"
            r += f"{emoji} {t['data']} | **R$ {t['valor']:,.2f}**"
            r += f" | {t['descricao']}"
            if t['categoria']:
                r += f" _{t['categoria']}_"
            r += "\n"

        return r

    def _resp_metas(self):
        """Lista metas de economia — sem servidor"""
        metas = self._coletar_metas()

        if not metas:
            return (
                "Você não tem metas de economia cadastradas.\n\n"
                "💡 Crie metas em **Metas de Economia** "
                "no menu principal."
            )

        r = "🎯 **Metas de Economia:**\n\n"
        for m in metas:
            barra = self._barra(m['pct'])
            r += f"**{m['nome']}**\n"
            r += f"{barra} {m['pct']:.0f}%\n"
            r += (
                f"R$ {m['atual']:,.2f} de R$ {m['meta']:,.2f} | "
                f"Falta: R$ {m['falta']:,.2f}\n"
            )
            if m['prazo']:
                try:
                    dias = (
                        datetime.strptime(m['prazo'], '%Y-%m-%d') -
                        datetime.now()
                    ).days
                    if dias > 0:
                        r += f"📅 {dias} dias restantes\n"
                    else:
                        r += f"⚠️ Prazo expirado há {abs(dias)} dias\n"
                except Exception:
                    pass
            r += "\n"

        return r

    def _resp_categorias(self):
        """Mostra gastos por categoria — sem servidor"""
        cats = self._coletar_categorias_mes()

        if not cats:
            return (
                "Sem gastos por categoria este mês.\n\n"
                "💡 Crie categorias no menu principal para "
                "organizar seus gastos!"
            )

        total = sum(c['total'] for c in cats)
        hoje  = datetime.now()
        r = (
            f"📊 **Gastos por Categoria "
            f"({hoje.strftime('%B/%Y').capitalize()}):**\n\n"
        )

        for c in cats:
            pct = (c['total'] / total * 100) if total > 0 else 0
            r += (
                f"• **{c['nome']}**: "
                f"R$ {c['total']:,.2f} ({pct:.1f}%)\n"
            )

        r += f"\n💸 **Total: R$ {total:,.2f}**"
        return r

    def _resp_maiores(self):
        """Lista maiores gastos do mês — sem servidor"""
        hoje    = datetime.now()
        ini_mes = hoje.replace(day=1).strftime('%Y-%m-%d')
        fim_mes = hoje.strftime('%Y-%m-%d')

        try:
            rows = self.db.execute(
                """SELECT t.amount, t.description,
                          t.date, c.name as categoria
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   ORDER BY t.amount DESC
                   LIMIT 5""",
                (self.uid, ini_mes, fim_mes)
            ).fetchall()

            if not rows:
                return "Sem despesas registradas este mês."

            r = "💸 **Maiores Gastos do Mês:**\n\n"
            for i, t in enumerate(rows, 1):
                r += f"{i}. **R$ {t['amount']:,.2f}** — {t['description']}"
                if t['categoria']:
                    r += f" _({t['categoria']})_"
                r += f" | {t['date']}\n"

            return r

        except Exception as e:
            return f"Erro ao buscar maiores gastos: {e}"

    def _resp_emprestimos(self):
        """Responde sobre empréstimos — sem servidor"""
        loans = self._coletar_emprestimos()

        if not loans:
            return (
                "Você não possui empréstimos cadastrados.\n\n"
                "💡 Use **💳 Empréstimos** no menu principal."
            )

        ativos   = [l for l in loans if l['status'] == 'ativo']
        quitados = [l for l in loans if l['status'] == 'quitado']

        r = "💳 **Resumo de Empréstimos**\n\n"

        if ativos:
            total_divida = sum(l['restante'] for l in ativos)
            r += f"🔄 **Em andamento ({len(ativos)}):**\n"

            for loan in ativos:
                barra = self._barra(loan['pct'])
                r += f"\n• **{loan['nome']}**\n"
                r += f"  {barra} {loan['pct']:.0f}%\n"
                r += (
                    f"  Pago: R$ {loan['pago']:,.2f} / "
                    f"R$ {loan['total']:,.2f}\n"
                )
                r += f"  Restante: R$ {loan['restante']:,.2f}\n"
                r += f"  Parcela : R$ {loan['parcela']:,.2f}\n"

            r += (
                f"\n💰 **Total em dívidas: "
                f"R$ {total_divida:,.2f}**\n"
            )

        if quitados:
            r += f"\n✅ **Quitados ({len(quitados)}):**\n"
            for loan in quitados:
                r += (
                    f"• {loan['nome']} — "
                    f"R$ {loan['total']:,.2f}\n"
                )

        return r

    def _resp_balanco_mes(self):
        """Responde sobre balanço do mês atual — sem servidor"""
        m    = self._coletar_mes_atual()
        hoje = datetime.now()

        r  = (
            f"📊 **Balanço de "
            f"{hoje.strftime('%B/%Y').capitalize()}:**\n\n"
        )
        r += f"• Receitas:  R$ {m['entradas']:,.2f}\n"
        r += f"• Despesas:  R$ {m['saidas']:,.2f}\n"

        saldo = m['saldo']
        emoji = "✅" if saldo >= 0 else "⚠️"
        r += f"• Saldo:     {emoji} **R$ {saldo:,.2f}**\n"

        if m['categorias']:
            r += "\n🏷️ **Principais categorias de gasto:**\n"
            for c in m['categorias']:
                r += f"• {c['nome']}: R$ {c['total']:,.2f}\n"

        return r

    def _resp_orcamento(self):
        """Responde sobre orçamento do mês — sem servidor"""
        orcamentos = self._coletar_orcamento_mes()

        if not orcamentos:
            return (
                "Não há orçamentos definidos para este mês.\n\n"
                "💡 Configure em **Orçamento Mensal** "
                "no menu principal."
            )

        hoje       = datetime.now()
        dias_mes   = 30
        dias_pass  = hoje.day
        pct_mes    = (dias_pass / dias_mes) * 100

        r = (
            f"📋 **Orçamento de "
            f"{hoje.strftime('%B/%Y').capitalize()}:**\n"
            f"_(Mês {pct_mes:.0f}% concluído)_\n\n"
        )

        total_orc  = total_gasto = 0
        for o in orcamentos:
            total_orc   += o['orcado']
            total_gasto += o['gasto']
            status = (
                "🔴 ACIMA"    if o['pct'] > pct_mes + 10 else
                "✅ OK"       if o['pct'] <= pct_mes + 10 else
                "🟡 ATENÇÃO"
            )
            r += (
                f"• **{o['nome']}**: "
                f"R$ {o['gasto']:,.2f} / R$ {o['orcado']:,.2f} "
                f"({o['pct']:.0f}%) {status}\n"
            )

        pct_total = (
            total_gasto / total_orc * 100
            if total_orc > 0 else 0
        )
        r += (
            f"\n**Total: R$ {total_gasto:,.2f} / "
            f"R$ {total_orc:,.2f} ({pct_total:.0f}%)**"
        )
        return r

    # ── Prompt Mínimo e Inteligente ──────────────────────────

    def _montar_prompt_minimo(
        self,
        pergunta: str,
        intencao: str
    ) -> str:
        """
        Monta prompt com APENAS os dados necessários
        para a intenção detectada.

        Princípio: mínimo de tokens, máximo de precisão.
        """
        hoje = datetime.now()

        # ── Sistema (fixo e compacto) ─────────────────────────
        sistema = (
            "Assistente financeiro pessoal. "
            "REGRAS: responda em português brasileiro, "
            "use APENAS os dados fornecidos, "
            "seja objetivo e direto, "
            "se dado não existir diga claramente, "
            "use bullets e negrito para clareza."
        )

        # ── Contexto base (sempre presente, mínimo) ───────────
        s = self._coletar_saldo()
        ctx  = f"DATA: {hoje.strftime('%d/%m/%Y')}\n"
        ctx += (
            f"SALDO: R$ {s['saldo']:,.2f} | "
            f"DISPONÍVEL: R$ {s['disponivel']:,.2f}\n"
        )

        # ── Dados específicos por intenção ────────────────────
        if intencao == 'previsao':
            historico = self._coletar_historico_mensal(3)
            if historico:
                ctx += "\nHISTÓRICO 3 MESES:\n"
                for h in historico:
                    ctx += (
                        f"- {h['mes']}: "
                        f"Receita R$ {h['entradas']:,.2f} | "
                        f"Despesa R$ {h['saidas']:,.2f} | "
                        f"Saldo R$ {h['saldo']:,.2f}\n"
                    )

        elif intencao == 'tendencia':
            historico = self._coletar_historico_mensal(6)
            cats      = self._coletar_categorias_mes()
            if historico:
                ctx += "\nHISTÓRICO 6 MESES:\n"
                for h in historico:
                    ctx += (
                        f"- {h['mes']}: "
                        f"Despesa R$ {h['saidas']:,.2f}\n"
                    )
            if cats:
                ctx += "\nCATEGORIAS MÊS ATUAL:\n"
                for c in cats[:5]:
                    ctx += (
                        f"- {c['nome']}: "
                        f"R$ {c['total']:,.2f}\n"
                    )

        elif intencao == 'comparativo':
            cats = self._coletar_categorias_mes()
            if cats:
                total = sum(c['total'] for c in cats)
                ctx  += "\nGASTOS POR CATEGORIA (mês atual):\n"
                for c in cats:
                    pct = (
                        c['total'] / total * 100
                        if total > 0 else 0
                    )
                    ctx += (
                        f"- {c['nome']}: "
                        f"R$ {c['total']:,.2f} ({pct:.1f}%)\n"
                    )

        elif intencao == 'conselho':
            # Para conselhos: saldo + mês + categorias + metas
            m    = self._coletar_mes_atual()
            cats = self._coletar_categorias_mes()
            metas = self._coletar_metas()

            ctx += (
                f"\nMÊS ATUAL: "
                f"Receita R$ {m['entradas']:,.2f} | "
                f"Despesa R$ {m['saidas']:,.2f} | "
                f"Saldo R$ {m['saldo']:,.2f}\n"
            )

            if cats:
                ctx += "\nCATEGORIAS:\n"
                for c in cats[:5]:
                    ctx += (
                        f"- {c['nome']}: "
                        f"R$ {c['total']:,.2f}\n"
                    )

            if metas:
                ctx += "\nMETAS:\n"
                for m in metas:
                    ctx += (
                        f"- {m['nome']}: "
                        f"{m['pct']:.0f}% | "
                        f"Falta R$ {m['falta']:,.2f}\n"
                    )

        else:
            # 'geral' — mês atual + categorias top 3
            m = self._coletar_mes_atual()
            ctx += (
                f"\nMÊS ATUAL: "
                f"Receita R$ {m['entradas']:,.2f} | "
                f"Despesa R$ {m['saidas']:,.2f} | "
                f"Saldo R$ {m['saldo']:,.2f}\n"
            )
            if m['categorias']:
                ctx += "TOP CATEGORIAS:\n"
                for c in m['categorias']:
                    ctx += (
                        f"- {c['nome']}: "
                        f"R$ {c['total']:,.2f}\n"
                    )

        # ── Prompt final compacto ─────────────────────────────
        return (
            f"{sistema}\n\n"
            f"DADOS FINANCEIROS:\n{ctx}\n"
            f"PERGUNTA: {pergunta}\n\n"
            f"Responda com base EXCLUSIVAMENTE nos dados acima."
        )

    # ── Utilitários ──────────────────────────────────────────

    def _barra(self, pct: float) -> str:
        """Barra de progresso visual compacta"""
        pct    = max(0, min(100, pct))
        filled = int(pct / 10)
        empty  = 10 - filled
        return f"[{'█' * filled}{'░' * empty}]"


# ============================================================
# CHAT MESSAGE
# ============================================================

class ChatMessage:
    """Representa uma mensagem no chat"""

    def __init__(self, text, is_user=True):
        self.text      = text
        self.is_user   = is_user
        self.timestamp = datetime.now()

    def formatted_html(self, dark_mode=False):
        """Retorna a mensagem formatada em HTML"""
        timestamp = self.timestamp.strftime("%H:%M:%S")

        if dark_mode:
            user_style = (
                "background-color: #2c3e50; color: #ecf0f1; "
                "border-radius: 10px; padding: 10px; "
                "margin: 5px 0; margin-left: 20%;"
            )
            ai_style = (
                "background-color: #34495e; color: #ecf0f1; "
                "border-radius: 10px; padding: 10px; "
                "margin: 5px 0; margin-right: 20%;"
            )
            time_style = (
                "color: #7f8c8d; font-size: 10px; "
                "text-align: right; margin-top: 2px;"
            )
        else:
            user_style = (
                "background-color: #e3f2fd; color: #0d47a1; "
                "border-radius: 10px; padding: 10px; "
                "margin: 5px 0; margin-left: 20%;"
            )
            ai_style = (
                "background-color: #f1f8e9; color: #33691e; "
                "border-radius: 10px; padding: 10px; "
                "margin: 5px 0; margin-right: 20%;"
            )
            time_style = (
                "color: #757575; font-size: 10px; "
                "text-align: right; margin-top: 2px;"
            )

        style = user_style if self.is_user else ai_style
        align = "right"    if self.is_user else "left"
        name  = "Você"     if self.is_user else "Assistente IA"

        return f"""
        <div style="text-align: {align};">
            <div style="{style}">
                <div><b>{name}</b></div>
                <div style="white-space: pre-wrap;">{self.text}</div>
                <div style="{time_style}">{timestamp}</div>
            </div>
        </div>
        """


# ============================================================
# THREAD DE COMUNICAÇÃO COM O SERVIDOR
# ============================================================

class AIAssistantThread(QThread):

    update_signal   = pyqtSignal(str)
    finished_signal = pyqtSignal()
    error_signal    = pyqtSignal(str)

    def __init__(self, api_key, prompt, parent=None):
        super().__init__(parent)
        self.api_key  = api_key
        self.prompt   = prompt
        self.running  = True
        self.base_url = None
        self.use_tor  = False
        self.session  = requests.Session()  # ← adicionar aqui também

    # ✅ CORRETO: _detect_network como método da CLASSE
    #    (mesmo nível de indentação que __init__ e run)
    def _detect_network(self):
        """
        Detecta automaticamente qual rede usar.
        Usa o tor_manager do app (sem instalar Tor externo).
        """
        import socket

        # ── 1. Rede local ─────────────────────────────────────
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((LOCAL_IP, LOCAL_PORT))
            s.close()
            self.base_url = LOCAL_URL
            self.use_tor  = False
            return True
        except (socket.timeout, socket.error, OSError):
            pass

        # ── 2. Tor via tor_manager ────────────────────────────
        try:
            from modulos.tor_manager import (
                obter_proxy_url,
                status_tor,
                iniciar_tor
            )

            st = status_tor()

            if st['socks_ok'] and st['bootstrap_ok']:
                proxy_url = obter_proxy_url()
                self.base_url = ONION_URL
                self.use_tor  = True
                self.session.proxies = {
                    'http':  proxy_url,
                    'https': proxy_url
                }
                return True

            sucesso, msg = iniciar_tor()
            if sucesso:
                proxy_url = obter_proxy_url()
                self.base_url = ONION_URL
                self.use_tor  = True
                self.session.proxies = {
                    'http':  proxy_url,
                    'https': proxy_url
                }
                return True

        except ImportError:
            pass
        except Exception as e:
            print(f"[AIThread] Erro Tor: {e}")

        return False

    def run(self):
        """Executa a consulta ao servidor de IA"""
        try:
            if not self._detect_network():
                self.error_signal.emit(
                    "Sem conexão disponível.\n"
                    "Verifique a rede local ou o serviço Tor."
                )
                self.finished_signal.emit()
                return

            session        = requests.Session()
            session.verify = False

            if self.use_tor:
                session.proxies = {
                    'http':  'socks5h://localhost:9050',
                    'https': 'socks5h://localhost:9050'
                }

            headers = {
                'Content-Type': 'application/json',
                'X-API-Key':    self.api_key
            }

            payload = {"prompt": self.prompt}

            response = session.post(
                f"{self.base_url}/api/servico/prompt",
                headers=headers,
                json=payload,
                timeout=None,
                verify=False
            )
            response.raise_for_status()

            dados    = response.json()
            resposta = dados.get("resposta", "")

            if resposta:
                self.update_signal.emit(resposta)

            self.finished_signal.emit()

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            if status == 401:
                self.error_signal.emit(
                    "API Key inválida.\n"
                    "Verifique sua chave em ⚙️ Configurações."
                )
            elif status == 404:
                self.error_signal.emit(
                    "Rota não encontrada no servidor."
                )
            else:
                self.error_signal.emit(f"Erro HTTP {status}: {str(e)}")
            self.finished_signal.emit()

        except requests.exceptions.ConnectionError:
            self.error_signal.emit(
                "Não foi possível conectar ao servidor."
            )
            self.finished_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))
            self.finished_signal.emit()

    def stop(self):
        """Para a thread"""
        self.running = False


# ============================================================
# WIDGET PRINCIPAL DO ASSISTENTE
# ============================================================

class AIAssistantWidget(QWidget):
    """
    Widget principal do Assistente Financeiro IA.

    Fluxo inteligente:
    1. Agente local responde perguntas simples (instantâneo)
    2. Perguntas complexas → servidor com prompt otimizado
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.is_dark_mode  = (
            parent.is_dark_mode if hasattr(parent, 'is_dark_mode') else False
        )
        self.messages   = []
        self.api_thread = None
        self.api_key    = None
        self.agente     = None

        self._load_api_key()
        self._init_agente()
        self.init_ui()
        self._show_welcome()

    # ── Inicialização ────────────────────────────────────────

    def _load_api_key(self):
        """Carrega a API Key do banco de dados"""
        if not (
            hasattr(self.parent_window, 'db_connection') and
            hasattr(self.parent_window, 'user_id')
        ):
            return
        try:
            row = self.parent_window.db_connection.execute(
                """SELECT setting_value FROM user_settings
                   WHERE user_id = ? AND setting_key = 'ai_api_key'""",
                (self.parent_window.user_id,)
            ).fetchone()
            if row:
                self.api_key = row[0]
        except Exception as e:
            print(f"[AIWidget] Erro ao carregar API Key: {e}")

    def _init_agente(self):
        """Inicializa o agente financeiro local"""
        if (
            hasattr(self.parent_window, 'db_connection') and
            hasattr(self.parent_window, 'user_id')
        ):
            try:
                self.agente = AgenteFinanceiroLocal(
                    self.parent_window.db_connection,
                    self.parent_window.user_id
                )
            except Exception as e:
                print(f"[AIWidget] Erro ao iniciar agente: {e}")

    def _show_welcome(self):
        """Exibe a mensagem de boas-vindas"""
        if self.api_key:
            welcome = (
                "Olá! Sou seu assistente financeiro pessoal. 💰\n\n"
                "Respostas instantâneas (sem servidor):\n"
                "• 'meu saldo' ou 'quanto tenho'\n"
                "• 'transações recentes'\n"
                "• 'minhas metas'\n"
                "• 'gastos por categoria'\n"
                "• 'maiores gastos'\n\n"
                "Análises avançadas (via servidor de IA):\n"
                "• Conselhos personalizados\n"
                "• Previsões e tendências\n"
                "• Comparativos e análises\n\n"
                "Como posso ajudar?"
            )
        else:
            welcome = (
                "Olá! 👋\n\n"
                "⚠️ API Key não configurada.\n\n"
                "Posso responder instantaneamente:\n"
                "• 'meu saldo'\n"
                "• 'transações recentes'\n"
                "• 'minhas metas'\n"
                "• 'gastos por categoria'\n\n"
                "Para análises avançadas, configure "
                "a API Key em ⚙️."
            )
        self.add_message(welcome, is_user=False)

    def init_ui(self):
        """Inicializa a interface"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Cabeçalho ────────────────────────────────────────
        header_layout = QHBoxLayout()

        self.status_indicator = QLabel("●")
        self.status_indicator.setFixedWidth(20)

        title_label = QLabel("Assistente Financeiro IA")
        title_label.setStyleSheet(
            "font-size: 15px; font-weight: bold;"
        )

        self.network_label = QLabel("")
        self.network_label.setStyleSheet(
            "font-size: 11px; color: gray;"
        )

        config_button = QPushButton("⚙️")
        config_button.setToolTip("Configurar API Key")
        config_button.setFixedSize(32, 32)
        config_button.clicked.connect(self.show_config_dialog)

        header_layout.addWidget(self.status_indicator)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.network_label)
        header_layout.addWidget(config_button)
        layout.addLayout(header_layout)

        # ── Chat ─────────────────────────────────────────────
        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        self.chat_area.setMinimumHeight(300)

        # ── Input ────────────────────────────────────────────
        self.input_area = QTextEdit()
        self.input_area.setPlaceholderText(
            "Digite sua pergunta... (Ctrl+Enter para enviar)"
        )
        self.input_area.setMaximumHeight(90)
        self.input_area.setAcceptRichText(False)

        # ── Botões ───────────────────────────────────────────
        self.send_button = QPushButton("➤ Enviar")
        self.send_button.clicked.connect(self.send_message)
        self.send_button.setFixedHeight(36)

        self.clear_button = QPushButton("🗑 Limpar")
        self.clear_button.clicked.connect(self.clear_chat)
        self.clear_button.setFixedHeight(36)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.input_area)
        shortcut.activated.connect(self.send_message)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.clear_button)
        button_layout.addStretch()
        button_layout.addWidget(self.send_button)

        layout.addWidget(self.chat_area, 1)
        layout.addWidget(self.input_area, 0)
        layout.addLayout(button_layout)

        self._update_status_indicator()
        self.apply_theme()

    # ── Tema ─────────────────────────────────────────────────

    def apply_theme(self):
        """Aplica o tema ao widget"""
        if self.is_dark_mode:
            self.setStyleSheet("""
                QWidget {
                    background-color: #1e272e;
                    color: #ecf0f1;
                }
                QTextEdit {
                    background-color: #2d3436;
                    color: #ecf0f1;
                    border: 1px solid #4b6584;
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 13px;
                }
                QPushButton {
                    background-color: #3498db;
                    color: #ecf0f1;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 14px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #2980b9; }
                QPushButton:disabled {
                    background-color: #4b6584;
                    color: #7f8c8d;
                }
            """)
            self.send_button.setStyleSheet(
                "background-color: #2ecc71; color: #1e272e; "
                "font-weight: bold; border-radius: 4px;"
            )
            self.clear_button.setStyleSheet(
                "background-color: #e74c3c; color: #ecf0f1; "
                "border-radius: 4px;"
            )
        else:
            self.setStyleSheet("""
                QTextEdit {
                    background-color: white;
                    color: #333333;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 8px;
                    font-size: 13px;
                }
                QPushButton {
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    padding: 6px 14px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #45a049; }
                QPushButton:disabled {
                    background-color: #ccc;
                    color: #999;
                }
            """)
            self.send_button.setStyleSheet(
                "background-color: #4CAF50; color: white; "
                "font-weight: bold; border-radius: 4px;"
            )
            self.clear_button.setStyleSheet(
                "background-color: #f44336; color: white; "
                "border-radius: 4px;"
            )

    # ── Status ───────────────────────────────────────────────

    def _update_status_indicator(self):
        """Atualiza o indicador de status"""
        if self.api_key:
            self.status_indicator.setStyleSheet(
                "color: green; font-size: 18px;"
            )
            self.status_indicator.setToolTip("API Key configurada")
        else:
            self.status_indicator.setStyleSheet(
                "color: orange; font-size: 18px;"
            )
            self.status_indicator.setToolTip(
                "API Key não configurada - modo básico"
            )

    def _set_network_label(self, source):
        """
        Atualiza label de rede.
        source: 'local', 'tor' ou 'local_agent'
        """
        if source == 'local_agent':
            self.network_label.setText("⚡ Local")
            self.network_label.setStyleSheet(
                "font-size: 11px; color: #f39c12;"
            )
        elif source == 'tor':
            self.network_label.setText("🧅 Tor")
            self.network_label.setStyleSheet(
                "font-size: 11px; color: #9b59b6;"
            )
        else:
            self.network_label.setText("🏠 Rede Local")
            self.network_label.setStyleSheet(
                "font-size: 11px; color: #27ae60;"
            )

    # ── Configuração ─────────────────────────────────────────

    def show_config_dialog(self):
        """Mostra o diálogo de configuração"""
        dialog = ApiConfigDialog(self.parent_window)
        if dialog.exec_() == QDialog.Accepted:
            self._load_api_key()
            self._update_status_indicator()
            self.messages = []
            self._show_welcome()

    # ── Chat ─────────────────────────────────────────────────

    def add_message(self, text, is_user=True):
        """Adiciona mensagem ao chat"""
        self.messages.append(ChatMessage(text, is_user))
        self._update_chat_view()

    def _update_chat_view(self):
        """Atualiza a visualização do chat"""
        scrollbar     = self.chat_area.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= scrollbar.maximum() - 10

        html = "".join(
            msg.formatted_html(self.is_dark_mode)
            for msg in self.messages
        )
        self.chat_area.setHtml(html)

        if was_at_bottom:
            QTimer.singleShot(
                0, lambda: scrollbar.setValue(scrollbar.maximum())
            )

    def send_message(self):
        """
        Envia mensagem com fluxo inteligente:
        1. Agente local tenta responder
        2. Se não → servidor com prompt otimizado
        """
        text = self.input_area.toPlainText().strip()
        if not text:
            return

        self.add_message(text, is_user=True)
        self.input_area.clear()

        # Tentar agente local
        if self.agente:
            try:
                resultado = self.agente.processar(text)

                if resultado['respondido']:
                    self._set_network_label('local_agent')
                    self.add_message(
                        resultado['resposta'], is_user=False
                    )
                    return

                prompt_servidor = resultado['prompt_servidor']

            except Exception as e:
                print(f"[AIWidget] Erro no agente: {e}")
                prompt_servidor = text
        else:
            prompt_servidor = text

        # Verificar API Key
        if not self.api_key:
            self.add_message(
                "⚠️ Configure a API Key em ⚙️ para análises avançadas.\n\n"
                "Para consultas básicas tente:\n"
                "• 'meu saldo'\n"
                "• 'transações recentes'\n"
                "• 'minhas metas'\n"
                "• 'gastos por categoria'",
                is_user=False
            )
            return

        self.add_message(
            "⏳ Analisando com IA...", is_user=False
        )

        if self.api_thread and self.api_thread.isRunning():
            self.api_thread.stop()
            self.api_thread.wait()

        self.api_thread = AIAssistantThread(
            api_key=self.api_key,
            prompt=prompt_servidor,
            parent=self
        )
        self.api_thread.update_signal.connect(self._update_ai_response)
        self.api_thread.error_signal.connect(self._handle_error)
        self.api_thread.finished_signal.connect(self._request_finished)

        self.send_button.setEnabled(False)
        self.api_thread.start()

        QTimer.singleShot(
            4000,
            lambda: self._set_network_label(
                'tor' if (
                    self.api_thread and self.api_thread.use_tor
                ) else 'local'
            )
        )

    def _update_ai_response(self, text):
        """Atualiza resposta da IA"""
        if self.messages:
            self.messages[-1].text = text
            self._update_chat_view()
            self.chat_area.verticalScrollBar().setValue(
                self.chat_area.verticalScrollBar().maximum()
            )

    def _handle_error(self, error_message):
        """Trata erros"""
        if self.messages:
            self.messages[-1].text = (
                f"❌ Erro:\n{error_message}"
            )
            self._update_chat_view()

    def _request_finished(self):
        """Finaliza requisição"""
        self.send_button.setEnabled(True)
        if self.api_thread:
            self._set_network_label(
                'tor' if self.api_thread.use_tor else 'local'
            )

    def clear_chat(self):
        """Limpa o chat"""
        reply = QMessageBox.question(
            self, "Limpar Chat",
            "Deseja limpar todo o histórico?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.messages = []
            self._show_welcome()
