#!/usr/bin/env python3
"""Derives the dashboard CSVs from the files exported by the notebook's last cell
(kpis, holdout_forecasts, daily_sales, family_month_sales, store_family_sales)."""
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

kpi = pd.read_csv(HERE / 'kpis.csv').set_index('kpi')['value']
pd.DataFrame([{
    'total_sales': round(kpi.total_sales, 2),
    'avg_daily_sales': round(kpi.avg_daily_sales, 2),
    'promotion_lift_pct': round(kpi.promotion_lift_pct, 1),
    'best_model_mape_pct': round(kpi.best_model_mape_pct, 2),
}]).to_csv(HERE / 'kpi_tiles.csv', index=False)

names = {
    'actual': 'Actual',
    'seasonal_naive': f'Seasonal naive (MAPE {kpi.seasonal_naive_mape_pct:.1f}%)',
    'prophet': f'Prophet (MAPE {kpi.prophet_mape_pct:.1f}%)',
    'random_forest': f'Random forest (MAPE {kpi.best_model_mape_pct:.1f}%)',
}
holdout = pd.read_csv(HERE / 'holdout_forecasts.csv').melt('date', var_name='model', value_name='sales')
holdout['model'] = holdout['model'].map(names)
holdout['sales'] = holdout['sales'].round(0)
holdout.to_csv(HERE / 'holdout_long.csv', index=False)

daily = pd.read_csv(HERE / 'daily_sales.csv', parse_dates=['date'])
dow = daily.groupby('day_of_week')['sales'].mean().round(0)
pd.DataFrame({'day_num': range(1, 8), 'day': [d[:3] for d in DAYS],
              'avg_daily_sales': [dow[d] for d in DAYS]}).to_csv(HERE / 'sales_by_day_of_week.csv', index=False)
month = daily.groupby('month')['sales'].mean().round(0)
pd.DataFrame({'month_num': range(1, 13), 'month': MONTHS,
              'avg_daily_sales': month.values}).to_csv(HERE / 'sales_by_month.csv', index=False)

family = pd.read_csv(HERE / 'family_month_sales.csv').groupby('family', as_index=False)['sales'].sum()
family['sales'] = family['sales'].round(0)
family.sort_values('sales', ascending=False).to_csv(HERE / 'sales_by_family.csv', index=False)

store = (pd.read_csv(HERE / 'store_family_sales.csv')
         .groupby(['store_nbr', 'city', 'state', 'type'], as_index=False)['sales'].sum())
store['store'] = 'Store ' + store['store_nbr'].astype(str) + ' · ' + store['city']
store['sales'] = store['sales'].round(0)
store[['store', 'store_nbr', 'city', 'state', 'type', 'sales']].sort_values(
    'sales', ascending=False).to_csv(HERE / 'sales_by_store.csv', index=False)
