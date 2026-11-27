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

# Rede local (HTTPS)
LOCAL_IP   = "10.0.0.254"
LOCAL_PORT = 5010
LOCAL_URL  = f"https://{LOCAL_IP}:{LOCAL_PORT}"

# Rede Tor (HTTP via onion)
ONION_HOST = "yc2jq3yzelefsjcwrau5p3y5pcmclf2nf2vume3yckpw6h5a4rspu7id.onion/login"
ONION_PORT = 80
ONION_URL  = f"http://{ONION_HOST}:{ONION_PORT}"

# Intervalo de polling (segundos)
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
        "parametros": "categoria=nome&periodo=mes|ano|todos (padrão: mes)",
        "exemplo":    "GET_GASTOS_CATEGORIA=alimentacao&mes → R$ 450,00"
    },
    {
        "comando":    "GET_TRANSACOES_RECENTES",
        "descricao":  "Lista as transações mais recentes. "
                      "Use quando o usuário pedir para ver transações "
                      "recentes, últimos gastos ou movimentações.",
        "parametros": "quantidade=N (padrão: 5)",
        "exemplo":    "GET_TRANSACOES_RECENTES=3 → 3 transações mais recentes"
    },
    {
        "comando":    "GET_MAIORES_GASTOS",
        "descricao":  "Lista as maiores despesas em um período. "
                      "Use quando o usuário perguntar sobre maiores gastos "
                      "ou onde está gastando mais dinheiro.",
        "parametros": "periodo=mes|ano|todos&limite=N (padrão: mes,5)",
        "exemplo":    "GET_MAIORES_GASTOS=mes&3 → 3 maiores gastos do mês"
    },
    {
        "comando":    "GET_BALANCO_MENSAL",
        "descricao":  "Retorna balanço financeiro mensal (receitas vs despesas). "
                      "Use quando o usuário pedir balanço, fluxo de caixa "
                      "ou comparativo de entradas e saídas.",
        "parametros": "mes=MM&ano=AAAA (padrão: mês e ano atuais)",
        "exemplo":    "GET_BALANCO_MENSAL=04&2026 → Balanço de abril/2026"
    },
    {
        "comando":    "GET_PREVISAO_GASTOS",
        "descricao":  "Retorna previsão de gastos futuros baseada nos padrões. "
                      "Use quando o usuário perguntar sobre previsão, projeção "
                      "ou quanto vai gastar nos próximos meses.",
        "parametros": "meses=N (padrão: 1)",
        "exemplo":    "GET_PREVISAO_GASTOS=3 → Previsão para os próximos 3 meses"
    },
    {
        "comando":    "GET_METAS_ECONOMIA",
        "descricao":  "Lista as metas de economia e seu progresso. "
                      "Use quando o usuário perguntar sobre metas, "
                      "progresso de poupança ou objetivos financeiros.",
        "parametros": "nenhum",
        "exemplo":    "GET_METAS_ECONOMIA → Lista todas as metas"
    },
    {
        "comando":    "GET_COMPARATIVO_CATEGORIAS",
        "descricao":  "Compara gastos entre categorias. "
                      "Use quando o usuário quiser comparar gastos "
                      "entre diferentes categorias.",
        "parametros": "periodo=mes|ano (padrão: mes)",
        "exemplo":    "GET_COMPARATIVO_CATEGORIAS=mes → Comparativo do mês"
    },
    {
        "comando":    "GET_TENDENCIA_GASTO",
        "descricao":  "Analisa tendência de gasto em uma categoria. "
                      "Use quando o usuário perguntar se está gastando "
                      "mais ou menos em determinada área.",
        "parametros": "categoria=nome&meses=N (padrão: meses=3)",
        "exemplo":    "GET_TENDENCIA_GASTO=alimentacao&6 → Tendência 6 meses"
    },
    {
        "comando":    "GET_ORCAMENTO_STATUS",
        "descricao":  "Verifica status do orçamento mensal. "
                      "Use quando o usuário perguntar sobre orçamento, "
                      "quanto ainda pode gastar ou se está no orçado.",
        "parametros": "categoria=nome (opcional)",
        "exemplo":    "GET_ORCAMENTO_STATUS=lazer → Status do orçamento lazer"
    }
]


