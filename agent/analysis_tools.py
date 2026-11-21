"""Deterministic analysis tools for the frozen CSV snapshot."""
import math
import statistics
from datetime import date
from xml.sax.saxutils import escape
from agent import number


def metric(value=None, unit='%', formula='', reason=None, **details):
    if value is None and not reason:
        reason = 'Required inputs are missing, invalid, or insufficient for this calculation.'
    return dict(value=value, unit=unit, formula=formula,
                status='unavailable' if value is None else 'ok',
                **({'reason': reason} if reason else {}), **details)


def positive_prices(rows):
    values = [number(r['adjusted_close']) for r in rows]
    if not rows or len({r['date'] for r in rows}) != len(rows):
        raise ValueError('No prices or duplicate price dates in selected history.')
    if any(v is None or v <= 0 for v in values):
        raise ValueError('Missing or nonpositive adjusted close; no interpolation is performed.')
    return values


def ema(values, period):
    """SMA-seeded EMA; None until the seed window is complete."""
    result = [None] * len(values)
    if len(values) >= period:
        result[period - 1] = statistics.mean(values[:period])
        alpha = 2 / (period + 1)
        for i in range(period, len(values)):
            result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result


class AnalysisTools:
    def __init__(self, engine):
        self.engine = engine

    def prices(self, ticker):
        symbol = self.engine.normalize(ticker)
        return symbol, sorted((r for r in self.engine.prices if r['symbol'] == symbol), key=lambda r: r['date'])

    def context(self, symbol):
        row = self.engine.snapshot[symbol]
        return dict(symbol=symbol, company=row['company_name'], snapshot_cutoff=row['snapshot_cutoff'],
                    data_notice='Fixed snapshot, not live data. Historical indicators do not predict future prices.')

    def price_chart(self, ticker, window=252):
        """Adjusted-close line chart with SMA20/50/200 as a standalone SVG; history only."""
        symbol, rows = self.prices(ticker)
        prices = positive_prices(rows)
        out = self.context(symbol)
        currency = self.engine.snapshot[symbol]['price_currency']
        count = min(window + 1, len(prices))
        first = len(prices) - count
        shown, dates = prices[first:], [r['date'] for r in rows[first:]]
        colors = {'Adjusted close': '#1f4e79', 'SMA20': '#d9822b', 'SMA50': '#2e8b57', 'SMA200': '#8e44ad'}
        series = {'Adjusted close': shown}
        for n in (20, 50, 200):
            # Averages use the full history so the lines are complete inside the plotted window.
            line = [statistics.mean(prices[i - n + 1:i + 1]) if i >= n - 1 else None for i in range(first, len(prices))]
            if any(v is not None for v in line):
                series[f'SMA{n}'] = line
        values = [v for line in series.values() for v in line if v is not None]
        low, high = min(values), max(values)
        pad = (high - low) * 0.06 or max(high * 0.01, 0.01)
        low, high = low - pad, high + pad
        width, height, left, right, top, bottom = 760, 380, 64, 20, 46, 44
        plot_w, plot_h = width - left - right, height - top - bottom

        def x(i):
            return left + (plot_w * i / (count - 1) if count > 1 else plot_w / 2)

        def y(v):
            return top + plot_h * (high - v) / (high - low)

        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
                 f'font-family="Arial, sans-serif" font-size="12" role="img">',
                 f'<title>{symbol} adjusted close, {dates[0]} to {dates[-1]}</title>',
                 f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
                 f'<text x="{left}" y="20" font-size="14" fill="#1a1a1a">{symbol} {escape(out["company"])} '
                 f'adjusted close ({currency}), {dates[0]} to {dates[-1]}</text>']
        for k in range(5):
            value = low + (high - low) * k / 4
            parts.append(f'<line x1="{left}" y1="{y(value):.1f}" x2="{width - right}" y2="{y(value):.1f}" stroke="#e3e3e3"/>')
            parts.append(f'<text x="{left - 8}" y="{y(value) + 4:.1f}" text-anchor="end" fill="#555555">{value:.2f}</text>')
        ticks = sorted({0, (count - 1) // 3, 2 * (count - 1) // 3, count - 1})
        for i in ticks:
            anchor = 'start' if i == 0 else ('end' if i == count - 1 else 'middle')
            parts.append(f'<line x1="{x(i):.1f}" y1="{top + plot_h}" x2="{x(i):.1f}" y2="{top + plot_h + 5}" stroke="#555555"/>')
            parts.append(f'<text x="{x(i):.1f}" y="{top + plot_h + 20}" text-anchor="{anchor}" fill="#555555">{dates[i]}</text>')
        parts.append(f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="none" stroke="#555555"/>')
        for offset, (name, line) in enumerate(series.items()):
            points = ' '.join(f'{x(i):.1f},{y(v):.1f}' for i, v in enumerate(line) if v is not None)
            if count == 1:
                parts.append(f'<circle cx="{x(0):.1f}" cy="{y(line[0]):.1f}" r="3" fill="{colors[name]}"/>')
            else:
                parts.append(f'<polyline points="{points}" fill="none" stroke="{colors[name]}" '
                             f'stroke-width="{2 if name == "Adjusted close" else 1.2}"/>')
            lx = left + offset * 130
            parts.append(f'<line x1="{lx}" y1="34" x2="{lx + 22}" y2="34" stroke="{colors[name]}" stroke-width="2"/>')
            parts.append(f'<text x="{lx + 28}" y="38" fill="#1a1a1a">{name}</text>')
        parts.append(f'<text x="{width - right}" y="{height - 6}" text-anchor="end" font-size="11" fill="#777777">'
                     'Fixed snapshot; historical prices only, not a forecast.</text></svg>')
        top_i, bottom_i = shown.index(max(shown)), shown.index(min(shown))
        out.update(points=count, requested_returns=window, start_date=dates[0], end_date=dates[-1],
                   status='ok' if count == window + 1 else 'short_history',
                   price_basis='adjusted_close', price_currency=currency,
                   source_url=self.engine.snapshot[symbol]['price_source_url'],
                   series_plotted=list(series),
                   summary={'start_price': shown[0], 'end_price': shown[-1],
                            'change_pct': (shown[-1] / shown[0] - 1) * 100 if count > 1 else None,
                            'high': {'value': shown[top_i], 'date': dates[top_i]},
                            'low': {'value': shown[bottom_i], 'date': dates[bottom_i]},
                            'latest_sma': {name: line[-1] for name, line in series.items() if name != 'Adjusted close'}},
                   svg='\n'.join(parts))
        return out

    def price_analysis(self, ticker, window=252, rolling_window=20):
        symbol, rows = self.prices(ticker)
        prices = positive_prices(rows)
        out = self.context(symbol)
        out.update(as_of=rows[-1]['date'], price_basis='adjusted_close',
                   price_currency=self.engine.snapshot[symbol]['price_currency'],
                   source_url=self.engine.snapshot[symbol]['price_source_url'])
        metrics = {}
        # Use calendar offsets, taking the last observation on or before the target date.
        last = date.fromisoformat(rows[-1]['date'])
        import calendar
        for months in (1, 3, 6, 12):
            index = last.year * 12 + last.month - 1 - months
            year, month = divmod(index, 12)
            month += 1
            target = date(year, month, min(last.day, calendar.monthrange(year, month)[1])).isoformat()
            candidates = [i for i, r in enumerate(rows) if r['date'] <= target]
            key = f'return_{months}m'
            if not candidates:
                metrics[key] = metric(formula='(end adjusted close / start adjusted close - 1) * 100', reason='Insufficient history for full calendar-month window.', target_date=target)
            else:
                i = candidates[-1]
                metrics[key] = metric((prices[-1] / prices[i] - 1) * 100,
                                      formula='(end adjusted close / start adjusted close - 1) * 100',
                                      start_date=rows[i]['date'], end_date=rows[-1]['date'],
                                      inputs={'start': prices[i], 'end': prices[-1]})
        averages = {}
        for n in (20, 50, 200):
            value = statistics.mean(prices[-n:]) if len(prices) >= n else None
            averages[n] = value
            metrics[f'sma_{n}'] = metric(value, unit=out['price_currency'], formula=f'mean of last {n} adjusted closes',
                                         reason='Insufficient history.' if value is None else None,
                                         price_distance_pct=(prices[-1] / value - 1) * 100 if value else None)
        changes = [b - a for a, b in zip(prices, prices[1:])]
        rsi = None
        if len(changes) >= 14:
            gain = statistics.mean(max(x, 0) for x in changes[:14])
            loss = statistics.mean(max(-x, 0) for x in changes[:14])
            for change in changes[14:]:
                gain = (13 * gain + max(change, 0)) / 14
                loss = (13 * loss + max(-change, 0)) / 14
            rsi = 50 if gain == loss == 0 else (100 if loss == 0 else 100 - 100 / (1 + gain / loss))
        metrics['rsi_14'] = metric(rsi, unit='index (0-100)', formula='100 - 100/(1 + Wilder average gain / average loss)',
                                    reason='At least 15 prices required.' if rsi is None else None,
                                    flat_price_convention=50)
        fast, slow = ema(prices, 12), ema(prices, 26)
        lines = [a - b for a, b in zip(fast, slow) if a is not None and b is not None]
        signals = ema(lines, 9)
        signal = signals[-1] if signals else None
        metrics['macd'] = metric(lines[-1] if lines else None, unit=out['price_currency'],
                                 formula='EMA12 - EMA26; signal=EMA9 of MACD; SMA seeds',
                                 signal=signal, histogram=lines[-1] - signal if signal is not None else None,
                                 reason='At least 26 prices for MACD, 34 for signal.' if len(prices) < 34 else None)
        selected, selected_rows = prices[-(window + 1):], rows[-(window + 1):]
        peak = selected[0]
        peak_date = selected_rows[0]['date']
        worst, worst_peak, trough = 0, peak_date, peak_date
        for p, row in zip(selected, selected_rows):
            if p > peak:
                peak, peak_date = p, row['date']
            drawdown = (p / peak - 1) * 100
            if drawdown < worst:
                worst, worst_peak, trough = drawdown, peak_date, row['date']
        metrics['maximum_drawdown'] = metric(worst if len(selected) > 1 else None,
                                             formula='minimum(price / running peak - 1) * 100',
                                             peak_date=worst_peak, trough_date=trough,
                                             start_date=selected_rows[0]['date'], end_date=selected_rows[-1]['date'],
                                             requested_returns=window, returns_used=len(selected) - 1)
        if 1 < len(selected) < window + 1:
            metrics['maximum_drawdown']['status'] = 'short_history'
        logs = [math.log(b / a) for a, b in zip(prices, prices[1:])]
        rolling = []
        for i in range(rolling_window, len(logs) + 1):
            rolling.append({'date': rows[i]['date'], 'value': statistics.stdev(logs[i-rolling_window:i]) * math.sqrt(252) * 100})
        metrics['rolling_volatility'] = metric(rolling[-1]['value'] if rolling else None,
                                               formula=f'sample stdev of {rolling_window} daily log returns * sqrt(252) * 100',
                                               reason='Insufficient history.' if not rolling else None,
                                               series=rolling[-window:], annualization_days=252, rolling_window=rolling_window)
        volume = number(rows[-1].get('volume'))
        prior = [number(r.get('volume')) for r in rows[-21:-1]]
        baseline = statistics.mean(prior) if len(prior) == 20 and all(v is not None and v >= 0 for v in prior) else None
        metrics['volume_ratio_20'] = metric(volume / baseline if volume is not None and volume >= 0 and baseline and baseline > 0 else None,
                                            unit='x', formula='latest volume / mean volume of previous 20 sessions',
                                            inputs={'latest_volume': volume, 'prior_average_volume': baseline})
        out['metrics'] = metrics
        out['trend_comparison'] = {
            'price_above_sma_50': prices[-1] > averages[50] if averages[50] is not None else None,
            'sma_50_above_sma_200': averages[50] > averages[200] if averages[50] is not None and averages[200] is not None else None,
        }
        # A crossover requires both today's and yesterday's averages, not just ordering.
        if len(prices) >= 201:
            previous = statistics.mean(prices[-51:-1]) - statistics.mean(prices[-201:-1])
            current = averages[50] - averages[200]
            out['trend_comparison']['latest_50_200_crossover'] = 'up' if previous <= 0 < current else ('down' if previous >= 0 > current else 'none')
        return out

    def stock_correlation(self, ticker, other_ticker, window=252):
        symbol, left = self.prices(ticker)
        other, right = self.prices(other_ticker)
        def returns(rows):
            values = positive_prices(rows)
            # Match both endpoints; never correlate a multi-day return with a one-day return.
            return {(a['date'], b['date']): math.log(q / p)
                    for a, b, p, q in zip(rows, rows[1:], values, values[1:])}
        a, b = returns(left), returns(right)
        dates = sorted(a.keys() & b.keys())[-window:]
        value = None
        reason = None
        if len(dates) < 2:
            reason = 'At least two matched return intervals required.'
        else:
            x, y = [a[d] for d in dates], [b[d] for d in dates]
            mx, my = statistics.mean(x), statistics.mean(y)
            divisor = math.sqrt(sum((v-mx)**2 for v in x) * sum((v-my)**2 for v in y))
            if divisor:
                value = max(-1, min(1, sum((u-mx)*(v-my) for u, v in zip(x, y)) / divisor))
            else:
                reason = 'Correlation undefined for constant returns.'
        result = metric(value, unit='correlation (-1 to 1)', formula='Pearson correlation of matched adjusted-close log returns', reason=reason,
                        returns_used=len(dates), requested_returns=window,
                        start_date=dates[0][0] if dates else None, end_date=dates[-1][1] if dates else None)
        if value is not None and len(dates) < window:
            result['status'] = 'short_history'
        return dict(**self.context(symbol), other_symbol=other, correlation=result,
                    source_urls=[self.engine.snapshot[s]['price_source_url'] for s in (symbol, other)])

    def financial_trends(self, ticker):
        symbol = self.engine.normalize(ticker)
        rows = [r for r in self.engine.financials if r['symbol'] == symbol]
        # Use a single annual vendor basis, rather than mixing issuer quarterly supplements.
        def get(name, end, currency):
            found = [r for r in rows if r['metric'] == 'annual' + name and r['period_type'] == '12M'
                     and r['period_end'] == end and r['currency'] == currency and number(r['value']) is not None]
            if len(found) != 1:
                return None
            return found[0]
        def prior(end):
            d = date.fromisoformat(end)
            try:
                return d.replace(year=d.year-1).isoformat()
            except ValueError:
                return d.replace(year=d.year-1, day=28).isoformat()
        results = {}
        for key, name in [('debt_growth', 'TotalDebt'), ('equity_growth', 'StockholdersEquity')]:
            candidates = sorted((r for r in rows if r['metric'] == 'annual' + name and r['period_type'] == '12M'), key=lambda r: r['period_end'], reverse=True)
            result = metric(reason='No comparable annual pair with positive prior value.', formula='(current / prior-year value - 1) * 100')
            for row in candidates:
                current = get(name, row['period_end'], row['currency'])
                previous = get(name, prior(row['period_end']), row['currency'])
                if current and previous and number(previous['value']) > 0:
                    result = metric((number(current['value']) / number(previous['value']) - 1) * 100,
                                    formula='(current / prior-year value - 1) * 100', inputs=[previous, current],
                                    period_end=current['period_end'], prior_period_end=previous['period_end'], currency=row['currency'])
                    break
            results[key] = result
        results['profit_margin_change'] = metric(unit='percentage points', reason='No two matched annual income periods.', formula='current annual margin - prior annual margin')
        results['return_on_equity'] = metric(reason='No annual profit with positive opening and closing equity.', formula='annual net income / mean(opening equity, closing equity) * 100')
        incomes = sorted((r for r in rows if r['metric'] == 'annualNetIncome' and r['period_type'] == '12M'), key=lambda r: r['period_end'], reverse=True)
        for row in incomes:
            end, currency = row['period_end'], row['currency']
            old = prior(end)
            income = get('NetIncome', end, currency)
            revenue = get('TotalRevenue', end, currency)
            previous_income, previous_revenue = get('NetIncome', old, currency), get('TotalRevenue', old, currency)
            if results['profit_margin_change']['value'] is None and all([income, revenue, previous_income, previous_revenue]):
                if number(revenue['value']) > 0 and number(previous_revenue['value']) > 0:
                    value = (number(income['value']) / number(revenue['value']) - number(previous_income['value']) / number(previous_revenue['value'])) * 100
                    results['profit_margin_change'] = metric(value, unit='percentage points', formula='current annual margin - prior annual margin',
                                                             period_end=end, prior_period_end=old, currency=currency,
                                                             inputs=[income, revenue, previous_income, previous_revenue])
            opening, closing = get('StockholdersEquity', old, currency), get('StockholdersEquity', end, currency)
            if results['return_on_equity']['value'] is None and all([income, opening, closing]):
                if number(opening['value']) > 0 and number(closing['value']) > 0:
                    results['return_on_equity'] = metric(number(income['value']) / ((number(opening['value']) + number(closing['value'])) / 2) * 100,
                                                        formula='annual net income / mean(opening equity, closing equity) * 100',
                                                        period_end=end, prior_period_end=old, currency=currency, inputs=[income, opening, closing])
        return dict(**self.context(symbol), metrics=results,
                    basis='Latest available comparable annual vendor observations per metric; may be older than the curated snapshot income period. No quarterly annualization or issuer/vendor mixing.')

    def rank_stocks(self, top_k=5, weights=None, filters=None, window=252):
        names = {'revenue_growth': 'Revenue growth', 'net_profit_margin': 'Net profit margin',
                 'debt_to_equity': 'Debt-to-equity', 'historical_volatility': 'Historical volatility'}
        weights = weights if weights is not None else {k: 1 for k in names}
        filters = filters if filters is not None else {}
        if not weights or set(weights) - names.keys():
            raise ValueError('weights must use one or more core metric keys: ' + ', '.join(names))
        if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in weights.values()) or not math.isfinite(sum(weights.values())) or sum(weights.values()) <= 0:
            raise ValueError('Weights must be finite, nonnegative numbers with positive total.')
        for key, bounds in filters.items():
            if key not in names or not isinstance(bounds, dict) or not bounds or set(bounds) - {'min', 'max'}:
                raise ValueError('Filters require a core metric key with min and/or max bounds.')
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in bounds.values()):
                raise ValueError('Filter bounds must be finite numbers.')
            if bounds.get('min', -math.inf) > bounds.get('max', math.inf):
                raise ValueError('Filter minimum exceeds maximum.')
        weights = {k: v / sum(weights.values()) for k, v in weights.items() if v > 0}
        eligible, excluded = [], []
        for symbol in self.engine.snapshot:
            raw = self.engine.run(symbol, window)['metrics']
            values = {key: raw[label]['value'] for key, label in names.items()}
            required = set(weights) | set(filters)
            missing = [key for key in required if values[key] is None or raw[names[key]]['status'] != 'ok']
            if missing:
                excluded.append({'symbol': symbol, 'reason': 'Missing input or incomplete volatility window', 'metrics': missing})
                continue
            if any(values[k] < bounds.get('min', -math.inf) or values[k] > bounds.get('max', math.inf) for k, bounds in filters.items()):
                excluded.append({'symbol': symbol, 'reason': 'Failed mandatory filter'})
                continue
            eligible.append({'symbol': symbol, 'company': self.engine.snapshot[symbol]['company_name'], 'values': values,
                             'metric_details': raw})
        for row in eligible:
            percentiles = {}
            for key in weights:
                vals = [r['values'][key] for r in eligible]
                v = row['values'][key]
                # Midranks give tied values identical scores; a single candidate scores 50.
                rank = (sum(x < v for x in vals) + (sum(x == v for x in vals) - 1) / 2)
                score = rank / (len(vals)-1) * 100 if len(vals) > 1 else 50
                percentiles[key] = 100-score if key in {'debt_to_equity', 'historical_volatility'} else score
            row['percentile_scores'] = percentiles
            row['score'] = sum(weights[k] * percentiles[k] for k in weights)
        eligible.sort(key=lambda r: (-r['score'], r['symbol']))
        for i, row in enumerate(eligible, 1):
            row['rank'] = i
        return dict(results=eligible[:top_k], eligible_count=len(eligible), excluded=excluded, weights=weights, filters=filters,
                    formula='Weighted mean of favorable-direction percentile scores among candidates remaining after mandatory filters; ties use midranks.',
                    directions={k: 'lower' if k in {'debt_to_equity', 'historical_volatility'} else 'higher' for k in weights},
                    caveats=['Descriptive screening score, not a forecast or personalized investment recommendation.',
                             'Reporting dates and period types differ across companies; inspect metric_details before comparing.',
                             'Sector classification is unavailable. Missing required metrics and short volatility histories are excluded.'])
