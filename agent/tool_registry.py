"""One source of truth for model-facing tool definitions and argument validation."""
MAX_BATCH_TOOLS = 6
TOOLS = {
    'list_tickers': {
        'description': 'List supported ticker symbols and company names. Use to resolve company names before other tools.',
        'parameters': {}, 'required': [],
        'example': {}},
    'ticker_metrics': {
        'description': 'Original four metrics: revenue growth, net profit margin, debt-to-equity, historical volatility. Default for a plain ticker or company overview.',
        'parameters': {'ticker': 'string', 'window': 'integer:2:5000'}, 'required': ['ticker'],
        'example': {'ticker': '0700.HK', 'window': 252}},
    'financial_trends': {
        'description': 'Annual profit-margin change (percentage points), debt growth, equity growth, and return on equity (ROE). Each uses its latest comparable annual observations; may be older than core metrics.',
        'parameters': {'ticker': 'string'}, 'required': ['ticker'],
        'example': {'ticker': '0700.HK'}},
    'price_analysis': {
        'description': 'Calendar 1/3/6/12-month returns, SMA20/50/200 and latest crossover, Wilder RSI14, MACD12/26/9, maximum drawdown, rolling annualized volatility and latest volume divided by previous 20-session average. window controls drawdown lookback and number of rolling points; rolling_window controls volatility estimation. Defaults 252 and 20. All use adjusted close except volume.',
        'parameters': {'ticker': 'string', 'window': 'integer:2:5000', 'rolling_window': 'integer:2:5000'}, 'required': ['ticker'],
        'example': {'ticker': '0700.HK', 'window': 252, 'rolling_window': 20}},
    'stock_correlation': {
        'description': 'Pearson correlation between two stocks using matched adjusted-close log-return intervals. window defaults to 252 returns. Not market beta.',
        'parameters': {'ticker': 'string', 'other_ticker': 'string', 'window': 'integer:2:5000'}, 'required': ['ticker', 'other_ticker'],
        'example': {'ticker': '0700.HK', 'other_ticker': '9988.HK', 'window': 60}},
    'rank_stocks': {
        'description': 'Set reuse_previous=true to keep last ranking parameters, overriding only supplied fields. Explicit filters={} clears filters. Screen all supported stocks, then return Top-K weighted percentile ranks. top_k defaults 5. weights defaults equal across revenue_growth, net_profit_margin, debt_to_equity, historical_volatility. Supply nonnegative weights for any subset. Higher growth/margin and lower debt/volatility score better. filters maps those same keys to min/max numeric bounds. Growth, margin and volatility are percent values (10 means 10%); debt is a multiple (0.5 means 0.5x). window defaults 252 for volatility. Missing required data excluded. No sector filters available.',
        'parameters': {'reuse_previous': 'boolean', 'top_k': 'integer:1:30', 'weights': 'object', 'filters': 'object', 'window': 'integer:2:5000'}, 'required': [],
        'example': {'top_k': 5, 'weights': {'revenue_growth': 2, 'historical_volatility': 1}, 'filters': {'net_profit_margin': {'min': 0}, 'debt_to_equity': {'max': 1}}}},
}


def validate(name, args):
    if not isinstance(name, str) or name not in TOOLS:
        raise ValueError('Unknown tool. Available: ' + ', '.join(TOOLS))
    spec = TOOLS[name]
    if not isinstance(args, dict):
        raise ValueError('arguments must be an object')
    if set(args) - spec['parameters'].keys():
        raise ValueError('Unexpected arguments for ' + name)
    if set(spec['required']) - args.keys():
        raise ValueError('Required arguments: ' + ', '.join(spec['required']))
    for key, value in args.items():
        kind = spec['parameters'][key]
        if kind == 'string' and (not isinstance(value, str) or not value.strip()):
            raise ValueError(key + ' must be a nonempty string')
        if kind == 'boolean' and type(value) is not bool:
            raise ValueError(key + ' must be a boolean')
        if kind == 'object' and not isinstance(value, dict):
            raise ValueError(key + ' must be an object')
        if kind.startswith('integer:'):
            _, low, high = kind.split(':')
            if type(value) is not int or not int(low) <= value <= int(high):
                raise ValueError(f'{key} must be an integer between {low} and {high}')


def validate_batch(calls):
    """Validate the entire batch before any tool runs; no nested actions."""
    if not isinstance(calls, list) or not 1 <= len(calls) <= MAX_BATCH_TOOLS:
        raise ValueError(f'tools must contain 1 to {MAX_BATCH_TOOLS} tool requests')
    for call in calls:
        if not isinstance(call, dict) or set(call) - {'tool', 'arguments'}:
            raise ValueError('Each batch entry must contain only tool and arguments')
        validate(call.get('tool'), call.get('arguments', {}))
    # Ranking changes session preferences. Keep it separate from independent reads.
    if len(calls) > 1 and any(call['tool'] == 'rank_stocks' for call in calls):
        raise ValueError('Call rank_stocks separately; batch only independent read tools')
