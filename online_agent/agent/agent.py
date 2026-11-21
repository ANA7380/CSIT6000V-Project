"""Offline, deterministic ticker agent. Python 3.9+, standard library only."""
import argparse
import csv
import json
import math
import re
import statistics
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class TickerAgent:
    def __init__(self, data_dir=ROOT / "data"):
        self.snapshot = {r["symbol"]: r for r in read_csv(data_dir / "hk_tech30_snapshot.csv")}
        self.financials = read_csv(data_dir / "hk_tech30_financials.csv")
        self.prices = read_csv(data_dir / "hk_tech30_daily_prices.csv")

    def normalize(self, ticker):
        ticker = ticker.strip().upper()
        if re.fullmatch(r"\d{1,5}(?:\.HK)?", ticker):
            ticker = f"{int(ticker.split('.')[0]):04d}.HK"
        if ticker not in self.snapshot:
            raise ValueError(f"Unknown ticker: {ticker}. Use --list to see available tickers.")
        return ticker

    def run(self, ticker, window=252):
        if type(window) is not int or not 2 <= window <= 5000:
            raise ValueError("Volatility window must be at least 2 returns.")
        symbol = self.normalize(ticker)
        row = self.snapshot[symbol]
        metrics = {}

        def ratio(name, numerator, denominator, formula, context, percent=False):
            a, b = number(row[numerator]), number(row[denominator])
            result = dict(value=None, unit="%" if percent else "x", formula=formula,
                          inputs={numerator: a, denominator: b}, **context)
            if a is None or b is None:
                result.update(status="unavailable", reason="Required financial input is missing.")
            elif b <= 0:
                result.update(status="unavailable", reason="Denominator is zero or negative; ratio is not meaningful.")
            else:
                value = (a / b - 1) if name == "Revenue growth" else a / b
                result.update(value=value * (100 if percent else 1), status="ok")
            metrics[name] = result

        income = dict(period_end=row["financial_period_end"], period_type=row["financial_period_type"],
                      currency=row["financial_currency"], source_url=row["income_statement_source_url"])
        ratio("Revenue growth", "revenue", "prior_year_revenue", "(revenue / prior-year revenue - 1) * 100",
              dict(**income, prior_period_end=row["prior_year_period_end"]), True)
        growth = metrics["Revenue growth"]
        if growth["status"] == "ok":
            current, previous = date.fromisoformat(income["period_end"]), date.fromisoformat(row["prior_year_period_end"])
            if not (current.year - previous.year == 1 and current.month == previous.month and abs(current.day - previous.day) <= 1):
                growth.update(value=None, status="unavailable", reason="Prior revenue is not a matching year-over-year period.")
        ratio("Net profit margin", "net_income", "revenue", "net income / revenue * 100", income, True)
        ratio("Debt-to-equity", "total_debt", "stockholders_equity", "total debt / stockholders equity",
              dict(period_end=row["balance_sheet_date"], currency=row["balance_sheet_currency"],
                   source_url=row["balance_sheet_source_url"]))

        prices = sorted((p for p in self.prices if p["symbol"] == symbol), key=lambda p: p["date"])
        selected = prices[-(window + 1):]
        values = [number(p["adjusted_close"]) for p in selected]
        volatility = dict(value=None, unit="%", formula="sample stdev(log(adjusted_close[t] / adjusted_close[t-1])) * sqrt(252) * 100",
                          requested_returns=window, observations=len(selected), annualization_days=252,
                          start_date=selected[0]["date"] if selected else None,
                          end_date=selected[-1]["date"] if selected else None,
                          source_url=row["price_source_url"])
        if len(values) < 3:
            volatility.update(status="unavailable", reason="At least 3 daily prices are required.")
        elif len({p["date"] for p in selected}) != len(selected):
            volatility.update(status="unavailable", reason="Duplicate price dates.")
        elif any(v is None or v <= 0 for v in values):
            volatility.update(status="unavailable", reason="Missing or nonpositive adjusted close in the selected window.")
        else:
            returns = [math.log(b / a) for a, b in zip(values, values[1:])]
            volatility.update(value=statistics.stdev(returns) * math.sqrt(252) * 100,
                              status="ok" if len(returns) == window else "short_history", returns_used=len(returns))
        metrics["Historical volatility"] = volatility
        # Preserve underlying observations for audit; use the curated snapshot's issuer overrides.
        evidence = [f for f in self.financials if f["symbol"] == symbol and f["period_end"] in
                    {row["financial_period_end"], row["prior_year_period_end"], row["balance_sheet_date"]}]
        return dict(symbol=symbol, company=row["company_name"], snapshot_cutoff=row["snapshot_cutoff"],
                    metrics=metrics, financial_observations=evidence,
                    notes=[row[k] for k in ("notes", "financial_verification", "net_income_basis") if row.get(k)],
                    balance_sheet_older_than_income=row["balance_sheet_older_than_income"],
                    calculated_at=datetime.now(timezone.utc).isoformat())


def display(result):
    print(f"\n{result['symbol']} — {result['company']}\nSnapshot: {result['snapshot_cutoff']}")
    for name, metric in result["metrics"].items():
        value = "N/A" if metric["value"] is None else f"{metric['value']:.2f}{metric['unit']}"
        print(f"\n{name}: {value} [{metric['status']}]")
        if "period_end" in metric:
            print(f"  Period: {metric['period_end']} {metric.get('period_type', '')}; currency: {metric['currency']}")
        if "prior_period_end" in metric:
            print(f"  Prior-year period: {metric['prior_period_end'] or 'unavailable'}")
        if "start_date" in metric:
            print(f"  Window: {metric['start_date']} to {metric['end_date']}; {metric.get('returns_used', 0)} of {metric['requested_returns']} requested returns")
        if "reason" in metric:
            print(f"  {metric['reason']}")
        print(f"  Formula: {metric['formula']}")
    print("\nFixed CSV snapshot; not live market data. Full inputs and sources are in the JSON audit log.")
    if result["balance_sheet_older_than_income"] == "true":
        print("Balance-sheet inputs are older than the income statement.")
    for note in result["notes"]:
        print(f"  {note}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker", nargs="?", help="e.g. 0700.HK, 00700, or 700; omit for interactive mode")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--window", type=int, default=252, help="Daily returns for annualized volatility (default 252)")
    parser.add_argument("--json", action="store_true", help="Print complete machine-readable result")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--log", type=Path, default=ROOT / "logs" / "requests.jsonl")
    args = parser.parse_args()
    if args.window < 2:
        parser.error("--window must be at least 2")
    agent = TickerAgent(args.data_dir)
    if args.list:
        for symbol, row in agent.snapshot.items():
            print(f"{symbol:10} {row['company_name']}")
        return

    def answer(ticker):
        result = agent.run(ticker, args.window)
        args.log.parent.mkdir(parents=True, exist_ok=True)
        with args.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(tool="ticker_metrics", parameters=dict(ticker=ticker, window=args.window), result=result), ensure_ascii=False) + "\n")
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            display(result)

    if args.ticker:
        try:
            answer(args.ticker)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        print("Ticker metrics agent. Enter a ticker, 'list', or 'quit'.")
        while True:
            try:
                ticker = input("Ticker> ").strip()
                if ticker.lower() in {"quit", "exit"}:
                    break
                if ticker.lower() == "list":
                    print("\n".join(f"{s} {r['company_name']}" for s, r in agent.snapshot.items()))
                elif ticker:
                    try:
                        answer(ticker)
                    except ValueError as exc:
                        print(exc)
            except (EOFError, KeyboardInterrupt):
                print()
                break


if __name__ == "__main__":
    main()
