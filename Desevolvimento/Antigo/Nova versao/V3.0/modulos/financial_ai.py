"""
Integração do sistema financeiro com agente de IA
"""
import socket
import json
import threading
import time
import random
from datetime import datetime, timedelta

import requests
import urllib3

urllib3.disable_warnings()


# ============================================================
# ENDPOINTS DE COMUNICAÇÃO
# ============================================================

LOCAL_IP   = "172.17.0.1"
LOCAL_PORT = 5010
LOCAL_URL  = f"https://{LOCAL_IP}:{LOCAL_PORT}"

ONION_HOST = "6mr2qs6pulbu55rpwirzjron6ycoaoi73rdg5nbvjt3n5x3goxv2emad.onion"
ONION_PORT = 80
ONION_URL  = f"http://{ONION_HOST}:{ONION_PORT}"

POLL_INTERVAL = 3


# ============================================================
# COMANDOS FINANCEIROS
# ============================================================

COMANDOS_FINANCEIROS = [
    {
        "comando":    "GET_SALDO",
        "descricao":  "Retorna o saldo atual da conta. "
                      "Use quando o usuário perguntar sobre saldo, "
                      "quanto tem na conta ou situação financeira geral.",
        "parametros": "nenhum",
        "exemplo":    "GET_SALDO → Saldo: R$ 1.250,50"
    },
    {
        "comando":    "GET_GASTOS_CATEGORIA",
        "descricao":  "Retorna gastos por categoria específica. "
                      "Use quando o usuário perguntar sobre gastos em "
                      "uma categoria específica.",
        "parametros": "categoria=nome&periodo=mes|ano|todos",
        "exemplo":    "GET_GASTOS_CATEGORIA=alimentacao&mes"
    },
    {
        "comando":    "GET_TRANSACOES_RECENTES",
        "descricao":  "Lista as transações mais recentes.",
        "parametros": "quantidade=N (padrão: 5)",
        "exemplo":    "GET_TRANSACOES_RECENTES=5"
    },
    {
        "comando":    "GET_MAIORES_GASTOS",
        "descricao":  "Lista as maiores despesas em um período.",
        "parametros": "periodo=mes|ano|todos&limite=N",
        "exemplo":    "GET_MAIORES_GASTOS=mes&5"
    },
    {
        "comando":    "GET_BALANCO_MENSAL",
        "descricao":  "Retorna balanço financeiro mensal "
                      "(receitas vs despesas).",
        "parametros": "mes=MM&ano=AAAA",
        "exemplo":    "GET_BALANCO_MENSAL=04&2026"
    },
    {
        "comando":    "GET_PREVISAO_GASTOS",
        "descricao":  "Retorna previsão de gastos futuros "
                      "baseada nos padrões históricos.",
        "parametros": "meses=N (padrão: 1)",
        "exemplo":    "GET_PREVISAO_GASTOS=3"
    },
    {
        "comando":    "GET_METAS_ECONOMIA",
        "descricao":  "Lista as metas de economia e seu progresso.",
        "parametros": "nenhum",
        "exemplo":    "GET_METAS_ECONOMIA"
    },
    {
        "comando":    "GET_COMPARATIVO_CATEGORIAS",
        "descricao":  "Compara gastos entre todas as categorias.",
        "parametros": "periodo=mes|ano",
        "exemplo":    "GET_COMPARATIVO_CATEGORIAS=mes"
    },
    {
        "comando":    "GET_TENDENCIA_GASTO",
        "descricao":  "Analisa tendência de gasto em uma categoria "
                      "nos últimos N meses.",
        "parametros": "categoria=nome&meses=N",
        "exemplo":    "GET_TENDENCIA_GASTO=alimentacao&6"
    },
    {
        "comando":    "GET_ORCAMENTO_STATUS",
        "descricao":  "Verifica status do orçamento mensal. "
                      "Mostra quanto já foi gasto vs orçado.",
        "parametros": "categoria=nome (opcional)",
        "exemplo":    "GET_ORCAMENTO_STATUS=lazer"
    },
    {
        "comando":    "GET_EMPRESTIMOS",
        "descricao":  "Lista todos os empréstimos ativos e quitados "
                      "com progresso de pagamento.",
        "parametros": "status=ativo|quitado|todos (padrão: todos)",
        "exemplo":    "GET_EMPRESTIMOS=ativo"
    },
    {
        "comando":    "GET_HISTORICO_MENSAL",
        "descricao":  "Retorna histórico de receitas e despesas "
                      "dos últimos N meses para análise de tendência.",
        "parametros": "meses=N (padrão: 3)",
        "exemplo":    "GET_HISTORICO_MENSAL=6"
    },
    {
        "comando":    "GET_RESUMO_COMPLETO",
        "descricao":  "Retorna resumo financeiro completo: saldo, "
                      "mês atual, categorias, metas e empréstimos. "
                      "Use para análises gerais ou quando o usuário "
                      "pedir uma visão geral das finanças.",
        "parametros": "nenhum",
        "exemplo":    "GET_RESUMO_COMPLETO"
    },
]


# ============================================================
# FUNÇÃO AUXILIAR — fora da classe
# ============================================================

def _log_tor_pronto(proxy_url: str):
    """Helper para logar quando Tor está pronto"""
    from modulos.tor_manager import SOCKS_PORT
    print(
        f"[FinancialAI] ✅ Tor disponível "
        f"→ SOCKS5 127.0.0.1:{SOCKS_PORT}"
    )


# ============================================================
# CLASSE PRINCIPAL
# ============================================================

