"""The claims are complete and nothing is skipped (6.1 S6).

The claims are read from the test files' functions, and which of them await data on the
baseline is computed from the contract and a built baseline, not from this run of pytest (which
may be given other data folders).
"""

from __future__ import annotations

import importlib.util
import inspect
import re
from pathlib import Path

from roastery_spec import baseline
from roastery_spec.claims import Claim, awaiting, claim_of
from roastery_spec.contract import TABLES

TESTS = Path(__file__).parent
SPEC = TESTS.parent
NEW_TABLES = TESTS / 'test_new_tables.py'
# Built so that this line does not match itself.
FORBIDDEN = re.compile(
    'pytest' + r'\.(skip|xfail|importorskip)\(|mark' + r'\.(skip|skipif|xfail)\b'
)

# Every claim, by name: deleting or renaming one fails here, and a new claim is added by hand.
CLAIMS = (
    'test_checkout_test_is_the_product_page_visitors_with_a_variant',
    'test_customer_months_is_c_01s_year_recomputed_from_full',
    'test_customers_account_kind_is_consumer_or_business',
    'test_customers_account_kind_large_order_values_orders_are_business',
    'test_customers_none_with_an_order_in_the_volume_window_is_erased',
    'test_daily_sales_equals_the_web_consumer_lines_at_list_price',
    'test_deliveries_is_derived_from_shipments',
    'test_door_counts_none_on_sundays',
    'test_green_purchases_kg_above_zero',
    'test_green_purchases_kilos_bought_at_least_kilos_roasted',
    'test_lesson_ids_every_order_values_row_has_one_order',
    'test_lesson_ids_every_subscribers_row_has_one_subscription',
    'test_lesson_ids_order_values_match_their_orders',
    'test_lesson_ids_sets_are_order_values_and_subscribers',
    'test_order_values_300_is_a_return_at_the_counter',
    'test_order_values_amount_is_the_sum_of_the_orders_lines',
    'test_order_values_status_follows_from_payments_and_invoices',
    'test_orders_finland_drops_below_half_in_one_week',
    'test_orders_of_a_business_account_go_on_invoice',
    'test_pricing_rules_at_most_one_subscriber_rule_on_any_day',
    'test_pricing_rules_kinds_are_subscriber_and_campaign',
    'test_pricing_rules_one_rule_per_campaign_on_its_days',
    'test_product_costs_below_list_price_in_every_prices_period',
    'test_product_costs_periods_are_half_open_and_never_overlap',
    'test_shipments_belong_to_web_orders',
    'test_shipments_delivered_on_or_after_shipped',
    'test_shipments_order_297_takes_21_days',
    'test_shop_days_is_the_join_of_the_three_series',
    'test_stock_movements_balance_at_close_is_latest_stock',
    'test_stock_movements_balance_is_never_negative',
    'test_stock_movements_count_nothing_for_p10_p20_from_5_to_9_october',
    'test_stock_movements_open_the_week_with_42_and_5',
    'test_stock_movements_reasons_are_the_five',
    'test_subscribers_are_the_subscriptions_outside_the_cast',
    'test_subscription_events_belong_to_a_subscription',
    'test_subscription_events_cancel_on_every_ended_subscribers_day',
    'test_subscription_events_reason_is_never_null',
    'test_subscription_events_types_are_skip_pause_resume_cancel',
    'test_subscription_shipments_at_most_one_per_subscription_and_month',
    'test_subscription_shipments_none_in_a_skipped_or_paused_month',
    'test_subscription_shipments_october_bags_of_p10_p20_ship_before_5_october',
    'test_subscription_shipments_only_while_the_subscription_runs',
    'test_subscription_shipments_qty_above_zero',
    'test_till_day_totals_none_on_sundays',
    'test_visits_are_the_web_visits_with_a_referrer',
    'test_weather_days_rain_never_negative',
    'test_web_visits_hold_their_events_by_the_30_minute_rule',
    'test_week_no_customer_outside_the_cast_buys_p10_or_p20_in_full',
    'test_week_no_customer_outside_the_cast_buys_p10_or_p20_in_month',
    'test_week_the_till_rings_only_r_5001_before_7_october_in_full',
    'test_week_the_till_rings_only_r_5001_before_7_october_in_month',
    'test_week_the_till_sells_no_p10_or_p20_in_full',
    'test_week_the_till_sells_no_p10_or_p20_in_month',
)


def _tests_of(path: Path) -> dict[str, object]:
    spec = importlib.util.spec_from_file_location(f'_claims_meta_{path.stem}', path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name: value for name, value in vars(module).items() if name.startswith('test_')}


def _claims() -> dict[str, Claim]:
    found: dict[str, Claim] = {}
    for path in sorted(TESTS.glob('test_*.py')):
        if path.name == Path(__file__).name:
            continue
        for name, test in _tests_of(path).items():
            claimed = claim_of(test)
            if claimed:
                assert name not in found, f'two claims named {name}'
                found[name] = claimed
    return found


def _new_needs() -> set[str]:
    """The 1.0 tables, and the 1.0 columns of baseline tables as table.column."""
    needs = {t.name for t in TABLES if t.since == '1.0'}
    needs |= {f'{t.name}.{c.name}' for t in TABLES for c in t.added}
    return needs


def test_the_claims_are_the_frozen_list():
    assert sorted(_claims()) == sorted(CLAIMS)
    assert len(CLAIMS) == len(set(CLAIMS))


def test_every_test_in_test_new_tables_is_a_claim():
    tests = _tests_of(NEW_TABLES)
    assert tests
    assert [name for name, test in tests.items() if claim_of(test) is None] == []


def test_every_claim_takes_its_extract_as_a_fixture():
    for path in sorted(TESTS.glob('test_*.py')):
        for name, test in _tests_of(path).items():
            claimed = claim_of(test)
            if claimed:
                assert claimed.extract in inspect.signature(test).parameters, name


def test_every_claim_names_a_table_of_the_contract():
    known = {t.name for t in TABLES} | _new_needs()
    for name, claimed in _claims().items():
        assert set(claimed.tables) <= known, name


def test_every_new_table_and_column_has_a_claim():
    claimed = {need for c in _claims().values() for need in c.tables}
    assert sorted(_new_needs() - claimed) == []


def test_the_claims_awaiting_data_on_the_baseline_are_exactly_the_new_tables(tmp_path):
    claims = _claims()
    baseline.build(tmp_path)
    expected = {name for name, c in claims.items() if set(c.tables) & _new_needs()}
    built = {name for name, c in claims.items() if awaiting(c.tables, tmp_path)}
    unbuilt = {name for name, c in claims.items() if awaiting(c.tables, None)}
    assert expected
    assert built == expected
    assert unbuilt == expected


def test_nothing_in_the_spec_is_skipped():
    found = []
    for path in sorted(SPEC.rglob('*.py')):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if FORBIDDEN.search(line):
                found.append(f'{path.relative_to(SPEC).as_posix()}:{number}')
    assert found == []
