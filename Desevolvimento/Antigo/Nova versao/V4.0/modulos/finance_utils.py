"""
Utilitários financeiros - cotações, conversão de moedas
"""
from datetime import datetime

try:
    import yfinance as yf
except ImportError:
    yf = None


class FinanceDataUtility:
    """Busca dados financeiros usando yfinance"""

    @staticmethod
    def get_stock_data(ticker, period="1d"):
        """Obtém dados de um ativo"""
        if yf is None:
            return {
                "success": False,
                "error": "yfinance não instalado. Execute: pip install yfinance"
            }
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period=period)

            if hist.empty:
                return {"success": False, "error": "Sem dados para este ativo"}

            first_price = hist['Close'].iloc[0]
            last_price = hist['Close'].iloc[-1]
            change_percent = ((last_price / first_price) - 1) * 100

            return {
                "success": True,
                "ticker": ticker,
                "name": info.get('shortName', info.get('longName', ticker)),
                "sector": info.get('sector', 'N/A'),
                "currency": info.get('currency', 'USD'),
                "current_price": last_price,
                "change_percent": change_percent,
                "market_cap": info.get('marketCap', 'N/A'),
                "volume": info.get('volume', 'N/A'),
                "history": {
                    "dates": hist.index.strftime('%Y-%m-%d').tolist(),
                    "prices": hist['Close'].tolist(),
                    "volumes": hist['Volume'].tolist()
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def convert_currency(amount, from_currency, to_currency):
        """Converte valor entre moedas"""
        if yf is None:
            return {"success": False, "error": "yfinance não instalado"}

        try:
            if from_currency == to_currency:
                return {
                    "success": True,
                    "original_amount": amount,
                    "original_currency": from_currency,
                    "converted_amount": amount,
                    "target_currency": to_currency,
                    "exchange_rate": 1.0
                }

            currency_map = {"REAL": "BRL", "DOLAR": "USD", "EURO": "EUR"}
            from_currency = currency_map.get(
                from_currency.upper(), from_currency.upper()
            )
            to_currency = currency_map.get(
                to_currency.upper(), to_currency.upper()
            )

            ticker = f"{from_currency}{to_currency}=X"
            data = yf.download(ticker, period="1d", progress=False)

            if not data.empty and 'Close' in data.columns:
                exchange_rate = data['Close'].iloc[-1]
                return {
                    "success": True,
                    "original_amount": amount,
                    "original_currency": from_currency,
                    "converted_amount": amount * exchange_rate,
                    "target_currency": to_currency,
                    "exchange_rate": exchange_rate,
                    "date": data.index[-1].strftime('%Y-%m-%d')
                }

            # Tentar inverso
            ticker_inv = f"{to_currency}{from_currency}=X"
            data = yf.download(ticker_inv, period="1d", progress=False)

            if not data.empty and 'Close' in data.columns:
                rate = 1 / data['Close'].iloc[-1]
                return {
                    "success": True,
                    "original_amount": amount,
                    "original_currency": from_currency,
                    "converted_amount": amount * rate,
                    "target_currency": to_currency,
                    "exchange_rate": rate,
                    "date": data.index[-1].strftime('%Y-%m-%d')
                }

            return {
                "success": False,
                "error": f"Sem taxa entre {from_currency} e {to_currency}"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_market_summary():
        """Obtém resumo dos principais índices"""
        if yf is None:
            return {"success": False, "error": "yfinance não instalado"}

        try:
            indices = {
                "^BVSP": "IBOVESPA",
                "^IXIC": "NASDAQ",
                "^GSPC": "S&P 500",
                "^DJI": "Dow Jones",
                "BTC-USD": "Bitcoin",
                "GC=F": "Ouro"
            }

            data = yf.download(list(indices.keys()), period="2d")
            price_col = 'Adj Close' if 'Adj Close' in data.columns else 'Close'

            results = []
            for ticker, name in indices.items():
                try:
                    current = data[price_col][ticker].iloc[-1]
                    prev = data[price_col][ticker].iloc[-2]
                    change = ((current / prev) - 1) * 100
                    results.append({
                        "ticker": ticker,
                        "name": name,
                        "current_price": current,
                        "change_percent": change
                    })
                except Exception:
                    continue

            return {
                "success": True,
                "last_update": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "indices": results
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