class FinancialAI:
    """
    Sistema de IA integrado ao sistema de gestão financeira.

    Detecta automaticamente se está na rede local (usa HTTPS)
    ou em rede externa (usa Tor via tor_manager).

    A API Key é fornecida pelo usuário via interface e
    armazenada no banco de dados.
    """

    def __init__(self, db_connection, user_id):
        self.db_connection = db_connection
        self.user_id       = user_id
        self.device_id     = None
        self.running       = False
        self.use_tor       = False
        self.base_url      = None
        self.api_key       = self._load_api_key()

        self.session        = requests.Session()
        self.session.verify = False

        if self.api_key:
            self.session.headers.update({
                "X-API-Key":    self.api_key,
                "Content-Type": "application/json"
            })

        self._logs = []

    # ----------------------------------------------------------
    # CONFIGURAÇÃO
    # ----------------------------------------------------------

    def _load_api_key(self):
        """Carrega a API Key salva pelo usuário no banco de dados"""
        try:
            row = self.db_connection.execute(
                """SELECT setting_value FROM user_settings
                   WHERE user_id = ? AND setting_key = 'ai_api_key'""",
                (self.user_id,)
            ).fetchone()

            return row[0] if row else None

        except Exception as e:
            print(f"[FinancialAI] Erro ao carregar API Key: {e}")
            return None

    def _detect_network(self):
        """
        Detecta automaticamente qual rede usar.
        Ordem de prioridade:
        1. Rede local (HTTPS direto)
        2. Tor via tor_manager (SOCKS5 gerenciado pelo app)
        """
        print("[FinancialAI] Detectando rede disponível...")

        # ── 1. Tentar rede local ──────────────────────────────
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((LOCAL_IP, LOCAL_PORT))
            s.close()

            self.base_url = LOCAL_URL
            self.use_tor  = False
            print(f"[FinancialAI] ✅ Rede local → {LOCAL_URL}")
            return True

        except (socket.timeout, socket.error, OSError):
            print(
                "[FinancialAI] Rede local indisponível, "
                "tentando Tor..."
            )

        # ── 2. Tentar via Tor (tor_manager) ───────────────────
        try:
            from modulos.tor_manager import (
                iniciar_tor, obter_proxy_url, status_tor
            )

            st = status_tor()

            # Tor já rodando com SOCKS5 disponível?
            if st['socks_ok'] and st['bootstrap_ok']:
                proxy_url = obter_proxy_url()
                self._configurar_sessao_tor(proxy_url)
                _log_tor_pronto(proxy_url)
                return True

            # Tentar iniciar Tor
            print("[FinancialAI] Iniciando Tor...")
            sucesso, msg = iniciar_tor()

            if sucesso:
                proxy_url = obter_proxy_url()
                self._configurar_sessao_tor(proxy_url)
                _log_tor_pronto(proxy_url)
                return True

            print(f"[FinancialAI] ❌ Tor falhou: {msg}")

        except ImportError:
            print("[FinancialAI] tor_manager não disponível")
        except Exception as e:
            print(f"[FinancialAI] ❌ Erro Tor: {e}")

        print("[FinancialAI] ❌ Nenhuma rede disponível")
        return False

    def _configurar_sessao_tor(self, proxy_url: str):
        """
        Configura a sessão requests para usar o proxy Tor.
        """
        self.base_url = ONION_URL
        self.use_tor  = True
        self.session.proxies = {
            'http':  proxy_url,
            'https': proxy_url
        }
        print(f"[FinancialAI] ✅ Tor ativo → {ONION_URL}")

    # ----------------------------------------------------------
    # REGISTRO
    # ----------------------------------------------------------

    def register(self):
        """Registra o sistema no servidor de IA"""
        if not self.api_key:
            print("[FinancialAI] ❌ API Key não configurada")
            return False

        if not self._detect_network():
            print("[FinancialAI] ❌ Sem conexão disponível")
            return False

        payload = {
            "nome":      "Sistema de Gestão Financeira",
            "descricao": "Sistema para gerenciar finanças pessoais, "
                         "transações, orçamentos e metas financeiras",
            "tipo":      "financeiro",
            "comandos":  COMANDOS_FINANCEIROS
        }

        try:
            response = self.session.post(
                f"{self.base_url}/api/servico/registrar",
                json=payload,
                timeout=10
            )
            data = response.json()

            if data.get("sucesso"):
                self.device_id = data["dispositivo_id"]
                network_type   = (
                    "Tor" if self.use_tor else "Rede Local"
                )
                print(
                    f"[FinancialAI] ✅ Registrado via "
                    f"{network_type} | ID: {self.device_id}"
                )
                return True

            print(f"[FinancialAI] ❌ Falha no registro: {data}")
            return False

        except Exception as e:
            print(f"[FinancialAI] ❌ Erro ao registrar: {e}")
            return False

    # ----------------------------------------------------------
    # INICIALIZAÇÃO
    # ----------------------------------------------------------

    def start(self):
        """Inicia o sistema de IA em background"""
        if self.register():
            self.running = True

            threading.Thread(
                target=self._heartbeat_loop,
                daemon=True,
                name="FinancialAI-Heartbeat"
            ).start()

            threading.Thread(
                target=self._commands_loop,
                daemon=True,
                name="FinancialAI-Commands"
            ).start()

            network_type = "Tor" if self.use_tor else "Rede Local"
            print(
                f"[FinancialAI] ✅ Sistema iniciado "
                f"via {network_type}"
            )
            return True

        return False

    def stop(self):
        """Para o sistema de IA"""
        self.running = False
        print("[FinancialAI] Sistema parado")

    # ----------------------------------------------------------
    # LOOPS DE BACKGROUND
    # ----------------------------------------------------------

    def _heartbeat_loop(self):
        """Envia heartbeats periódicos para manter a conexão"""
        while self.running:
            try:
                self.session.post(
                    f"{self.base_url}/api/servico/"
                    f"heartbeat/{self.device_id}",
                    timeout=5
                )
            except Exception:
                pass

            time.sleep(30)

    def _commands_loop(self):
        """Verifica e processa comandos pendentes do servidor"""
        while self.running:
            try:
                response = self.session.get(
                    f"{self.base_url}/api/servico/"
                    f"comandos/{self.device_id}",
                    timeout=10
                )
                data = response.json()

                for cmd in data.get("comandos", []):
                    resultado = self.process_command(
                        cmd["comando"],
                        cmd.get("parametros", "")
                    )

                    self.session.post(
                        f"{self.base_url}/api/servico/resultado",
                        json={
                            "comando_id": cmd["id"],
                            "resposta":   str(resultado),
                            "sucesso":    True
                        },
                        timeout=10
                    )

            except Exception as e:
                print(
                    f"[FinancialAI] Erro no loop "
                    f"de comandos: {e}"
                )

            time.sleep(POLL_INTERVAL)

    # ----------------------------------------------------------
    # PROCESSAMENTO DE COMANDOS
    # ----------------------------------------------------------

    def process_command(self, command, parameters):
        """Processa comandos recebidos do servidor de IA"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {command} | {parameters}"
        self._logs.append(log_entry)
        print(f"[FinancialAI] ⚡ {log_entry}")

        try:
            return self._execute(command, parameters)
        except Exception as e:
            erro = f"Erro ao executar {command}: {str(e)}"
            print(f"[FinancialAI] ❌ {erro}")
            return erro

    def _execute(self, command, parameters):
        """Mapeia e executa o comando recebido"""

        if command == "GET_SALDO":
            return self._get_balance()

        elif command == "GET_GASTOS_CATEGORIA":
            params   = self._parse_parameters(parameters)
            category = params.get("categoria", "")
            period   = params.get("periodo", "mes")
            return self._get_category_expenses(category, period)

        elif command == "GET_TRANSACOES_RECENTES":
            limit = int(parameters) if parameters.isdigit() else 5
            return self._get_recent_transactions(limit)

        elif command == "GET_MAIORES_GASTOS":
            params = self._parse_parameters(parameters)
            period = params.get("periodo", "mes")
            limit  = int(params.get("limite", "5"))
            return self._get_top_expenses(period, limit)

        elif command == "GET_BALANCO_MENSAL":
            params = self._parse_parameters(parameters)
            month  = int(params.get("mes",  datetime.now().month))
            year   = int(params.get("ano",  datetime.now().year))
            return self._get_monthly_balance(month, year)

        elif command == "GET_PREVISAO_GASTOS":
            months = int(parameters) if parameters.isdigit() else 1
            return self._get_expense_forecast(months)

        elif command == "GET_METAS_ECONOMIA":
            return self._get_savings_goals()

        elif command == "GET_COMPARATIVO_CATEGORIAS":
            period = (
                parameters if parameters in ["mes", "ano"]
                else "mes"
            )
            return self._get_category_comparison(period)

        elif command == "GET_TENDENCIA_GASTO":
            params   = self._parse_parameters(parameters)
            category = params.get("categoria", "")
            months   = int(params.get("meses", "3"))
            return self._get_expense_trend(category, months)

        elif command == "GET_ORCAMENTO_STATUS":
            category = parameters if parameters else None
            return self._get_budget_status(category)

        elif command == "GET_EMPRESTIMOS":
            status = (
                parameters
                if parameters in ["ativo", "quitado"]
                else "todos"
            )
            return self._get_emprestimos(status)

        elif command == "GET_HISTORICO_MENSAL":
            meses = (
                int(parameters)
                if parameters.isdigit() else 3
            )
            return self._get_historico_mensal(meses)

        elif command == "GET_RESUMO_COMPLETO":
            return self._get_resumo_completo()

        else:
            disponíveis = ", ".join(
                c["comando"] for c in COMANDOS_FINANCEIROS
            )
            return (
                f"Comando '{command}' não reconhecido.\n"
                f"Disponíveis: {disponíveis}"
            )

    # ----------------------------------------------------------
    # UTILITÁRIOS
    # ----------------------------------------------------------

    def _parse_parameters(self, params_str):
        """Converte string de parâmetros em dicionário"""
        result = {}

        if "&" in params_str:
            for part in params_str.split("&"):
                if "=" in part:
                    key, value = part.split("=", 1)
                    result[key.strip()] = value.strip()
                else:
                    result[part.strip()] = True
        elif "=" in params_str:
            key, value = params_str.split("=", 1)
            result[key.strip()] = value.strip()

        return result

    def _get_date_range(self, period):
        """Retorna (start_date, end_date, period_name)"""
        today = datetime.now()

        if period == "mes":
            start = today.replace(day=1).strftime('%Y-%m-%d')
            end   = today.strftime('%Y-%m-%d')
            name  = "este mês"
        elif period == "ano":
            start = today.replace(
                month=1, day=1
            ).strftime('%Y-%m-%d')
            end   = today.strftime('%Y-%m-%d')
            name  = "este ano"
        else:
            start = "2000-01-01"
            end   = today.strftime('%Y-%m-%d')
            name  = "todo o período"

        return start, end, name

    # ----------------------------------------------------------
    # IMPLEMENTAÇÃO DOS COMANDOS ORIGINAIS
    # ----------------------------------------------------------

    def _get_balance(self):
        """Retorna o saldo atual da conta"""
        try:
            transactions = self.db_connection.execute(
                'SELECT transaction_type, amount '
                'FROM transactions WHERE user_id = ?',
                (self.user_id,)
            ).fetchall()

            entries = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'entrada'
            )
            exits = sum(
                t['amount'] for t in transactions
                if t['transaction_type'] == 'saida'
            )
            balance = entries - exits

            savings_row = self.db_connection.execute(
                'SELECT SUM(current_amount) as total '
                'FROM savings_goals WHERE user_id = ?',
                (self.user_id,)
            ).fetchone()

            savings   = (
                savings_row['total']
                if savings_row['total'] else 0
            )
            available = balance - savings

            return (
                f"Saldo total: R$ {balance:,.2f}\n"
                f"Guardado em metas: R$ {savings:,.2f}\n"
                f"Saldo disponível: R$ {available:,.2f}"
            )

        except Exception as e:
            return f"Erro ao obter saldo: {str(e)}"

    def _get_category_expenses(self, category, period):
        """Retorna gastos de uma categoria específica"""
        try:
            start, end, period_name = self._get_date_range(period)

            cat_row = self.db_connection.execute(
                'SELECT id FROM categories '
                'WHERE user_id = ? AND name = ?',
                (self.user_id, category)
            ).fetchone()

            if not cat_row:
                return f"Categoria '{category}' não encontrada"

            total = self.db_connection.execute(
                """SELECT SUM(amount) as total
                   FROM transactions
                   WHERE user_id = ? AND category_id = ?
                   AND transaction_type = 'saida'
                   AND date BETWEEN ? AND ?""",
                (self.user_id, cat_row['id'], start, end)
            ).fetchone()['total'] or 0

            today  = datetime.now()
            months = max(1, (
                (today.year  - int(start[:4])) * 12 +
                (today.month - int(start[5:7])) + 1
            ))
            avg = total / months if period != "mes" else total

            return (
                f"Gastos em '{category}' ({period_name}): "
                f"R$ {total:,.2f}\n"
                f"Média mensal: R$ {avg:,.2f}"
            )

        except Exception as e:
            return f"Erro ao obter gastos da categoria: {str(e)}"

    def _get_recent_transactions(self, limit):
        """Retorna as transações mais recentes"""
        try:
            transactions = self.db_connection.execute(
                '''SELECT t.amount, t.description,
                          t.transaction_type, t.date,
                          c.name as category_name
                   FROM transactions t
                   LEFT JOIN categories c
                          ON t.category_id = c.id
                   WHERE t.user_id = ?
                   ORDER BY t.date DESC, t.id DESC
                   LIMIT ?''',
                (self.user_id, limit)
            ).fetchall()

            if not transactions:
                return "Não há transações recentes"

            result = f"Últimas {len(transactions)} transações:\n\n"

            for t in transactions:
                tipo = (
                    "Receita"
                    if t['transaction_type'] == 'entrada'
                    else "Despesa"
                )
                result += (
                    f"• {t['date']} | {t['description']}\n"
                    f"  {tipo}: R$ {t['amount']:,.2f}"
                )
                if t['category_name']:
                    result += f" | {t['category_name']}"
                result += "\n\n"

            return result.strip()

        except Exception as e:
            return (
                f"Erro ao obter transações recentes: {str(e)}"
            )

    def _get_top_expenses(self, period, limit):
        """Retorna as maiores despesas em um período"""
        try:
            start, end, period_name = self._get_date_range(period)

            expenses = self.db_connection.execute(
                '''SELECT t.amount, t.description, t.date,
                          c.name as category_name
                   FROM transactions t
                   LEFT JOIN categories c
                          ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   ORDER BY t.amount DESC
                   LIMIT ?''',
                (self.user_id, start, end, limit)
            ).fetchall()

            if not expenses:
                return (
                    f"Não há despesas registradas {period_name}"
                )

            result = f"Maiores despesas {period_name}:\n\n"

            for i, e in enumerate(expenses, 1):
                result += (
                    f"{i}. R$ {e['amount']:,.2f} "
                    f"- {e['description']}\n"
                    f"   Data: {e['date']}"
                )
                if e['category_name']:
                    result += f" | {e['category_name']}"
                result += "\n\n"

            return result.strip()

        except Exception as e:
            return f"Erro ao obter maiores despesas: {str(e)}"

    def _get_monthly_balance(self, month, year):
        """Retorna o balanço mensal"""
        try:
            try:
                start = datetime(
                    year, month, 1
                ).strftime('%Y-%m-%d')
                if month == 12:
                    end = (
                        datetime(year + 1, 1, 1) -
                        timedelta(days=1)
                    )
                else:
                    end = (
                        datetime(year, month + 1, 1) -
                        timedelta(days=1)
                    )
                end = end.strftime('%Y-%m-%d')
            except ValueError:
                return f"Mês/ano inválidos: {month}/{year}"

            results = self.db_connection.execute(
                '''SELECT transaction_type, SUM(amount) as total
                   FROM transactions
                   WHERE user_id = ? AND date BETWEEN ? AND ?
                   GROUP BY transaction_type''',
                (self.user_id, start, end)
            ).fetchall()

            income = expense = 0
            for r in results:
                if r['transaction_type'] == 'entrada':
                    income  = r['total']
                elif r['transaction_type'] == 'saida':
                    expense = r['total']

            balance = income - expense

            top_cats = self.db_connection.execute(
                '''SELECT c.name, SUM(t.amount) as total
                   FROM transactions t
                   JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   GROUP BY c.name
                   ORDER BY total DESC LIMIT 3''',
                (self.user_id, start, end)
            ).fetchall()

            month_name = datetime(
                year, month, 1
            ).strftime('%B').capitalize()

            result = (
                f"Balanço de {month_name}/{year}:\n\n"
                f"Receitas: R$ {income:,.2f}\n"
                f"Despesas: R$ {expense:,.2f}\n"
                f"Saldo: R$ {balance:,.2f}"
            )

            if top_cats:
                result += "\n\nPrincipais categorias de despesa:"
                for cat in top_cats:
                    result += (
                        f"\n• {cat['name']}: "
                        f"R$ {cat['total']:,.2f}"
                    )

            return result

        except Exception as e:
            return f"Erro ao calcular balanço mensal: {str(e)}"

    def _get_expense_forecast(self, months):
        """Retorna previsão de gastos futuros"""
        try:
            today            = datetime.now()
            three_months_ago = (
                today - timedelta(days=90)
            ).strftime('%Y-%m-%d')

            monthly_stats = self.db_connection.execute(
                """SELECT strftime('%Y-%m', date) as month,
                          SUM(CASE WHEN transaction_type='entrada'
                              THEN amount ELSE 0 END) as income,
                          SUM(CASE WHEN transaction_type='saida'
                              THEN amount ELSE 0 END) as expense
                   FROM transactions
                   WHERE user_id = ? AND date >= ?
                   GROUP BY month""",
                (self.user_id, three_months_ago)
            ).fetchall()

            if not monthly_stats:
                return "Dados insuficientes para previsão"

            avg_income = (
                sum(m['income']  for m in monthly_stats) /
                len(monthly_stats)
            )
            avg_expense = (
                sum(m['expense'] for m in monthly_stats) /
                len(monthly_stats)
            )
            avg_balance = avg_income - avg_expense

            result          = (
                f"Previsão para os próximos {months} meses:\n\n"
            )
            running_balance = 0
            variation       = 0.05

            for i in range(1, months + 1):
                next_month = (
                    today.replace(day=1) +
                    timedelta(days=32 * i)
                ).replace(day=1)

                month_name = (
                    next_month.strftime('%B %Y').capitalize()
                )

                m_income  = avg_income  * (
                    1 + random.uniform(-variation, variation)
                )
                m_expense = avg_expense * (
                    1 + random.uniform(-variation, variation)
                )
                m_balance       = m_income - m_expense
                running_balance += m_balance

                result += (
                    f"{month_name}:\n"
                    f"• Receita prevista: R$ {m_income:,.2f}\n"
                    f"• Despesa prevista: R$ {m_expense:,.2f}\n"
                    f"• Saldo mensal:     R$ {m_balance:,.2f}\n\n"
                )

            result += (
                f"Em {months} meses:\n"
                f"• Saldo acumulado: R$ {running_balance:,.2f}\n"
                f"• Média mensal:    R$ {avg_balance:,.2f}"
            )

            return result

        except Exception as e:
            return f"Erro ao gerar previsão: {str(e)}"

    def _get_savings_goals(self):
        """Retorna as metas de economia e seu progresso"""
        try:
            goals = self.db_connection.execute(
                '''SELECT name, target_amount,
                          current_amount, deadline
                   FROM savings_goals WHERE user_id = ?
                   ORDER BY deadline''',
                (self.user_id,)
            ).fetchall()

            if not goals:
                return "Não há metas de economia cadastradas"

            result = "Metas de economia:\n\n"

            for goal in goals:
                progress  = (
                    (goal['current_amount'] /
                     goal['target_amount']) * 100
                    if goal['target_amount'] > 0 else 0
                )
                remaining = (
                    goal['target_amount'] -
                    goal['current_amount']
                )

                result += (
                    f"Meta: {goal['name']}\n"
                    f"• Valor alvo:  R$ {goal['target_amount']:,.2f}\n"
                    f"• Valor atual: R$ {goal['current_amount']:,.2f}\n"
                    f"• Progresso:   {progress:.1f}%\n"
                    f"• Faltam:      R$ {remaining:,.2f}\n"
                )

                if goal['deadline']:
                    deadline_dt = datetime.strptime(
                        goal['deadline'], '%Y-%m-%d'
                    )
                    days_left = (
                        deadline_dt - datetime.now()
                    ).days

                    if days_left > 0:
                        result += (
                            f"• Prazo: {goal['deadline']} "
                            f"({days_left} dias restantes)\n"
                        )
                    else:
                        result += (
                            f"• Prazo: EXPIRADO "
                            f"({abs(days_left)} dias atrás)\n"
                        )

                result += "\n"

            return result.strip()

        except Exception as e:
            return f"Erro ao obter metas de economia: {str(e)}"

    def _get_category_comparison(self, period):
        """Retorna comparativo entre categorias de despesa"""
        try:
            start, end, period_name = self._get_date_range(period)

            categories = self.db_connection.execute(
                '''SELECT c.name, SUM(t.amount) as total
                   FROM transactions t
                   JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   GROUP BY c.name ORDER BY total DESC''',
                (self.user_id, start, end)
            ).fetchall()

            if not categories:
                return (
                    f"Não há categorias com gastos {period_name}"
                )

            total_expense = sum(
                cat['total'] for cat in categories
            )

            result = (
                f"Comparativo entre categorias "
                f"({period_name}):\n\n"
            )

            for cat in categories:
                pct = (cat['total'] / total_expense) * 100
                result += (
                    f"• {cat['name']}: "
                    f"R$ {cat['total']:,.2f} ({pct:.1f}%)\n"
                )

            result += (
                f"\nTotal de despesas: R$ {total_expense:,.2f}"
            )

            return result

        except Exception as e:
            return f"Erro ao comparar categorias: {str(e)}"

    def _get_expense_trend(self, category, months):
        """Analisa tendência de gasto em uma categoria"""
        try:
            cat_row = self.db_connection.execute(
                'SELECT id FROM categories '
                'WHERE user_id = ? AND name = ?',
                (self.user_id, category)
            ).fetchone()

            if not cat_row:
                return f"Categoria '{category}' não encontrada"

            category_id  = cat_row['id']
            today        = datetime.now()
            monthly_data = []

            for i in range(months):
                ref = (
                    today.replace(day=1) -
                    timedelta(days=i * 32)
                ).replace(day=1)

                if ref.month == 12:
                    next_m = datetime(ref.year + 1, 1, 1)
                else:
                    next_m = datetime(
                        ref.year, ref.month + 1, 1
                    )

                start = ref.strftime('%Y-%m-%d')
                end   = (
                    next_m - timedelta(days=1)
                ).strftime('%Y-%m-%d')

                total = self.db_connection.execute(
                    """SELECT SUM(amount) as total
                       FROM transactions
                       WHERE user_id = ? AND category_id = ?
                       AND transaction_type = 'saida'
                       AND date BETWEEN ? AND ?""",
                    (self.user_id, category_id, start, end)
                ).fetchone()['total'] or 0

                month_name = ref.strftime('%B %Y').capitalize()
                monthly_data.append((month_name, total))

            monthly_data.reverse()

            if not any(v > 0 for _, v in monthly_data):
                return (
                    f"Não há gastos registrados para "
                    f"'{category}' nos últimos {months} meses"
                )

            result = (
                f"Tendência de gastos em '{category}':\n\n"
            )
            for month_name, amount in monthly_data:
                result += f"• {month_name}: R$ {amount:,.2f}\n"

            values      = [v for _, v in monthly_data]
            first_value = values[0]
            last_value  = values[-1]

            trend_pct = (
                ((last_value / first_value) - 1) * 100
                if first_value > 0 else 0
            )

            result += "\nAnálise:\n"

            if trend_pct > 5:
                result += (
                    f"• AUMENTO de "
                    f"{abs(trend_pct):.1f}% no período\n"
                )
            elif trend_pct < -5:
                result += (
                    f"• REDUÇÃO de "
                    f"{abs(trend_pct):.1f}% no período\n"
                )
            else:
                result += "• ESTÁVEL no período\n"

            if len(values) >= 4:
                recent_avg = sum(values[-3:]) / 3
                prev_avg   = (
                    sum(values[:-3]) /
                    max(1, len(values) - 3)
                )
                recent_chg = (
                    ((recent_avg / prev_avg) - 1) * 100
                    if prev_avg > 0 else 0
                )

                if recent_chg > 5:
                    result += (
                        f"• AUMENTO de "
                        f"{abs(recent_chg):.1f}% recentemente\n"
                    )
                elif recent_chg < -5:
                    result += (
                        f"• REDUÇÃO de "
                        f"{abs(recent_chg):.1f}% recentemente\n"
                    )
                else:
                    result += "• ESTÁVEL recentemente\n"

            return result.strip()

        except Exception as e:
            return f"Erro ao analisar tendência: {str(e)}"

    def _get_budget_status(self, category=None):
        """Verifica status do orçamento mensal"""
        try:
            today         = datetime.now()
            current_month = today.month
            current_year  = today.year

            start = today.replace(day=1).strftime('%Y-%m-%d')
            end   = today.strftime('%Y-%m-%d')

            if current_month == 12:
                last_day = (
                    datetime(current_year + 1, 1, 1) -
                    timedelta(days=1)
                )
            else:
                last_day = (
                    datetime(current_year, current_month + 1, 1) -
                    timedelta(days=1)
                )

            days_in_month  = last_day.day
            days_passed    = today.day
            days_remaining = days_in_month - days_passed
            month_progress = (days_passed / days_in_month) * 100

            if category:
                cat_row = self.db_connection.execute(
                    'SELECT id, name FROM categories '
                    'WHERE user_id = ? AND name = ?',
                    (self.user_id, category)
                ).fetchone()

                if not cat_row:
                    return (
                        f"Categoria '{category}' não encontrada"
                    )

                budget = self.db_connection.execute(
                    '''SELECT amount FROM category_budgets
                       WHERE user_id = ? AND category_id = ?
                       AND month = ? AND year = ?''',
                    (
                        self.user_id, cat_row['id'],
                        current_month, current_year
                    )
                ).fetchone()

                if not budget:
                    return (
                        f"Não há orçamento definido para "
                        f"'{cat_row['name']}' em "
                        f"{today.strftime('%B %Y')}"
                    )

                budget_amount   = budget['amount']
                current_expense = self.db_connection.execute(
                    """SELECT SUM(amount) as total
                       FROM transactions
                       WHERE user_id = ? AND category_id = ?
                       AND transaction_type = 'saida'
                       AND date BETWEEN ? AND ?""",
                    (
                        self.user_id, cat_row['id'],
                        start, end
                    )
                ).fetchone()['total'] or 0

                remaining = budget_amount - current_expense
                percent   = (
                    (current_expense / budget_amount) * 100
                )

                if percent > month_progress + 10:
                    status = "ACIMA do esperado"
                elif percent < month_progress - 10:
                    status = "ABAIXO do esperado"
                else:
                    status = "DE ACORDO com o esperado"

                return (
                    f"Orçamento de '{cat_row['name']}' "
                    f"({today.strftime('%B %Y')}):\n\n"
                    f"• Orçado:         R$ {budget_amount:,.2f}\n"
                    f"• Gasto:          R$ {current_expense:,.2f} "
                    f"({percent:.1f}%)\n"
                    f"• Restante:       R$ {remaining:,.2f}\n"
                    f"• Status:         {status}\n"
                    f"• Mês:            "
                    f"{month_progress:.1f}% concluído\n"
                    f"• Dias restantes: {days_remaining}"
                )

            else:
                budgets = self.db_connection.execute(
                    '''SELECT cb.amount, c.id, c.name
                       FROM category_budgets cb
                       JOIN categories c
                            ON cb.category_id = c.id
                       WHERE cb.user_id = ?
                       AND cb.month = ? AND cb.year = ?''',
                    (self.user_id, current_month, current_year)
                ).fetchall()

                if not budgets:
                    return (
                        f"Não há orçamentos definidos para "
                        f"{today.strftime('%B %Y')}"
                    )

                result       = (
                    f"Status do orçamento "
                    f"({today.strftime('%B %Y')}):\n\n"
                )
                total_budget = 0
                total_spent  = 0

                for b in budgets:
                    current_expense = self.db_connection.execute(
                        """SELECT SUM(amount) as total
                           FROM transactions
                           WHERE user_id = ? AND category_id = ?
                           AND transaction_type = 'saida'
                           AND date BETWEEN ? AND ?""",
                        (self.user_id, b['id'], start, end)
                    ).fetchone()['total'] or 0

                    total_budget += b['amount']
                    total_spent  += current_expense

                    percent   = (
                        (current_expense / b['amount']) * 100
                        if b['amount'] > 0 else 0
                    )
                    remaining = b['amount'] - current_expense

                    result += (
                        f"• {b['name']}:\n"
                        f"  Orçado: R$ {b['amount']:,.2f} | "
                        f"Gasto: R$ {current_expense:,.2f} "
                        f"({percent:.1f}%) | "
                        f"Restante: R$ {remaining:,.2f}\n\n"
                    )

                budget_pct = (
                    (total_spent / total_budget) * 100
                    if total_budget > 0 else 0
                )

                if budget_pct > month_progress + 10:
                    status = "ACIMA do esperado"
                elif budget_pct < month_progress - 10:
                    status = "ABAIXO do esperado"
                else:
                    status = "DE ACORDO com o esperado"

                result += (
                    "RESUMO GERAL:\n"
                    f"• Total orçado:   R$ {total_budget:,.2f}\n"
                    f"• Total gasto:    R$ {total_spent:,.2f} "
                    f"({budget_pct:.1f}%)\n"
                    f"• Total restante: "
                    f"R$ {total_budget - total_spent:,.2f}\n"
                    f"• Mês: {month_progress:.1f}% concluído\n"
                    f"• Status geral: {status}"
                )

                return result

        except Exception as e:
            return (
                f"Erro ao verificar status do orçamento: {str(e)}"
            )

    # ----------------------------------------------------------
    # NOVOS COMANDOS
    # ----------------------------------------------------------

    def _get_emprestimos(self, status_filtro: str = "todos"):
        """Retorna empréstimos com progresso de pagamento"""
        try:
            tabela_existe = self.db_connection.execute(
                """SELECT COUNT(*) FROM sqlite_master
                   WHERE type='table' AND name='loans'"""
            ).fetchone()[0] > 0

            if not tabela_existe:
                return "Nenhum empréstimo cadastrado."

            query = """
                SELECT l.name, l.final_amount,
                       l.installment_amount,
                       l.num_installments,
                       l.status, l.start_date,
                       COALESCE(
                           (SELECT SUM(lp.amount)
                            FROM loan_payments lp
                            WHERE lp.loan_id = l.id),
                           0
                       ) as total_pago
                FROM loans l
                WHERE l.user_id = ?
            """
            params = [self.user_id]

            if status_filtro in ["ativo", "quitado"]:
                query  += " AND l.status = ?"
                params.append(status_filtro)

            query += " ORDER BY l.status ASC, l.name ASC"

            loans = self.db_connection.execute(
                query, params
            ).fetchall()

            if not loans:
                label = (
                    f" {status_filtro}"
                    if status_filtro != "todos" else ""
                )
                return f"Nenhum empréstimo{label} cadastrado."

            ativos   = [
                l for l in loans if l['status'] == 'ativo'
            ]
            quitados = [
                l for l in loans if l['status'] == 'quitado'
            ]

            result = "EMPRÉSTIMOS:\n\n"

            if ativos:
                total_divida = sum(
                    l['final_amount'] - l['total_pago']
                    for l in ativos
                )
                result += f"EM ANDAMENTO ({len(ativos)}):\n"

                for l in ativos:
                    restante = l['final_amount'] - l['total_pago']
                    pct = (
                        l['total_pago'] /
                        l['final_amount'] * 100
                        if l['final_amount'] > 0 else 0
                    )
                    result += (
                        f"• {l['name']}\n"
                        f"  Pago: R$ {l['total_pago']:,.2f} / "
                        f"R$ {l['final_amount']:,.2f} "
                        f"({pct:.0f}%)\n"
                        f"  Restante: R$ {restante:,.2f}\n"
                        f"  Parcela : "
                        f"R$ {l['installment_amount']:,.2f}\n"
                    )

                result += (
                    f"\nTotal em dívidas: "
                    f"R$ {total_divida:,.2f}\n"
                )

            if quitados:
                result += f"\nQUITADOS ({len(quitados)}):\n"
                for l in quitados:
                    result += (
                        f"• {l['name']} — "
                        f"R$ {l['final_amount']:,.2f}\n"
                    )

            return result

        except Exception as e:
            return f"Erro ao obter empréstimos: {str(e)}"

    def _get_historico_mensal(self, meses: int = 3):
        """Retorna histórico mensal para análise de tendência"""
        try:
            hoje   = datetime.now()
            inicio = (
                hoje.replace(day=1) -
                timedelta(days=meses * 31)
            ).strftime('%Y-%m-%d')

            rows = self.db_connection.execute(
                """SELECT strftime('%Y-%m', date) as mes,
                          SUM(CASE WHEN transaction_type='entrada'
                              THEN amount ELSE 0 END) as entradas,
                          SUM(CASE WHEN transaction_type='saida'
                              THEN amount ELSE 0 END) as saidas,
                          COUNT(*) as qtd_transacoes
                   FROM transactions
                   WHERE user_id = ? AND date >= ?
                   GROUP BY mes
                   ORDER BY mes ASC""",
                (self.user_id, inicio)
            ).fetchall()

            if not rows:
                return "Dados históricos insuficientes."

            result = f"HISTÓRICO {meses} MESES:\n\n"
            for r in rows:
                saldo = r['entradas'] - r['saidas']
                result += (
                    f"• {r['mes']}\n"
                    f"  Receitas  : R$ {r['entradas']:,.2f}\n"
                    f"  Despesas  : R$ {r['saidas']:,.2f}\n"
                    f"  Saldo     : R$ {saldo:,.2f}\n"
                    f"  Transações: {r['qtd_transacoes']}\n\n"
                )

            media_entrada = (
                sum(r['entradas'] for r in rows) / len(rows)
            )
            media_saida = (
                sum(r['saidas'] for r in rows) / len(rows)
            )
            result += (
                f"MÉDIAS:\n"
                f"• Receita média : R$ {media_entrada:,.2f}\n"
                f"• Despesa média : R$ {media_saida:,.2f}\n"
                f"• Saldo médio   : "
                f"R$ {media_entrada - media_saida:,.2f}"
            )

            return result

        except Exception as e:
            return f"Erro ao obter histórico: {str(e)}"

    def _get_resumo_completo(self):
        """
        Retorna resumo financeiro completo.
        Usado quando o servidor precisa de visão geral
        para responder perguntas complexas.
        """
        try:
            hoje    = datetime.now()
            ini_mes = hoje.replace(day=1).strftime('%Y-%m-%d')
            fim_mes = hoje.strftime('%Y-%m-%d')

            # ── Saldo geral ───────────────────────────────────
            rows = self.db_connection.execute(
                """SELECT transaction_type, SUM(amount) as total
                   FROM transactions WHERE user_id = ?
                   GROUP BY transaction_type""",
                (self.user_id,)
            ).fetchall()

            entradas = saidas = 0
            for r in rows:
                if r['transaction_type'] == 'entrada':
                    entradas = r['total'] or 0
                else:
                    saidas   = r['total'] or 0

            saldo = entradas - saidas

            # ── Mês atual ─────────────────────────────────────
            rows_mes = self.db_connection.execute(
                """SELECT transaction_type, SUM(amount) as total
                   FROM transactions
                   WHERE user_id = ?
                   AND date BETWEEN ? AND ?
                   GROUP BY transaction_type""",
                (self.user_id, ini_mes, fim_mes)
            ).fetchall()

            ent_mes = sai_mes = 0
            for r in rows_mes:
                if r['transaction_type'] == 'entrada':
                    ent_mes = r['total'] or 0
                else:
                    sai_mes = r['total'] or 0

            # ── Top categorias do mês ─────────────────────────
            cats = self.db_connection.execute(
                """SELECT c.name, SUM(t.amount) as total
                   FROM transactions t
                   LEFT JOIN categories c
                          ON t.category_id = c.id
                   WHERE t.user_id = ?
                   AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   GROUP BY c.name
                   ORDER BY total DESC
                   LIMIT 5""",
                (self.user_id, ini_mes, fim_mes)
            ).fetchall()

            # ── Metas ─────────────────────────────────────────
            metas = self.db_connection.execute(
                """SELECT name, target_amount, current_amount
                   FROM savings_goals WHERE user_id = ?""",
                (self.user_id,)
            ).fetchall()

            guardado = sum(
                m['current_amount'] for m in metas
            )

            result = (
                f"RESUMO FINANCEIRO COMPLETO "
                f"({hoje.strftime('%d/%m/%Y')}):\n\n"
                f"SALDO GERAL:\n"
                f"• Total     : R$ {saldo:,.2f}\n"
                f"• Guardado  : R$ {guardado:,.2f}\n"
                f"• Disponível: R$ {saldo - guardado:,.2f}\n\n"
                f"MÊS ATUAL "
                f"({hoje.strftime('%B/%Y').upper()}):\n"
                f"• Receitas : R$ {ent_mes:,.2f}\n"
                f"• Despesas : R$ {sai_mes:,.2f}\n"
                f"• Saldo mês: R$ {ent_mes - sai_mes:,.2f}\n"
            )

            if cats:
                result += "\nTOP CATEGORIAS DO MÊS:\n"
                for c in cats:
                    result += (
                        f"• {c['name'] or 'Sem categoria'}: "
                        f"R$ {c['total']:,.2f}\n"
                    )

            if metas:
                result += "\nMETAS DE ECONOMIA:\n"
                for m in metas:
                    pct = (
                        m['current_amount'] /
                        m['target_amount'] * 100
                        if m['target_amount'] > 0 else 0
                    )
                    result += (
                        f"• {m['name']}: "
                        f"R$ {m['current_amount']:,.2f} / "
                        f"R$ {m['target_amount']:,.2f} "
                        f"({pct:.0f}%)\n"
                    )

            # ── Empréstimos ativos ────────────────────────────
            try:
                tabela_existe = self.db_connection.execute(
                    """SELECT COUNT(*) FROM sqlite_master
                       WHERE type='table' AND name='loans'"""
                ).fetchone()[0] > 0

                if tabela_existe:
                    loans = self.db_connection.execute(
                        """SELECT l.name, l.final_amount,
                                  COALESCE(
                                      (SELECT SUM(lp.amount)
                                       FROM loan_payments lp
                                       WHERE lp.loan_id = l.id),
                                      0
                                  ) as total_pago
                           FROM loans l
                           WHERE l.user_id = ?
                           AND l.status = 'ativo'""",
                        (self.user_id,)
                    ).fetchall()

                    if loans:
                        total_divida = sum(
                            l['final_amount'] - l['total_pago']
                            for l in loans
                        )
                        result += (
                            f"\nEMPRÉSTIMOS ATIVOS "
                            f"({len(loans)}):\n"
                        )
                        for l in loans:
                            restante = (
                                l['final_amount'] -
                                l['total_pago']
                            )
                            result += (
                                f"• {l['name']}: "
                                f"R$ {restante:,.2f} restante\n"
                            )
                        result += (
                            f"Total em dívidas: "
                            f"R$ {total_divida:,.2f}\n"
                        )
            except Exception:
                pass

            return result

        except Exception as e:
            return f"Erro ao gerar resumo: {str(e)}"