# ============================================================
# CLASSE PRINCIPAL
# ============================================================

class FinancialAI:
    """
    Sistema de IA integrado ao sistema de gestão financeira.

    Detecta automaticamente se está na rede local (usa HTTPS)
    ou em rede externa (usa Tor/HTTP onion).

    A API Key é fornecida pelo usuário via interface e
    armazenada no banco de dados.
    """

    def __init__(self, db_connection, user_id):
        self.db_connection  = db_connection
        self.user_id        = user_id
        self.device_id      = None
        self.running        = False
        self.use_tor        = False
        self.base_url       = None
        self.api_key        = self._load_api_key()

        self.session = requests.Session()
        self.session.verify = False  # Local usa HTTPS com cert próprio

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
        Detecta automaticamente se está na rede local ou externa.

        - Tenta conexão TCP com o servidor local (HTTPS)
        - Se falhar, configura para usar Tor (onion)

        Returns:
            bool: True se detectou rede disponível
        """
        print("[FinancialAI] Detectando rede disponível...")

        # Tentar rede local primeiro
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((LOCAL_IP, LOCAL_PORT))
            s.close()

            self.base_url = LOCAL_URL
            self.use_tor  = False

            print(f"[FinancialAI] ✅ Rede local detectada → {LOCAL_URL}")
            return True

        except (socket.timeout, socket.error, OSError):
            print("[FinancialAI] Rede local indisponível, tentando Tor...")

        # Tentar via Tor
        try:
            tor_session = requests.Session()
            tor_session.proxies = {
                'http':  'socks5h://localhost:9050',
                'https': 'socks5h://localhost:9050'
            }
            tor_session.get(
                f"http://check.torproject.org",
                timeout=10
            )

            self.base_url = ONION_URL
            self.use_tor  = True

            # Atualizar sessão com proxy Tor
            self.session.proxies = {
                'http':  'socks5h://localhost:9050',
                'https': 'socks5h://localhost:9050'
            }

            print(f"[FinancialAI] ✅ Tor disponível → {ONION_URL}")
            return True

        except Exception as e:
            print(f"[FinancialAI] ❌ Tor indisponível: {e}")

        print("[FinancialAI] ❌ Nenhuma rede disponível")
        return False

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
                network_type   = "Tor" if self.use_tor else "Rede Local"
                print(
                    f"[FinancialAI] ✅ Registrado via {network_type} "
                    f"| ID: {self.device_id}"
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
            print(f"[FinancialAI] ✅ Sistema iniciado via {network_type}")
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
                    f"{self.base_url}/api/servico/heartbeat/{self.device_id}",
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
                    f"{self.base_url}/api/servico/comandos/{self.device_id}",
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
                print(f"[FinancialAI] Erro no loop de comandos: {e}")

            time.sleep(POLL_INTERVAL)

    # ----------------------------------------------------------
    # PROCESSAMENTO DE COMANDOS
    # ----------------------------------------------------------

    def process_command(self, command, parameters):
        """
        Processa comandos recebidos do servidor de IA

        Args:
            command    (str): Comando a ser executado
            parameters (str): Parâmetros do comando

        Returns:
            str: Resultado da execução
        """
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
            period = parameters if parameters in ["mes", "ano"] else "mes"
            return self._get_category_comparison(period)

        elif command == "GET_TENDENCIA_GASTO":
            params   = self._parse_parameters(parameters)
            category = params.get("categoria", "")
            months   = int(params.get("meses", "3"))
            return self._get_expense_trend(category, months)

        elif command == "GET_ORCAMENTO_STATUS":
            category = parameters if parameters else None
            return self._get_budget_status(category)

        else:
            return (
                f"Comando '{command}' não reconhecido. "
                f"Parâmetros: '{parameters}'"
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
        """
        Retorna (start_date, end_date, period_name) para um período

        Args:
            period (str): 'mes', 'ano' ou 'todos'

        Returns:
            tuple: (start_date str, end_date str, period_name str)
        """
        today = datetime.now()

        if period == "mes":
            start = today.replace(day=1).strftime('%Y-%m-%d')
            end   = today.strftime('%Y-%m-%d')
            name  = "este mês"
        elif period == "ano":
            start = today.replace(month=1, day=1).strftime('%Y-%m-%d')
            end   = today.strftime('%Y-%m-%d')
            name  = "este ano"
        else:
            start = "2000-01-01"
            end   = today.strftime('%Y-%m-%d')
            name  = "todo o período"

        return start, end, name

    # ----------------------------------------------------------
    # IMPLEMENTAÇÃO DOS COMANDOS
    # ----------------------------------------------------------

    def _get_balance(self):
        """Retorna o saldo atual da conta"""
        try:
            transactions = self.db_connection.execute(
                'SELECT transaction_type, amount FROM transactions '
                'WHERE user_id = ?',
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

            # Total guardado em metas
            savings_row = self.db_connection.execute(
                'SELECT SUM(current_amount) as total FROM savings_goals '
                'WHERE user_id = ?',
                (self.user_id,)
            ).fetchone()

            savings = savings_row['total'] if savings_row['total'] else 0
            available = balance - savings

            return (
                f"Saldo total: R$ {balance:.2f}\n"
                f"Guardado em metas: R$ {savings:.2f}\n"
                f"Saldo disponível: R$ {available:.2f}"
            )

        except Exception as e:
            return f"Erro ao obter saldo: {str(e)}"

    def _get_category_expenses(self, category, period):
        """Retorna gastos de uma categoria específica"""
        try:
            start, end, period_name = self._get_date_range(period)

            cat_row = self.db_connection.execute(
                'SELECT id FROM categories WHERE user_id = ? AND name = ?',
                (self.user_id, category)
            ).fetchone()

            if not cat_row:
                return f"Categoria '{category}' não encontrada"

            total = self.db_connection.execute(
                """SELECT SUM(amount) as total FROM transactions
                   WHERE user_id = ? AND category_id = ?
                   AND transaction_type = 'saida'
                   AND date BETWEEN ? AND ?""",
                (self.user_id, cat_row['id'], start, end)
            ).fetchone()['total'] or 0

            # Calcular média mensal
            today = datetime.now()
            months = max(1, (
                (today.year - int(start[:4])) * 12 +
                (today.month - int(start[5:7])) + 1
            ))
            avg = total / months if period != "mes" else total

            return (
                f"Gastos em '{category}' ({period_name}): "
                f"R$ {total:.2f}\n"
                f"Média mensal: R$ {avg:.2f}"
            )

        except Exception as e:
            return f"Erro ao obter gastos da categoria: {str(e)}"

    def _get_recent_transactions(self, limit):
        """Retorna as transações mais recentes"""
        try:
            transactions = self.db_connection.execute(
                '''SELECT t.amount, t.description, t.transaction_type,
                          t.date, c.name as category_name
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
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
                    "Receita" if t['transaction_type'] == 'entrada'
                    else "Despesa"
                )
                result += (
                    f"• {t['date']} | {t['description']}\n"
                    f"  {tipo}: R$ {t['amount']:.2f}"
                )
                if t['category_name']:
                    result += f" | {t['category_name']}"
                result += "\n\n"

            return result.strip()

        except Exception as e:
            return f"Erro ao obter transações recentes: {str(e)}"

    def _get_top_expenses(self, period, limit):
        """Retorna as maiores despesas em um período"""
        try:
            start, end, period_name = self._get_date_range(period)

            expenses = self.db_connection.execute(
                '''SELECT t.amount, t.description, t.date,
                          c.name as category_name
                   FROM transactions t
                   LEFT JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ? AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   ORDER BY t.amount DESC
                   LIMIT ?''',
                (self.user_id, start, end, limit)
            ).fetchall()

            if not expenses:
                return f"Não há despesas registradas {period_name}"

            result = f"Maiores despesas {period_name}:\n\n"

            for i, e in enumerate(expenses, 1):
                result += (
                    f"{i}. R$ {e['amount']:.2f} - {e['description']}\n"
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
                start = datetime(year, month, 1).strftime('%Y-%m-%d')
                if month == 12:
                    end = datetime(year + 1, 1, 1) - timedelta(days=1)
                else:
                    end = datetime(year, month + 1, 1) - timedelta(days=1)
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

            income  = 0
            expense = 0
            for r in results:
                if r['transaction_type'] == 'entrada':
                    income = r['total']
                elif r['transaction_type'] == 'saida':
                    expense = r['total']

            balance = income - expense

            top_cats = self.db_connection.execute(
                '''SELECT c.name, SUM(t.amount) as total
                   FROM transactions t
                   JOIN categories c ON t.category_id = c.id
                   WHERE t.user_id = ? AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   GROUP BY c.name ORDER BY total DESC LIMIT 3''',
                (self.user_id, start, end)
            ).fetchall()

            month_name = datetime(year, month, 1).strftime('%B').capitalize()

            result = (
                f"Balanço de {month_name}/{year}:\n\n"
                f"Receitas: R$ {income:.2f}\n"
                f"Despesas: R$ {expense:.2f}\n"
                f"Saldo: R$ {balance:.2f}"
            )

            if top_cats:
                result += "\n\nPrincipais categorias de despesa:"
                for cat in top_cats:
                    result += f"\n• {cat['name']}: R$ {cat['total']:.2f}"

            return result

        except Exception as e:
            return f"Erro ao calcular balanço mensal: {str(e)}"

    def _get_expense_forecast(self, months):
        """Retorna previsão de gastos futuros"""
        try:
            today           = datetime.now()
            three_months_ago = (
                today - timedelta(days=90)
            ).strftime('%Y-%m-%d')

            monthly_stats = self.db_connection.execute(
                '''SELECT strftime('%Y-%m', date) as month,
                          SUM(CASE WHEN transaction_type='entrada'
                               THEN amount ELSE 0 END) as income,
                          SUM(CASE WHEN transaction_type='saida'
                               THEN amount ELSE 0 END) as expense
                   FROM transactions
                   WHERE user_id = ? AND date >= ?
                   GROUP BY month''',
                (self.user_id, three_months_ago)
            ).fetchall()

            if not monthly_stats:
                return "Dados insuficientes para previsão"

            avg_income  = (
                sum(m['income']  for m in monthly_stats) / len(monthly_stats)
            )
            avg_expense = (
                sum(m['expense'] for m in monthly_stats) / len(monthly_stats)
            )
            avg_balance = avg_income - avg_expense

            result           = f"Previsão para os próximos {months} meses:\n\n"
            running_balance  = 0
            variation        = 0.05

            for i in range(1, months + 1):
                # Calcular próximo mês
                next_month = (
                    today.replace(day=1) +
                    timedelta(days=32 * i)
                ).replace(day=1)

                month_name = next_month.strftime('%B %Y').capitalize()

                m_income  = avg_income  * (1 + random.uniform(-variation, variation))
                m_expense = avg_expense * (1 + random.uniform(-variation, variation))
                m_balance = m_income - m_expense
                running_balance += m_balance

                result += (
                    f"{month_name}:\n"
                    f"• Receita prevista: R$ {m_income:.2f}\n"
                    f"• Despesa prevista: R$ {m_expense:.2f}\n"
                    f"• Saldo mensal:     R$ {m_balance:.2f}\n\n"
                )

            result += (
                f"Em {months} meses:\n"
                f"• Saldo acumulado: R$ {running_balance:.2f}\n"
                f"• Média mensal:    R$ {avg_balance:.2f}"
            )

            return result

        except Exception as e:
            return f"Erro ao gerar previsão: {str(e)}"

    def _get_savings_goals(self):
        """Retorna as metas de economia e seu progresso"""
        try:
            goals = self.db_connection.execute(
                '''SELECT name, target_amount, current_amount, deadline
                   FROM savings_goals WHERE user_id = ?
                   ORDER BY deadline''',
                (self.user_id,)
            ).fetchall()

            if not goals:
                return "Não há metas de economia cadastradas"

            result = "Metas de economia:\n\n"

            for goal in goals:
                progress  = (
                    (goal['current_amount'] / goal['target_amount']) * 100
                    if goal['target_amount'] > 0 else 0
                )
                remaining = goal['target_amount'] - goal['current_amount']

                result += (
                    f"Meta: {goal['name']}\n"
                    f"• Valor alvo:  R$ {goal['target_amount']:.2f}\n"
                    f"• Valor atual: R$ {goal['current_amount']:.2f}\n"
                    f"• Progresso:   {progress:.1f}%\n"
                    f"• Faltam:      R$ {remaining:.2f}\n"
                )

                if goal['deadline']:
                    deadline_dt = datetime.strptime(
                        goal['deadline'], '%Y-%m-%d'
                    )
                    days_left = (deadline_dt - datetime.now()).days

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
                   WHERE t.user_id = ? AND t.transaction_type = 'saida'
                   AND t.date BETWEEN ? AND ?
                   GROUP BY c.name ORDER BY total DESC''',
                (self.user_id, start, end)
            ).fetchall()

            if not categories:
                return f"Não há categorias com gastos {period_name}"

            total_expense = sum(cat['total'] for cat in categories)

            result = f"Comparativo entre categorias ({period_name}):\n\n"

            for cat in categories:
                pct = (cat['total'] / total_expense) * 100
                result += (
                    f"• {cat['name']}: "
                    f"R$ {cat['total']:.2f} ({pct:.1f}%)\n"
                )

            result += f"\nTotal de despesas: R$ {total_expense:.2f}"

            return result

        except Exception as e:
            return f"Erro ao comparar categorias: {str(e)}"

    def _get_expense_trend(self, category, months):
        """Analisa tendência de gasto em uma categoria"""
        try:
            cat_row = self.db_connection.execute(
                'SELECT id FROM categories WHERE user_id = ? AND name = ?',
                (self.user_id, category)
            ).fetchone()

            if not cat_row:
                return f"Categoria '{category}' não encontrada"

            category_id  = cat_row['id']
            today        = datetime.now()
            monthly_data = []

            for i in range(months):
                ref = (
                    today.replace(day=1) - timedelta(days=i * 32)
                ).replace(day=1)

                if ref.month == 12:
                    next_m = datetime(ref.year + 1, 1, 1)
                else:
                    next_m = datetime(ref.year, ref.month + 1, 1)

                start = ref.strftime('%Y-%m-%d')
                end   = (next_m - timedelta(days=1)).strftime('%Y-%m-%d')

                total = self.db_connection.execute(
                    """SELECT SUM(amount) as total FROM transactions
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
                    f"Não há gastos registrados para '{category}' "
                    f"nos últimos {months} meses"
                )

            result = f"Tendência de gastos em '{category}':\n\n"
            for month_name, amount in monthly_data:
                result += f"• {month_name}: R$ {amount:.2f}\n"

            # Calcular tendência
            values      = [v for _, v in monthly_data]
            first_value = values[0]
            last_value  = values[-1]

            trend_pct = (
                ((last_value / first_value) - 1) * 100
                if first_value > 0 else 0
            )

            result += "\nAnálise:\n"

            if trend_pct > 5:
                result += f"• AUMENTO de {abs(trend_pct):.1f}% no período\n"
            elif trend_pct < -5:
                result += f"• REDUÇÃO de {abs(trend_pct):.1f}% no período\n"
            else:
                result += "• ESTÁVEL no período\n"

            # Tendência recente (últimos 3 meses vs anteriores)
            if len(values) >= 4:
                recent_avg  = sum(values[-3:]) / 3
                prev_avg    = sum(values[:-3]) / max(1, len(values) - 3)
                recent_chg  = (
                    ((recent_avg / prev_avg) - 1) * 100
                    if prev_avg > 0 else 0
                )

                if recent_chg > 5:
                    result += f"• AUMENTO de {abs(recent_chg):.1f}% recentemente\n"
                elif recent_chg < -5:
                    result += f"• REDUÇÃO de {abs(recent_chg):.1f}% recentemente\n"
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

            # Dias do mês para calcular progresso
            if current_month == 12:
                last_day = datetime(current_year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(
                    current_year, current_month + 1, 1
                ) - timedelta(days=1)

            days_in_month  = last_day.day
            days_passed    = today.day
            days_remaining = days_in_month - days_passed
            month_progress = (days_passed / days_in_month) * 100

            if category:
                # Orçamento de uma categoria específica
                cat_row = self.db_connection.execute(
                    'SELECT id, name FROM categories '
                    'WHERE user_id = ? AND name = ?',
                    (self.user_id, category)
                ).fetchone()

                if not cat_row:
                    return f"Categoria '{category}' não encontrada"

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
                    """SELECT SUM(amount) as total FROM transactions
                       WHERE user_id = ? AND category_id = ?
                       AND transaction_type = 'saida'
                       AND date BETWEEN ? AND ?""",
                    (self.user_id, cat_row['id'], start, end)
                ).fetchone()['total'] or 0

                remaining   = budget_amount - current_expense
                percent     = (current_expense / budget_amount) * 100

                if percent > month_progress + 10:
                    status = "ACIMA do esperado"
                elif percent < month_progress - 10:
                    status = "ABAIXO do esperado"
                else:
                    status = "DE ACORDO com o esperado"

                return (
                    f"Orçamento de '{cat_row['name']}' "
                    f"({today.strftime('%B %Y')}):\n\n"
                    f"• Orçado:            R$ {budget_amount:.2f}\n"
                    f"• Gasto:             R$ {current_expense:.2f} "
                    f"({percent:.1f}%)\n"
                    f"• Restante:          R$ {remaining:.2f}\n"
                    f"• Status:            {status}\n"
                    f"• Mês:               {month_progress:.1f}% concluído\n"
                    f"• Dias restantes:    {days_remaining}"
                )

            else:
                # Todos os orçamentos do mês
                budgets = self.db_connection.execute(
                    '''SELECT cb.amount, c.id, c.name
                       FROM category_budgets cb
                       JOIN categories c ON cb.category_id = c.id
                       WHERE cb.user_id = ? AND cb.month = ? AND cb.year = ?''',
                    (self.user_id, current_month, current_year)
                ).fetchall()

                if not budgets:
                    return (
                        f"Não há orçamentos definidos para "
                        f"{today.strftime('%B %Y')}"
                    )

                result        = (
                    f"Status do orçamento ({today.strftime('%B %Y')}):\n\n"
                )
                total_budget  = 0
                total_spent   = 0

                for b in budgets:
                    current_expense = self.db_connection.execute(
                        """SELECT SUM(amount) as total FROM transactions
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
                        f"  Orçado: R$ {b['amount']:.2f} | "
                        f"Gasto: R$ {current_expense:.2f} ({percent:.1f}%) | "
                        f"Restante: R$ {remaining:.2f}\n\n"
                    )

                # Resumo geral
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
                    f"• Total orçado:  R$ {total_budget:.2f}\n"
                    f"• Total gasto:   R$ {total_spent:.2f} "
                    f"({budget_pct:.1f}%)\n"
                    f"• Total restante: R$ {total_budget - total_spent:.2f}\n"
                    f"• Mês: {month_progress:.1f}% concluído\n"
                    f"• Status geral: {status}"
                )

                return result

        except Exception as e:
            return f"Erro ao verificar status do orçamento: {str(e)}"
