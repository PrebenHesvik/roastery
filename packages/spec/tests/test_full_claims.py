"""The tier 3 claims of data-docs' `test_roastery_tier3.py`, ported with names and literals as
they were. They run on the full data folder (`--full`, `ROASTERY_FULL_DATA`, else the baseline),
which holds the tiny tables as well, so a join to `prices` works. The answers are written here,
never computed from the formulas.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import duckdb
import pytest

FIRST = date(2024, 10, 1)
LAST = date(2026, 9, 30)
FIRST_SQL = "DATE '2024-10-01'"
LAST_SQL = "DATE '2026-09-30'"
PRICE_HOLDS = (
    'p.product_id = s.product_id AND s.sale_date >= p.valid_from '
    'AND (p.valid_to IS NULL OR s.sale_date < p.valid_to)'
)


@pytest.fixture(scope='module')
def con(full: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    return full


def one(con: duckdb.DuckDBPyConnection, query: str):
    """The single value of a query."""
    row = con.execute(query).fetchone()
    assert row is not None
    return row[0]


def rows(con: duckdb.DuckDBPyConnection, query: str) -> list[tuple]:
    """Every row of a query."""
    return con.execute(query).fetchall()


def percent(hits: int, total: int) -> Decimal:
    """A rate in percent to one decimal, halves rounded up."""
    return (Decimal(hits) * 100 / Decimal(total)).quantize(Decimal('0.1'), ROUND_HALF_UP)


@pytest.mark.parametrize(
    ('table', 'column'),
    [
        ('daily_sales', 'sale_date'),
        ('visits', 'visit_date'),
        ('shop_days', 'shop_date'),
        ('order_values', 'order_date'),
    ],
)
def test_a_day_counted_table_lies_within_1_october_2024_and_30_september_2026(con, table, column):
    low, high = rows(con, f'SELECT min({column}), max({column}) FROM {table}')[0]
    assert FIRST <= low
    assert high <= LAST


def test_checkout_test_counts_test_days_not_dates_so_it_has_no_date_to_leave_the_window(con):
    columns = [c[0] for c in con.execute('DESCRIBE checkout_test').fetchall()]
    assert columns == ['visitor_no', 'test_day', 'variant', 'converted']


def test_deliveries_ship_the_day_after_a_web_order_placed_inside_the_window(con):
    joined = 'FROM deliveries d JOIN order_values o USING (order_no)'
    assert one(con, f'SELECT count(*) {joined}') == 480
    assert one(con, "SELECT count(*) FROM order_values WHERE channel = 'web'") == 480
    assert one(con, f'SELECT count(*) {joined} WHERE d.shipped_on = o.order_date + 1') == 480
    assert (
        one(
            con,
            f'SELECT count(*) {joined} WHERE o.order_date NOT BETWEEN {FIRST_SQL} AND {LAST_SQL}',
        )
        == 0
    )


def test_daily_sales_runs_the_whole_window_and_ends_on_30_september_2026(con):
    assert rows(con, 'SELECT min(sale_date), max(sale_date) FROM daily_sales') == [(FIRST, LAST)]
    assert one(con, 'SELECT count(DISTINCT sale_date) FROM daily_sales') == 730


def test_daily_sales_has_no_row_where_no_price_holds(con):
    unpriced = (
        'SELECT count(*) FROM daily_sales s '
        f'WHERE NOT EXISTS (SELECT 1 FROM prices p WHERE {PRICE_HOLDS})'
    )
    assert one(con, unpriced) == 0
    # the grinder from June 2025; the kettle (priced from 7 October 2026) is never sold
    assert rows(
        con,
        'SELECT product_id, count(*), min(sale_date) FROM daily_sales GROUP BY ALL ORDER BY ALL',
    ) == [('P-10', 730, FIRST), ('P-11', 730, FIRST), ('P-20', 487, date(2025, 6, 1))]


def test_daily_sales_amount_is_the_quantity_times_the_price_of_the_day(con):
    wrong = (
        'SELECT count(*) FROM daily_sales s JOIN prices p ON '
        f'{PRICE_HOLDS} WHERE s.amount <> s.qty * p.price'
    )
    assert one(con, wrong) == 0
    assert one(con, 'SELECT sum(amount) FROM daily_sales') == Decimal('2409009.00')


def test_daily_sales_sells_most_on_friday_and_about_three_times_as_much_as_on_sunday(con):
    by_day = dict(rows(con, 'SELECT isodow(sale_date), sum(qty) FROM daily_sales GROUP BY ALL'))
    assert max(by_day, key=by_day.get) == 5
    assert min(by_day, key=by_day.get) == 7
    assert (by_day[5], by_day[7]) == (2718, 951)
    assert round(by_day[5] / by_day[7], 1) == 2.9


def test_daily_sales_sells_double_in_each_december(con):
    nov = one(
        con,
        'SELECT sum(amount) FROM daily_sales WHERE year(sale_date) = 2024 '
        'AND month(sale_date) = 11',
    )
    dec = one(
        con,
        'SELECT sum(amount) FROM daily_sales WHERE year(sale_date) = 2024 '
        'AND month(sale_date) = 12',
    )
    assert (nov, dec) == (Decimal('70903.00'), Decimal('158725.00'))
    # quantity per month: a December against the average of the other eleven months of its
    # year of the window (October to September)
    year = "CASE WHEN sale_date < DATE '2025-10-01' THEN 1 ELSE 2 END"
    got = rows(
        con,
        f'SELECT {year}, sum(qty) FILTER (WHERE month(sale_date) = 12), '
        'sum(qty) FILTER (WHERE month(sale_date) <> 12) '
        'FROM daily_sales GROUP BY ALL ORDER BY 1',
    )
    assert got == [(1, 905, 4488), (2, 1067, 6041)]
    ratios = [round(Decimal(d) / (Decimal(o) / 11), 1) for _, d, o in got]
    assert ratios == [Decimal('2.2'), Decimal('1.9')]


def test_daily_sales_grows_in_the_second_year_for_every_product_sold_in_both(con):
    got = rows(
        con,
        "SELECT product_id, sum(qty) FILTER (WHERE sale_date < DATE '2025-10-01'), "
        "sum(qty) FILTER (WHERE sale_date >= DATE '2025-10-01') "
        "FROM daily_sales WHERE product_id IN ('P-10', 'P-11') GROUP BY ALL ORDER BY ALL",
    )
    assert got == [('P-10', 3912, 5146), ('P-11', 1399, 1696)]
    assert all(second > first for _, first, second in got)


def test_daily_sales_ramps_the_growth_in_over_october_to_december_2025(con):
    got = rows(
        con,
        "SELECT date_trunc('month', sale_date)::DATE, sum(amount) FROM daily_sales "
        "WHERE sale_date BETWEEN DATE '2025-09-01' AND DATE '2026-01-31' GROUP BY ALL ORDER BY 1",
    )
    assert got == [
        (date(2025, 9, 1), Decimal('85810.00')),
        (date(2025, 10, 1), Decimal('93093.00')),
        (date(2025, 11, 1), Decimal('92512.00')),
        (date(2025, 12, 1), Decimal('214363.00')),
        (date(2026, 1, 1), Decimal('118170.00')),
    ]
    # October grows on September by less than a tenth: no step on 1 October
    assert got[1][1] / got[0][1] < Decimal('1.1')


def test_daily_sales_grinder_is_flat_in_the_june_to_september_months_both_years_have(con):
    # the grinder (P-20) starts in June 2025 and sells 1 a day at its base, so it does not grow
    got = rows(
        con,
        "SELECT sum(qty) FILTER (WHERE sale_date BETWEEN DATE '2025-06-01' AND DATE '2025-09-30'), "
        "sum(qty) FILTER (WHERE sale_date BETWEEN DATE '2026-06-01' AND DATE '2026-09-30') "
        "FROM daily_sales WHERE product_id = 'P-20'",
    )
    assert got == [(82, 82)]


def test_order_values_has_its_mean_above_its_median_and_18_distinct_amounts(con):
    mean, median, distinct, high, low = rows(
        con,
        'SELECT round(avg(amount), 2), median(amount), count(DISTINCT amount), '
        'max(amount), min(amount) FROM order_values',
    )[0]
    assert (mean, median) == (475.42, Decimal('238.00'))
    assert mean > median
    assert distinct == 18
    assert (high, low) == (Decimal('5712.00'), Decimal('-899.00'))


def test_order_values_carries_a_channel_and_a_status_with_a_refund_and_unpaid_orders(con):
    assert rows(
        con, 'SELECT channel, status, count(*) FROM order_values GROUP BY ALL ORDER BY ALL'
    ) == [
        ('shop', 'paid', 118),
        ('shop', 'refund', 1),
        ('shop', 'unpaid', 1),
        ('web', 'paid', 448),
        ('web', 'unpaid', 32),
    ]
    assert rows(
        con, "SELECT order_no, order_date, amount FROM order_values WHERE status = 'refund'"
    ) == [(300, date(2026, 5, 18), Decimal('-899.00'))]


def test_order_values_has_no_shop_order_on_a_sunday_when_the_shop_is_closed(con):
    assert rows(
        con,
        'SELECT channel, count(*) FROM order_values WHERE isodow(order_date) = 7 '
        'GROUP BY ALL ORDER BY 1',
    ) == [('web', 69)]


def test_order_values_has_one_cafe_order_of_48_bags_as_the_one_big_value(con):
    assert rows(con, 'SELECT order_no, amount, status FROM order_values WHERE amount > 5000') == [
        (600, Decimal('5712.00'), 'unpaid')
    ]
    assert one(con, 'SELECT max(amount) FROM order_values WHERE order_no <> 600') < 5000


def test_budget_runs_to_december_2026_with_one_row_per_month_and_kind(con):
    assert rows(con, 'SELECT min(month), max(month), count(DISTINCT kind) FROM budget') == [
        (FIRST, date(2026, 12, 1), 2)
    ]
    assert one(con, 'SELECT count(DISTINCT month) FROM budget') == 27
    assert one(con, 'SELECT count(*) FROM (SELECT month, kind FROM budget GROUP BY ALL)') == 54


def test_budget_steps_up_by_year_starts_equipment_with_the_grinder_and_doubles_december(con):
    got = rows(
        con,
        'SELECT kind, budget_nok, min(month), max(month), count(*) FROM budget '
        'GROUP BY ALL ORDER BY ALL',
    )
    assert got == [
        ('beans', 70000, FIRST, date(2025, 9, 1), 11),
        ('beans', 95000, date(2025, 10, 1), date(2026, 11, 1), 13),
        ('beans', 140000, date(2024, 12, 1), date(2024, 12, 1), 1),
        ('beans', 190000, date(2025, 12, 1), date(2026, 12, 1), 2),
        ('equipment', 0, FIRST, date(2025, 5, 1), 8),
        ('equipment', 18000, date(2025, 6, 1), date(2026, 11, 1), 17),
        ('equipment', 36000, date(2025, 12, 1), date(2026, 12, 1), 2),
    ]


def test_some_months_beat_the_budget_and_some_miss_it(con):
    got = rows(
        con,
        "SELECT b.kind, CASE WHEN b.month < DATE '2025-10-01' THEN 1 ELSE 2 END, "
        'count(*) FILTER (WHERE s.amount >= b.budget_nok), '
        'count(*) FILTER (WHERE s.amount < b.budget_nok) FROM budget b '
        "JOIN (SELECT date_trunc('month', sale_date)::DATE AS month, "
        "CASE WHEN product_id IN ('P-10', 'P-11') THEN 'beans' ELSE 'equipment' END AS kind, "
        'sum(amount) AS amount FROM daily_sales GROUP BY ALL) s USING (month, kind) '
        'GROUP BY ALL ORDER BY ALL',
    )
    # months with sales, per year October to September: beans beat 8 and miss 4, then beat 3
    # and miss 9; equipment (from June 2025) beats 2 and misses 2, then beats 7 and misses 5
    assert got == [
        ('beans', 1, 8, 4),
        ('beans', 2, 3, 9),
        ('equipment', 1, 2, 2),
        ('equipment', 2, 7, 5),
    ]


def test_checkout_test_has_4000_visitors_over_40_days_100_a_day_in_two_variants_of_2000(con):
    assert rows(
        con, 'SELECT min(test_day), max(test_day), count(DISTINCT test_day) FROM checkout_test'
    ) == [(1, 40, 40)]
    assert rows(con, 'SELECT variant, count(*) FROM checkout_test GROUP BY ALL ORDER BY 1') == [
        ('A', 2000),
        ('B', 2000),
    ]
    per_day = 'SELECT test_day FROM checkout_test GROUP BY ALL HAVING count(*) <> 100'
    assert one(con, f'SELECT count(*) FROM ({per_day})') == 0


def test_checkout_test_converts_12_percent_against_14_9_percent_at_the_end(con):
    got = dict(rows(con, 'SELECT variant, sum(converted::INTEGER) FROM checkout_test GROUP BY ALL'))
    assert got == {'A': 239, 'B': 297}
    assert percent(got['A'], 2000) == Decimal('12.0')
    assert percent(got['B'], 2000) == Decimal('14.9')


def test_checkout_test_gap_is_about_2_7_standard_errors():
    a, b = 239, 297
    pooled = (a + b) / 4000
    se = (pooled * (1 - pooled) * (1 / 2000 + 1 / 2000)) ** 0.5
    assert round((b - a) / 2000 / se, 1) == 2.7


def test_checkout_test_is_a_fluke_after_two_days_8_percent_against_24_percent(con):
    got = rows(
        con,
        'SELECT variant, sum(converted::INTEGER), count(*) FROM checkout_test '
        'WHERE test_day <= 2 GROUP BY ALL ORDER BY 1',
    )
    assert got == [('A', 8, 100), ('B', 24, 100)]
    assert [percent(h, n) for _, h, n in got] == [Decimal('8.0'), Decimal('24.0')]


def test_checkout_test_a_against_a_is_equal_11_9_and_12_0_percent(con):
    got = rows(
        con,
        'SELECT visitor_no % 4, sum(converted::INTEGER), count(*) FROM checkout_test '
        "WHERE variant = 'A' GROUP BY ALL ORDER BY 1",
    )
    assert got == [(0, 119, 1000), (2, 120, 1000)]
    assert [percent(h, n) for _, h, n in got] == [Decimal('11.9'), Decimal('12.0')]


def test_subscribers_start_on_1_january_2024_on_real_dates_and_never_end_before_they_start(con):
    assert rows(con, 'SELECT min(started), max(started), count(*) FROM subscribers') == [
        (date(2024, 1, 1), date(2026, 9, 22), 240)
    ]
    assert one(con, 'SELECT count(*) FROM subscribers WHERE ended < started') == 0
    assert one(con, f'SELECT count(*) FROM subscribers WHERE ended > {LAST_SQL}') == 0
    assert one(con, 'SELECT count(ended) FROM subscribers') == 104
    assert rows(con, 'SELECT product_id, count(*) FROM subscribers GROUP BY ALL ORDER BY 1') == [
        ('P-10', 160),
        ('P-11', 80),
    ]


def test_subscribers_later_cohorts_stay_longer(con):
    kept = (
        'SELECT year(started), count(*), '
        'sum((ended IS NULL OR ended >= started + INTERVAL {months} MONTH)::INTEGER) '
        'FROM subscribers {where} GROUP BY ALL ORDER BY 1'
    )
    # twelve months kept, for the starts that have had twelve months to end
    year = rows(con, kept.format(months=12, where="WHERE started <= DATE '2025-09-30'"))
    assert year == [(2024, 88, 55), (2025, 66, 53)]
    assert year[1][2] / year[1][1] > year[0][2] / year[0][1]
    # six months kept: the 2024 cohort loses some, the later ones none
    half = rows(con, kept.format(months=6, where=''))
    assert half == [(2024, 88, 72), (2025, 88, 88), (2026, 64, 64)]


def test_visits_has_3600_visits_over_the_whole_window_reaching_one_to_four_steps(con):
    assert rows(con, 'SELECT min(visit_date), max(visit_date) FROM visits') == [(FIRST, LAST)]
    assert rows(con, 'SELECT min(reached), max(reached), count(DISTINCT reached) FROM visits') == [
        (1, 4, 4)
    ]


def test_visits_has_a_small_finnish_cell_with_four_visits_from_the_newsletter(con):
    assert rows(
        con, "SELECT source, count(*) FROM visits WHERE country = 'FI' GROUP BY ALL ORDER BY 1"
    ) == [('ads', 96), ('newsletter', 4)]


def test_visits_come_most_from_norway(con):
    assert rows(con, 'SELECT country, count(*) FROM visits GROUP BY ALL ORDER BY 2 DESC, 1') == [
        ('NO', 2000),
        ('DK', 750),
        ('SE', 750),
        ('FI', 100),
    ]


def test_visits_reverses_between_the_sources_and_the_total_simpsons_paradox(con):
    cells = rows(
        con,
        'SELECT country, source, sum((reached = 4)::INTEGER), count(*) FROM visits '
        "WHERE country IN ('DK', 'SE') GROUP BY ALL ORDER BY ALL",
    )
    assert [(c, s, n) for c, s, _, n in cells] == [
        ('DK', 'ads', 650),
        ('DK', 'newsletter', 100),
        ('SE', 'ads', 100),
        ('SE', 'newsletter', 650),
    ]
    assert [(c, s, percent(h, n)) for c, s, h, n in cells] == [
        ('DK', 'ads', Decimal('10.2')),
        ('DK', 'newsletter', Decimal('24.0')),
        ('SE', 'ads', Decimal('6.0')),
        ('SE', 'newsletter', Decimal('20.2')),
    ]
    paid = {(c, s): h / n for c, s, h, n in cells}
    # Denmark beats Sweden in each source ...
    assert paid['DK', 'ads'] > paid['SE', 'ads']
    assert paid['DK', 'newsletter'] > paid['SE', 'newsletter']
    # ... and loses in the total, because Sweden's visits come from the newsletter
    total = rows(
        con,
        'SELECT country, sum((reached = 4)::INTEGER), count(*) FROM visits '
        "WHERE country IN ('DK', 'SE') GROUP BY ALL ORDER BY 1",
    )
    assert [(c, percent(h, n)) for c, h, n in total] == [
        ('DK', Decimal('12.0')),
        ('SE', Decimal('18.3')),
    ]


def test_deliveries_gives_norway_and_finland_the_same_mean_and_another_spread(con):
    got = rows(
        con,
        'SELECT country, avg(days), round(stddev_pop(days), 2) FROM deliveries '
        "WHERE country IN ('NO', 'FI') GROUP BY ALL ORDER BY 1",
    )
    # Norway from Bergen the next day to the far north in five; Finland two to four days
    assert got == [('FI', 3.0, 0.82), ('NO', 3.0, 1.63)]
    spread = 'SELECT DISTINCT days FROM deliveries WHERE country = {!r} ORDER BY 1'
    assert [d for (d,) in rows(con, spread.format('NO'))] == [1, 3, 5]
    assert [d for (d,) in rows(con, spread.format('FI'))] == [2, 3, 4]


def test_deliveries_has_one_lost_parcel_of_21_days_in_sweden(con):
    assert rows(con, 'SELECT order_no, country, days FROM deliveries WHERE days > 5') == [
        (297, 'SE', 21)
    ]
    assert rows(con, 'SELECT country, count(*) FROM deliveries GROUP BY ALL ORDER BY 1') == [
        ('DK', 60),
        ('FI', 60),
        ('NO', 240),
        ('SE', 120),
    ]


def test_shop_days_has_730_days_and_a_closed_sunday(con):
    assert rows(
        con, 'SELECT min(shop_date), max(shop_date), count(DISTINCT shop_date) FROM shop_days'
    ) == [(FIRST, LAST, 730)]
    assert one(con, 'SELECT max(walk_ins) FROM shop_days WHERE isodow(shop_date) = 7') == 0
    assert one(con, 'SELECT min(walk_ins) FROM shop_days WHERE isodow(shop_date) <> 7') > 0


def test_shop_days_rings_up_no_receipts_on_a_closed_day_and_never_more_than_walk_ins(con):
    assert one(con, 'SELECT count(*) FROM shop_days WHERE walk_ins = 0 AND receipts <> 0') == 0
    assert one(con, 'SELECT count(*) FROM shop_days WHERE walk_ins = 0') == 104
    assert one(con, 'SELECT count(*) FROM shop_days WHERE receipts > walk_ins') == 0
    assert one(con, 'SELECT min(receipts) FROM shop_days WHERE walk_ins > 0') > 0


def test_shop_days_rain_and_walk_ins_correlate_negatively(con):
    assert round(one(con, 'SELECT corr(rain_mm, walk_ins) FROM shop_days'), 2) == -0.40
    # without the closed Sundays the link is plain
    open_days = 'SELECT corr(rain_mm, walk_ins) FROM shop_days WHERE isodow(shop_date) <> 7'
    assert round(one(con, open_days), 2) == -0.80


def test_shop_days_gives_monday_to_wednesday_about_the_same_walk_ins_as_their_weight(con):
    # the noise cycles every five days, so it does not line up with the weekdays
    assert rows(
        con,
        'SELECT isodow(shop_date), sum(walk_ins), count(*) FROM shop_days '
        'WHERE isodow(shop_date) <= 3 GROUP BY ALL ORDER BY 1',
    ) == [(1, 3655, 104), (2, 3724, 105), (3, 3633, 105)]


def test_shop_days_rains_on_about_two_days_in_three(con):
    assert one(con, 'SELECT count(*) FROM shop_days WHERE rain_mm > 0') == 489
