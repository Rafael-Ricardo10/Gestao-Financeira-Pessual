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
# ENDPOINTS DO SERVIDOR DE IA
# ============================================================

LOCAL_IP   = "10.0.0.254"
LOCAL_PORT = 5010
LOCAL_URL  = f"https://{LOCAL_IP}:{LOCAL_PORT}"

ONION_HOST = "6mr2qs6pulbu55rpwirzjron6ycoaoi73rdg5nbvjt3n5x3goxv2emad.onion"
ONION_PORT = 80
ONION_URL  = f"http://{ONION_HOST}:{ONION_PORT}"


# ============================================================
# AGENTE FINANCEIRO LOCAL - MOTOR DE INTELIGÊNCIA
# ============================================================

class AgenteFinanceiroLocal:
    """
    Agente financeiro local que:
    1. Coleta dados reais do banco de dados
    2. Processa e responde perguntas simples localmente
    3. Prepara contexto rico e preciso para o servidor de IA
    4. Garante que a LLM receba informações corretas e completas
    """

    # Perguntas respondidas localmente (sem servidor)
    PADROES_LOCAIS = {
        # Saldo
        'saldo':              '_resp_saldo',
        'quanto tenho':       '_resp_saldo',
        'meu dinheiro':       '_resp_saldo',
        'situação financeira':'_resp_saldo',
        'quanto sobrou':      '_resp_saldo',
        'disponível':         '_resp_saldo',

        # Transações recentes
        'transações recentes':'_resp_recentes',
        'últimos gastos':     '_resp_recentes',
        'ultimos gastos':     '_resp_recentes',
        'última compra':      '_resp_recentes',
        'ultima compra':      '_resp_recentes',
        'movimentações':      '_resp_recentes',
        'movimentacoes':      '_resp_recentes',

        # Metas
        'minhas metas':       '_resp_metas',
        'metas de economia':  '_resp_metas',
        'poupança':           '_resp_metas',
        'poupanca':           '_resp_metas',
        'economizando':       '_resp_metas',
        'objetivos':          '_resp_metas',

        # Categorias
        'categorias':         '_resp_categorias',
        'gastos por categoria':'_resp_categorias',
        'onde gasto mais':    '_resp_categorias',

        # Maiores gastos
        'maior gasto':        '_resp_maiores',
        'maiores gastos':     '_resp_maiores',
        'mais gastei':        '_resp_maiores',
        'mais caro':          '_resp_maiores',
    }

    def __init__(self, db_connection, user_id):
        self.db  = db_connection
        self.uid = user_id

    # ── API Principal ────────────────────────────────────────

    def processar(self, texto):
        """
        Processa a mensagem do usuário.

        Returns:
            dict com:
            - respondido (bool): se respondeu localmente
            - resposta (str): resposta local se respondido
            - prompt_servidor (str): prompt completo para servidor
        """
        texto_lower = texto.lower().strip()

        # Tentar resposta local
        for padrao, metodo in self.PADROES_LOCAIS.items():
            if padrao in texto_lower:
                try:
                    resposta = getattr(self, metodo)()
                    if resposta:
                        return {
                            'respondido':     True,
                            'resposta':       resposta,
                            'prompt_servidor': ''
                        }
                except Exception as e:
                    print(f"[Agente] Erro local ({metodo}): {e}")

        # Precisa do servidor - montar prompt inteligente
        prompt = self._montar_prompt_servidor(texto)
        return {
            'respondido':     False,
            'resposta':       '',
            'prompt_servidor': prompt
        }

    # ── Coleta de Dados do Banco ─────────────────────────────

    def _coletar_dados_completos(self):
        """
        Coleta todos os dados financeiros do usuário.
        Retorna dicionário estruturado com dados reais.
        """
        dados = {
            'saldo_total':      0,
            'total_entradas':   0,
            'total_saidas':     0,
            'guardado_metas':   0,
            'disponivel':       0,
            'tem_categorias':   False,
            'categorias':       [],
            'metas':            [],
            'resumo_mes':       {},
            'resumo_mes_passado': {},
            'resumo_ano':       {},
            'top_gastos_mes':   [],
            'recentes':         [],
            'total_transacoes': 0,
        }

        try:
            hoje = datetime.now()

            # ── Saldo geral ──────────────────────────────────
            rows = self.db.execute(
                """SELECT transaction_type, SUM(amount) as total
                   FROM transactions WHERE user_id = ?
                   GROUP BY transaction_type""",
                (self.uid,)
            ).fetchall()

            for r in rows:
                if r['transaction_type'] == 'entrada':
                    dados['total_entradas'] = r['total'] or 0
                else:
                    dados['total_saidas'] = r['total'] or 0

            dados['saldo_total'] = (
                dados['total_entradas'] - dados['total_saidas']
            )

            # Total de transações
            dados['total_transacoes'] = self.db.execute(
                "SELECT COUNT(*) as n FROM transactions WHERE user_id = ?",
                (self.uid,)
            ).fetchone()['n']

            # ── Metas de economia ────────────────────────────
            metas = self.db.execute(
                """SELECT name, target_amount, current_amount, deadline
                   FROM savings_goals WHERE user_id = ?
                   ORDER BY deadline""",
                (self.uid,)
            ).fetchall()

            for m in metas:
                pct = (
                    (m['current_amount'] / m['target_amount']) * 100
                    if m['target_amount'] > 0 else 0
                )
                dados['guardado_metas'] += m['current_amount']
                dados['metas'].append({
                    'nome':    m['name'],
                    'meta':    m['target_amount'],
                    'atual':   m['current_amount'],
                    'pct':     pct,
                    'prazo':   m['deadline'],
                })

            dados['disponivel'] = (
                dados['saldo_total'] - dados['guardado_metas']
            )

            # ── Categorias ───────────────────────────────────
            categorias = self.db.execute(
                """SELECT id, name FROM categories
                   WHERE user_id = ?
                   AND (is_hidden = 0 OR is_hidden IS NULL)
                   ORDER BY name""",
                (self.uid,)
            ).fetchall()

            dados['tem_categorias'] = len(categorias) > 0

            # ── Resumo mês atual ─────────────────────────────
            ini_mes = hoje.replace(day=1).strftime('%Y-%m-%d')
            fim_mes = hoje.strftime('%Y-%m-%d')
            dados['resumo_mes'] = self._resumo_periodo(
                ini_mes, fim_mes, "mês atual"
            )

            # ── Resumo mês passado ───────────────────────────
            primeiro_mes = hoje.replace(day=1)
            ultimo_mes_p = primeiro_mes - timedelta(days=1)
            ini_mp = ultimo_mes_p.replace(day=1).strftime('%Y-%m-%d')
            fim_mp = ultimo_mes_p.strftime('%Y-%m-%d')
            dados['resumo_mes_passado'] = self._resumo_periodo(
                ini_mp, fim_mp, "mês passado"
            )

            # ── Resumo ano atual ─────────────────────────────
            ini_ano = f"{hoje.year}-01-01"
            fim_ano = hoje.strftime('%Y-%m-%d')
            dados['resumo_ano'] = self._resumo_periodo(
                ini_ano, fim_ano, "ano atual"
            )

            # ── Top gastos do mês ────────────────────────────
            top = self.db.execute(
                """SELECT t.amount, t.description,
                          t.date, c.name as categoria
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   ORDER BY t.amount DESC LIMIT 5""",
                (self.uid, ini_mes, fim_mes)
            ).fetchall()

            for t in top:
                dados['top_gastos_mes'].append({
                    'valor':     t['amount'],
                    'descricao': t['description'],
                    'data':      t['date'],
                    'categoria': t['categoria'],
                })

            # ── Transações recentes ──────────────────────────
            recentes = self.db.execute(
                """SELECT t.amount, t.description,
                          t.transaction_type, t.date,
                          c.name as categoria
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   ORDER BY t.date DESC, t.id DESC
                   LIMIT 10""",
                (self.uid,)
            ).fetchall()

            for t in recentes:
                dados['recentes'].append({
                    'valor':     t['amount'],
                    'descricao': t['description'],
                    'tipo':      t['transaction_type'],
                    'data':      t['date'],
                    'categoria': t['categoria'],
                })

            # ── Categorias com gastos do mês ─────────────────
            cats_mes = self.db.execute(
                """SELECT c.name, t.transaction_type,
                          SUM(t.amount) as total
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND t.date BETWEEN ? AND ?
                   GROUP BY c.name, t.transaction_type
                   ORDER BY total DESC""",
                (self.uid, ini_mes, fim_mes)
            ).fetchall()

            cats_dict = {}
            for r in cats_mes:
                nome = r['name'] if r['name'] else None
                if nome not in cats_dict:
                    cats_dict[nome] = {
                        'entradas': 0, 'saidas': 0
                    }
                if r['transaction_type'] == 'entrada':
                    cats_dict[nome]['entradas'] = r['total']
                else:
                    cats_dict[nome]['saidas'] = r['total']

            dados['categorias'] = [
                {
                    'nome':     nome if nome else 'Sem categoria',
                    'entradas': v['entradas'],
                    'saidas':   v['saidas'],
                }
                for nome, v in cats_dict.items()
            ]

        except Exception as e:
            print(f"[Agente] Erro ao coletar dados: {e}")

        return dados

    def _resumo_periodo(self, inicio, fim, label):
        """Coleta resumo financeiro de um período"""
        try:
            rows = self.db.execute(
                """SELECT t.transaction_type,
                          c.name as categoria,
                          SUM(t.amount) as total,
                          COUNT(*) as qtd
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND t.date BETWEEN ? AND ?
                   GROUP BY t.transaction_type, c.name
                   ORDER BY total DESC""",
                (self.uid, inicio, fim)
            ).fetchall()

            entradas = saidas = 0
            cats_saida = []

            for r in rows:
                if r['transaction_type'] == 'entrada':
                    entradas += r['total']
                else:
                    saidas += r['total']
                    cats_saida.append({
                        'categoria': r['categoria'] or 'Sem categoria',
                        'total':     r['total'],
                        'qtd':       r['qtd'],
                    })

            # Ordenar por valor
            cats_saida.sort(key=lambda x: x['total'], reverse=True)

            return {
                'label':      label,
                'inicio':     inicio,
                'fim':        fim,
                'entradas':   entradas,
                'saidas':     saidas,
                'saldo':      entradas - saidas,
                'categorias': cats_saida[:5],  # top 5
                'qtd_trans':  len(rows),
            }

        except Exception as e:
            print(f"[Agente] Erro resumo período: {e}")
            return {
                'label': label, 'entradas': 0,
                'saidas': 0, 'saldo': 0,
                'categorias': [], 'qtd_trans': 0
            }

    # ── Respostas Locais ─────────────────────────────────────

    def _resp_saldo(self):
        """Responde sobre saldo atual"""
        d = self._coletar_dados_completos()

        r  = "💰 **Resumo Financeiro Atual**\n\n"
        r += f"• Saldo total: **R$ {d['saldo_total']:.2f}**\n"

        if d['guardado_metas'] > 0:
            r += f"• Guardado em metas: R$ {d['guardado_metas']:.2f}\n"
            r += f"• Disponível: **R$ {d['disponivel']:.2f}**\n"

        r += f"\n📊 Total de entradas: R$ {d['total_entradas']:.2f}"
        r += f"\n📊 Total de saídas:   R$ {d['total_saidas']:.2f}"

        # Mês atual
        mes = d['resumo_mes']
        if mes['entradas'] > 0 or mes['saidas'] > 0:
            r += f"\n\n📅 **Este mês:**\n"
            r += f"• Receitas: R$ {mes['entradas']:.2f}\n"
            r += f"• Despesas: R$ {mes['saidas']:.2f}\n"
            r += f"• Saldo:    R$ {mes['saldo']:.2f}"

        return r

    def _resp_recentes(self):
        """Lista transações recentes"""
        d = self._coletar_dados_completos()

        if not d['recentes']:
            return "Não há transações registradas ainda."

        r = "📋 **Últimas Transações:**\n\n"
        for t in d['recentes']:
            emoji = "💚" if t['tipo'] == 'entrada' else "🔴"
            r += f"{emoji} {t['data']} | R$ {t['valor']:.2f}"
            r += f" | {t['descricao']}"
            if t['categoria']:
                r += f" ({t['categoria']})"
            r += "\n"

        return r

    def _resp_metas(self):
        """Lista metas de economia"""
        d = self._coletar_dados_completos()

        if not d['metas']:
            return (
                "Você não tem metas de economia cadastradas.\n\n"
                "💡 Você pode criar metas em "
                "**Metas de Economia** no menu principal."
            )

        r = "🎯 **Metas de Economia:**\n\n"
        for m in d['metas']:
            barra = self._barra(m['pct'])
            r += f"**{m['nome']}**\n"
            r += f"{barra} {m['pct']:.0f}%\n"
            r += (
                f"R$ {m['atual']:.2f} de R$ {m['meta']:.2f} | "
                f"Faltam: R$ {m['meta'] - m['atual']:.2f}\n"
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
        """Mostra gastos por categoria do mês"""
        d = self._coletar_dados_completos()

        cats = [
            c for c in d['categorias'] if c['saidas'] > 0
        ]

        if not cats:
            if not d['tem_categorias']:
                return (
                    "Você ainda não criou categorias.\n\n"
                    "💡 Crie categorias no menu principal para "
                    "organizar melhor seus gastos!"
                )
            return "Sem gastos por categoria este mês."

        total = sum(c['saidas'] for c in cats)
        r = f"📊 **Gastos por Categoria (mês atual):**\n\n"

        for c in sorted(cats, key=lambda x: x['saidas'], reverse=True):
            nome = c['nome']
            pct  = (c['saidas'] / total * 100) if total > 0 else 0
            r += f"• {nome}: R$ {c['saidas']:.2f} ({pct:.1f}%)\n"

        r += f"\n💸 Total: R$ {total:.2f}"
        return r

    def _resp_maiores(self):
        """Lista maiores gastos do mês"""
        d = self._coletar_dados_completos()

        if not d['top_gastos_mes']:
            return "Sem despesas registradas este mês."

        r = "💸 **Maiores Gastos do Mês:**\n\n"
        for i, t in enumerate(d['top_gastos_mes'], 1):
            r += f"{i}. R$ {t['valor']:.2f} — {t['descricao']}"
            if t['categoria']:
                r += f" ({t['categoria']})"
            r += f" | {t['data']}\n"

        return r

    # ── Prompt Inteligente para o Servidor ───────────────────

    def _montar_prompt_servidor(self, pergunta_usuario):
        """
        Monta prompt rico, preciso e eficiente para o servidor de IA.

        Princípios:
        - Dados reais e verificados do banco
        - Contexto claro sobre ausência de dados
        - Instruções precisas para a LLM
        - Mínimo de tokens, máximo de informação
        """
        d    = self._coletar_dados_completos()
        hoje = datetime.now()

        # ── Sistema ──────────────────────────────────────────
        sistema = (
            "Você é um assistente financeiro pessoal preciso e empático.\n"
            "REGRAS OBRIGATÓRIAS:\n"
            "1. Responda SEMPRE em português brasileiro\n"
            "2. Use APENAS os dados fornecidos abaixo - não invente valores\n"
            "3. Se um dado não existir, diga claramente que não há registro\n"
            "4. Seja objetivo, direto e amigável\n"
            "5. Use formatação clara com bullets e negrito\n"
            "6. Quando não houver categorias, explique isso ao usuário\n"
            "7. Nunca chame gastos sem categoria de 'Outros' se não existir "
            "essa categoria - diga 'sem categoria definida'\n"
        )

        # ── Dados do Usuário ─────────────────────────────────
        dados_ctx = f"\n{'='*50}\n"
        dados_ctx += f"DATA ATUAL: {hoje.strftime('%d/%m/%Y %H:%M')}\n"
        dados_ctx += f"{'='*50}\n\n"

        # Saldo
        dados_ctx += "## SITUAÇÃO FINANCEIRA GERAL\n"
        dados_ctx += f"- Saldo total: R$ {d['saldo_total']:.2f}\n"
        dados_ctx += (
            f"- Total de entradas (histórico): "
            f"R$ {d['total_entradas']:.2f}\n"
        )
        dados_ctx += (
            f"- Total de saídas (histórico): "
            f"R$ {d['total_saidas']:.2f}\n"
        )
        dados_ctx += (
            f"- Total de transações registradas: "
            f"{d['total_transacoes']}\n"
        )

        if d['guardado_metas'] > 0:
            dados_ctx += (
                f"- Guardado em metas: R$ {d['guardado_metas']:.2f}\n"
            )
            dados_ctx += (
                f"- Saldo disponível: R$ {d['disponivel']:.2f}\n"
            )

        # Categorias
        dados_ctx += "\n## CATEGORIAS\n"
        if not d['tem_categorias']:
            dados_ctx += (
                "IMPORTANTE: O usuário ainda NÃO criou categorias. "
                "Portanto NÃO há gastos por categoria. "
                "Não mencione 'Outros' ou qualquer categoria. "
                "Sugira ao usuário criar categorias para melhor controle.\n"
            )
        else:
            cats_com_gasto = [
                c for c in d['categorias'] if c['saidas'] > 0
            ]
            if cats_com_gasto:
                dados_ctx += "Gastos por categoria (mês atual):\n"
                for c in cats_com_gasto:
                    dados_ctx += (
                        f"  - {c['nome']}: "
                        f"R$ {c['saidas']:.2f}\n"
                    )
            else:
                dados_ctx += (
                    "Existem categorias cadastradas mas sem gastos "
                    "registrados neste mês.\n"
                )

        # Mês atual
        mes = d['resumo_mes']
        dados_ctx += f"\n## MÊS ATUAL ({hoje.strftime('%B/%Y').upper()})\n"
        if mes['entradas'] == 0 and mes['saidas'] == 0:
            dados_ctx += "Sem movimentações neste mês.\n"
        else:
            dados_ctx += f"- Receitas: R$ {mes['entradas']:.2f}\n"
            dados_ctx += f"- Despesas: R$ {mes['saidas']:.2f}\n"
            dados_ctx += f"- Saldo do mês: R$ {mes['saldo']:.2f}\n"
            if mes['saldo'] >= 0:
                dados_ctx += "- Status: POSITIVO ✅\n"
            else:
                dados_ctx += "- Status: NEGATIVO ⚠️\n"

        # Mês passado
        mp = d['resumo_mes_passado']
        if mp['entradas'] > 0 or mp['saidas'] > 0:
            mes_p = (hoje.replace(day=1) - timedelta(days=1))
            dados_ctx += (
                f"\n## MÊS PASSADO "
                f"({mes_p.strftime('%B/%Y').upper()})\n"
            )
            dados_ctx += f"- Receitas: R$ {mp['entradas']:.2f}\n"
            dados_ctx += f"- Despesas: R$ {mp['saidas']:.2f}\n"
            dados_ctx += f"- Saldo: R$ {mp['saldo']:.2f}\n"

        # Ano atual
        ano = d['resumo_ano']
        dados_ctx += f"\n## ANO ATUAL ({hoje.year})\n"
        if ano['entradas'] == 0 and ano['saidas'] == 0:
            dados_ctx += "Sem movimentações este ano.\n"
        else:
            dados_ctx += f"- Receitas: R$ {ano['entradas']:.2f}\n"
            dados_ctx += f"- Despesas: R$ {ano['saidas']:.2f}\n"
            dados_ctx += f"- Saldo: R$ {ano['saldo']:.2f}\n"

        # Top gastos do mês
        if d['top_gastos_mes']:
            dados_ctx += "\n## MAIORES DESPESAS DO MÊS\n"
            for i, t in enumerate(d['top_gastos_mes'], 1):
                cat = (
                    f" ({t['categoria']})"
                    if t['categoria'] else " (sem categoria)"
                )
                dados_ctx += (
                    f"{i}. R$ {t['valor']:.2f} - "
                    f"{t['descricao']}{cat} | {t['data']}\n"
                )

        # Transações recentes
        if d['recentes']:
            dados_ctx += "\n## TRANSAÇÕES RECENTES\n"
            for t in d['recentes'][:5]:
                tipo = (
                    "Entrada" if t['tipo'] == 'entrada'
                    else "Saída"
                )
                cat = (
                    f" ({t['categoria']})"
                    if t['categoria'] else ""
                )
                dados_ctx += (
                    f"- {t['data']} | {tipo} "
                    f"R$ {t['valor']:.2f} | "
                    f"{t['descricao']}{cat}\n"
                )

        # Metas
        if d['metas']:
            dados_ctx += "\n## METAS DE ECONOMIA\n"
            for m in d['metas']:
                dados_ctx += (
                    f"- {m['nome']}: "
                    f"R$ {m['atual']:.2f} / R$ {m['meta']:.2f} "
                    f"({m['pct']:.0f}%)"
                )
                if m['prazo']:
                    dados_ctx += f" | Prazo: {m['prazo']}"
                dados_ctx += "\n"
        else:
            dados_ctx += "\n## METAS DE ECONOMIA\n"
            dados_ctx += "Nenhuma meta cadastrada.\n"

        dados_ctx += f"\n{'='*50}\n"

        # ── Prompt Final ─────────────────────────────────────
        prompt_final = (
            f"{sistema}\n\n"
            f"DADOS FINANCEIROS REAIS DO USUÁRIO:\n"
            f"{dados_ctx}\n"
            f"PERGUNTA DO USUÁRIO: {pergunta_usuario}\n\n"
            f"Responda com base EXCLUSIVAMENTE nos dados acima. "
            f"Se algo não tiver dados, diga claramente."
        )

        return prompt_final

    # ── Utilitários ──────────────────────────────────────────

    def _barra(self, pct):
        """Barra de progresso visual"""
        pct     = max(0, min(100, pct))
        filled  = int(pct / 10)
        empty   = 10 - filled
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
    """
    Thread para processar requisições ao servidor de IA.
    Usa /api/servico/prompt com X-API-Key.
    Timeout=None (sem limite).
    """

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

    def _detect_network(self):
        """Detecta automaticamente qual rede usar"""
        import socket

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

        try:
            test_session = requests.Session()
            test_session.proxies = {
                'http':  'socks5h://localhost:9050',
                'https': 'socks5h://localhost:9050'
            }
            test_session.get(
                "http://check.torproject.org",
                timeout=10
            )
            self.base_url = ONION_URL
            self.use_tor  = True
            return True
        except Exception:
            pass

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

            # Sem limite de timeout
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
