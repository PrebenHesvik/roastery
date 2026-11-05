"""The volume's world: the allocator and its feasibility check (6.5, U3).

`build` gives the World the volume plays: the script's steps as they are (the week, C-01's
year, the jobs of the week), less the setup's four stock steps, and around them the generated
trade of 1 January 2024 to 31 October 2026, made in the plan's order of satisfaction: the
lesson orders of `order_values`, the 240 subscribers, the business accounts, the filler demand
of `daily_sales` (the panel's reached-4 orders first), Finland's week, the panel and the test,
the outside series, the stock and the jobs. Every generated row is named by a handle (V4);
`lesson_ids` and the panel's customers are handles, which a play resolves.

`feasibility` checks the targets can be met before any step is made and says, per
constraint, how much room is left or which day binds; it raises `Infeasible` naming the day
and product, or the rule, that cannot be met.

The teaching window (V3, reopened in U7) is [5 Oct 2026 00:00, 10 Oct 2026 07:00] UTC. In it a
generated step is only a Place or Pay of P-11 and P-21 lines by a customer registered before
it, a Ship or Deliver of a generated parcel, or a NightlyExtract; none falls in the BLACKOUT
before E-09's lone batch, and none sits at a moment of the script. After the window a generated
Ship or Deliver may name a cast order; nothing else generated ever names a cast id.
"""

from __future__ import annotations

import bisect
import datetime as dt
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from random import Random
from typing import Final

from roastery.catalogue import BeanDetails
from roastery.checkout import Item, PlaceOrder
from roastery.customer import Email
from roastery.ids import (
    AccountKind,
    Country,
    CustomerId,
    OrderId,
    PaymentId,
    PostalCode,
    ProductId,
    SubscriptionId,
)
from roastery.money import Money, Qty

from roastery_sim import panel as panel_plan
from roastery_sim import script, series
from roastery_sim.outside import (
    DoorCount,
    FxRate,
    TillDayTotal,
    TillLine,
    TillReceipt,
    WeatherDay,
    WebEvent,
    WebVisit,
)
from roastery_sim.script import (
    Action,
    AddCampaign,
    AddProduct,
    BuyGreen,
    CancelOrder,
    CancelSubscription,
    CountAtClose,
    Credit,
    CsvExport,
    Deliver,
    Erase,
    Invoice,
    NightlyExtract,
    Pause,
    Pay,
    Place,
    Refund,
    Register,
    Relay,
    Resume,
    Roast,
    SetCost,
    SetSubscriberDiscount,
    Settle,
    Ship,
    ShipBags,
    Skip,
    Step,
    Stocktake,
    Subscribe,
    World,
    WriteOff,
)
from roastery_sim.targets import Lesson, Targets

# The fixed days and moments ------------------------------------------


def _utc(year: int, month: int, day: int, hour: int, minute: int) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.UTC)


def _at(day: dt.date, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute), tzinfo=dt.UTC)


FIRST_DAY: Final = dt.date(2024, 1, 1)
LAST_DAY: Final = dt.date(2026, 10, 31)
"""The days the world spans."""
WINDOW: Final = (dt.date(2024, 10, 1), dt.date(2026, 9, 30))
"""The tier-3 window: `daily_sales` fixes the web consumer bags of these days."""
COUNTED_ON: Final = dt.date(2026, 9, 30)
QUIET: Final = (_utc(2026, 10, 5, 0, 0), _utc(2026, 10, 10, 7, 0))
"""The teaching window, both ends in it (V3): only what `WINDOW_ACTIONS` names is generated."""
BLACKOUT: Final = (_utc(2026, 10, 6, 14, 0), _utc(2026, 10, 6, 15, 21))
"""Half-open: no generated step, so the 15:20:30 relay finds E-09 alone and takes nothing (W31)."""
WEEK: Final = (dt.date(2026, 10, 5), dt.date(2026, 10, 9))
FINLAND_WEEK: Final = (dt.date(2026, 4, 20), dt.date(2026, 4, 26))
"""ISO week 2026-W17, when Finland's consumers buy about a quarter as much (V8)."""
TEST_DAYS: Final = (dt.date(2026, 3, 2), dt.date(2026, 4, 10))
RULE_DAYS: Final = (dt.date(2024, 6, 1), dt.date(2025, 6, 1))
RULE_PERCENT: Final = 10
"""The subscriber rule, half-open (V7)."""
OPENING_AT: Final = _utc(2026, 10, 4, 12, 0)
OPENING: Final[Mapping[str, int]] = {'P-10': 42, 'P-11': 12, 'P-20': 5, 'P-21': 2}
"""The stocktakes that land the balance before the week (V10, W8). P-10 and P-20 are exact;
P-11 and P-21 are floors, raised to cover the week's own filler."""
AFTER_WEEK: Final = _utc(2026, 10, 10, 8, 0)
"""The first restock after the window."""

CUSTOMER_HOURS: Final = (dt.time(9, 0), dt.time(16, 0))
"""Every generated customer step is at or between these, UTC: no zone moves its date."""
CUSTOMER_ACTIONS: Final = (
    Register,
    Subscribe,
    CancelSubscription,
    Skip,
    Pause,
    Resume,
    Place,
    Pay,
    Settle,
    Invoice,
    Credit,
    Refund,
)
WINDOW_ACTIONS: Final = (Place, Pay, Ship, Deliver, NightlyExtract)
"""What a generated step in the teaching window may be."""
FORBIDDEN: Final = (
    script.AddCategory,
    AddProduct,
    script.SetPrice,
    AddCampaign,
    script.Change,
    Erase,
)
"""Nothing generated makes or changes these (V3)."""

PLACEHOLDER: Final = CustomerId('C-0')
"""A `PlaceOrder` holds a valid id; a generated Place names its customer by handle."""
_CAST: Final = frozenset(
    x.value for x in (*script.CAST.customers, *script.CAST.orders, *script.CAST.subscriptions)
)
COUNTRIES: Final[tuple[Country, ...]] = ('NO', 'SE', 'DK', 'FI')
SHARE: Final[Mapping[str, int]] = {'NO': 48, 'SE': 25, 'DK': 12, 'FI': 15}
"""Who buys the filler, by country, per hundred orders."""
FINLAND_CUT: Final = 4
"""In its week Finland's consumers place at most a quarter of their usual filler orders."""
CURRENCY: Final[Mapping[str, str]] = {'NO': 'NOK', 'SE': 'SEK', 'DK': 'DKK', 'FI': 'EUR'}
NEW_CUSTOMER: Final = 0.11
"""The chance a consumer order is a new customer's: about 1,500 over the span."""
TWO_BAGS: Final = 0.35
SECOND_LINE: Final = 0.12
BAGS_PER_ORDER: Final = 1.39
"""What the filler's draws give on average; feasibility estimates order counts with it."""
FINLAND_MEAN: Final = 12
"""Feasibility refuses a mean of Finland's four weeks around its week below this."""
DRAWN_MEAN: Final = 10
"""The claim's floor for the drawn mean (`test_orders_finland_drops_below_half_in_one_week`)."""
DELIVERY_DAYS: Final[Mapping[str, tuple[int, ...]]] = {
    'NO': (1, 1, 2, 3, 3, 5),
    'SE': (2, 3, 4),
    'DK': (1, 2, 3),
    'FI': (2, 3, 4),
}
SUBSCRIPTION_MOVES: Final = 6
"""About one subscription in this many skips a month or pauses."""
OCTOBER_STARTS: Final = 0.3
"""The chance of a new subscription on a day after the window (about the volume's rate)."""
OCTOBER_PAUSES: Final = 12
"""About one running subscription in this many pauses after the window."""
JOIN_DAYS: Final = 7
"""A pool consumer registers on the day of their first view or up to this many days before."""
BUSINESS_DAILY: Final = 0.05
"""The chance a business account orders on a weekday after the window: about its 2026 rate."""

LOST_PARCEL: Final = 297
REFUND: Final = 300
CAFE: Final = 600
REFUND_ID: Final = PaymentId('PAY-99001')
PAYMENT_FIRST: Final = 200001
"""Generated payments are PAY-200001 on: clear of the week's, the year's and the tests'."""

_P10, _P11, _P20, _P21 = script.P10, script.P11, script.P20, script.P21
_STOCKED: Final = (_P10, _P11, _P20, _P21)
_BEANS: Final = (_P10, _P11)
_IN_WINDOW: Final = (_P11, _P21)
"""What other customers buy in the teaching week: the cast's P-10 and P-20 stay its own."""
_GREEN: Final[Mapping[ProductId, tuple[str, Decimal]]] = {
    _P10: ('Ethiopia', Decimal('92.00')),
    _P11: ('Brazil', Decimal('68.00')),
}
"""The green beans each roast is made from, and their base price per kilo."""
_COSTS: Final[Mapping[ProductId, tuple[Decimal, Decimal, Decimal]]] = {
    _P10: (Decimal('23.00'), Decimal('6.50'), Decimal('8.00')),
    _P11: (Decimal('68.00'), Decimal('9.00'), Decimal('22.00')),
}
"""A bag's green, packaging and roasting cost in 2024; each later year adds a little."""

_NAMES: Final[Mapping[str, tuple[str, ...]]] = {
    'NO': tuple(
        'Kari Ola Nora Emil Sofie Henrik Ida Jonas Maja Sigrid Astrid Bjorn Eirik Frida Geir'
        ' Hanne Ivar Jorunn Kjell Liv Magnus Nils Oda Petter Ragnhild Silje Torunn Unni Vegard'
        ' Wenche Anders Berit Camilla Dag Elin Finn Gunnhild Hakon Inger Jan Karin Leif Marit'
        ' Nina Ole Per Randi Solveig Terje Trude Vidar Aud Bente Cecilie Erlend Gro Halvor'
        ' Ingvild Jostein Kristin Lene Morten Oddny Ragnar Siri Steinar Thea Ulrik Vilde Anette'
        ' Brede Didrik Eline Fredrik Guro Herman Iselin Jakob Kaja Linnea Mathias Synnove Arne'
        ' Borghild Even Hedda Ottar'.split()
    ),
    'SE': tuple(
        'Anna Erik Elsa Johan Oskar Linnea Nils Ebba Agnes Axel Birgitta Carl Dagny Elias Filip'
        ' Gustav Hedvig Ingela Jonna Karl Lena Linus Malin Moa Olle Pernilla Rut Sixten Stina'
        ' Tove Ulf Valter Viktor Wilma Alva Bengt Cecilia Daniel Emil Freja Gunnar Hampus Ivan'
        ' Jenny Kerstin Lisa Ludvig Maria Mats Nora Ove Petra Rebecka Siv Svante Tilda Torsten'
        ' Ulla Vera Yngve Albin Britt Elin Felicia Goran Hugo Ines Josefin Klara Leo Majken'
        ' Max Selma Sten Thilde Vilgot Wera Ylva Ake Folke Greta Tyra Algot'.split()
    ),
    'DK': tuple(
        'Freja Mads Clara Rasmus Emma Jens Anders Bente Christian Dorthe Esben Frederik Grethe'
        ' Hans Ida Jakob Karen Lone Mette Niels Ole Pia Rikke Soren Tine Ulla Viggo Asger Birthe'
        ' Carsten Ditte Erik Flemming Gitte Henrik Inge Jesper Kirsten Laura Morten Nanna Poul'
        ' Rasmine Sanne Thomas Tove Vibeke Aksel Bodil Casper Dagmar Elise Finn Gry Holger Iben'
        ' Jonas Kasper Lise Magnus Nikolaj Oliver Pernille Signe Sofus Trine Valdemar Agnete'
        ' Bjarke Cecilie Emil Frida Gustav Helle Jeppe Kamma Lasse Marie Ebbe Jytte Knud'.split()
    ),
    'FI': tuple(
        'Helmi Juho Venla Onni Lauri Elina Aada Antti Eero Eila Heikki Iida Ilkka Jaana Jari'
        ' Kaarina Kalle Kirsi Lassi Leena Matti Merja Mikko Minna Niina Olli Paivi Pekka Pirjo'
        ' Reijo Riikka Sami Sanna Seppo Taina Teemu Tuula Ville Aleksi Anni Eetu Emilia Hannu'
        ' Heli Inkeri Jukka Kaisa Kimmo Linnea Markku Marjatta Nea Oskari Outi Pasi Raili Risto'
        ' Saara Sakari Tarja Timo Topias Ulla Veikko Vilma Aarne Elias Emmi Hilkka Jouni Kerttu'
        ' Lotta Mauno Oona Petra Tapio Veera Arvo Ilona Jarmo Sirpa Urho'.split()
    ),
}
"""Generated first names, ASCII; none is a name of the cast or of the club's members (U7)."""
_BUSINESS: Final = (
    ('Kaffebar Bryggen', 'NO', '5003'),
    ('Fjordkontoret', 'NO', '0150'),
    ('Cafe Soder', 'SE', '11820'),
    ('Kontorkaffe Malmo', 'SE', '21119'),
    ('Kaffebar Norrebro', 'DK', '2200'),
    ('Kontor Aarhus', 'DK', '8000'),
    ('Kahvila Kallio', 'FI', '00530'),
    ('Toimisto Tampere', 'FI', '33100'),
)
"""The eight business accounts, two per country; the Bergen cafe takes order 600 (V6)."""

_NO_PRODUCT: Final = ('2000000000992', Decimal('45.00'))
"""The till's code with no product: a pastry."""
_LOOSE: Final = '2100000000111'
_LOOSE_GRAMS: Final = (100, 250, 500)


# The report -----------------------------------------------------------


class Infeasible(ValueError):
    """The targets cannot be met: `where` names the day and product, or the rule."""

    def __init__(self, where: str, why: str) -> None:
        super().__init__(f'{where}: {why}')
        self.where = where
        self.why = why


@dataclass(frozen=True)
class Bound:
    """One constraint: the room left, and what binds it."""

    constraint: str
    slack: int
    binding: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class Report:
    """What `feasibility` found, constraint by constraint."""

    bounds: tuple[Bound, ...]
    misfits: tuple[int, ...]
    """The lesson web orders that exceed their day's quota: business orders (V6)."""

    def lines(self) -> tuple[str, ...]:
        found = [f'misfits ({len(self.misfits)}): {", ".join(map(str, self.misfits))}']
        for b in self.bounds:
            binding = ', '.join(b.binding[:6]) + (' ...' if len(b.binding) > 6 else '')
            found.append(f'{b.constraint}: slack {b.slack}; binding {binding or "-"}; {b.note}')
        return tuple(found)


# The fit: what the lessons and C-01's year take of daily_sales ---------


@dataclass(frozen=True)
class _Fit:
    misfits: tuple[int, ...]
    business: frozenset[int]
    filler: Mapping[tuple[dt.date, ProductId], int]


def _days(first: dt.date, last: dt.date) -> list[dt.date]:
    return [first + dt.timedelta(days=n) for n in range((last - first).days + 1)]


def _lesson_lines(lesson: Lesson) -> list[tuple[ProductId, int]]:
    lines = [(ProductId(lesson.coffee), lesson.bags)]
    if lesson.p20:
        lines.append((_P20, 1))
    return lines


def _fit(targets: Targets) -> _Fit:
    big = {x.order_no for x in targets.lessons if x.bags >= 10 or x.order_no == CAFE}
    use: dict[tuple[dt.date, ProductId], int] = defaultdict(int)
    carriers: dict[tuple[dt.date, ProductId], list[Lesson]] = defaultdict(list)
    for lesson in targets.lessons:
        if lesson.channel != 'web' or lesson.order_no in big:
            continue
        for product, qty in _lesson_lines(lesson):
            use[lesson.order_date, product] += qty
            carriers[lesson.order_date, product].append(lesson)
    for day, lines in script.YEAR:
        for product, qty in lines:
            use[day, product] += qty
    moved: set[int] = set()
    for key in sorted(use, key=lambda k: (k[0], k[1].value)):
        day, product = key
        target = targets.daily_sales.get((day, product.value))
        if target is None:
            raise Infeasible(f'{day} {product}', 'a web consumer line where no price holds')
        while use[key] > target:
            left = [x for x in carriers[key] if x.order_no not in moved]
            if not left:
                raise Infeasible(f'{day} {product}', "C-01's year alone exceeds daily_sales")
            worst = max(left, key=lambda x: (x.bags, -x.order_no))
            moved.add(worst.order_no)
            for each, qty in _lesson_lines(worst):
                use[worst.order_date, each] -= qty
    filler: dict[tuple[dt.date, ProductId], int] = {}
    for day in _days(FIRST_DAY, LAST_DAY):
        week = WEEK[0] <= day <= WEEK[1]
        for product in _IN_WINDOW if week else _STOCKED:
            if WINDOW[0] <= day <= WINDOW[1]:
                target = targets.daily_sales.get((day, product.value))
                quota = 0 if target is None else target - use.get((day, product), 0)
            else:
                quota = targets.demand(day, product.value) or 0
            if quota < 0:
                raise Infeasible(f'{day} {product}', f'the filler would be {quota}')
            if quota:
                filler[day, product] = quota
    return _Fit(tuple(sorted(moved)), frozenset(big | moved), filler)


def _settle_day(ordered: dt.date) -> dt.date:
    """A business invoice's settle day: two weeks after the order, or its next settle day if
    sooner. The settle days are the months' last days, the order's own day not counted."""
    month_end = _months_after(ordered, 1) - dt.timedelta(days=1)
    if month_end == ordered:
        month_end = _months_after(ordered, 2) - dt.timedelta(days=1)
    return min(ordered + dt.timedelta(days=14), month_end)


def _lesson_ship(lesson: Lesson) -> dt.date:
    return lesson.order_date + dt.timedelta(days=1)


def _deliver_moment(day: dt.date) -> dt.datetime:
    """A lesson's delivery, at 12:00 UTC on its day."""
    return _at(day, 12)


def _promised(shipped: dt.date) -> dt.date:
    """A parcel's promised day: two days after it ships, as the script's (W31)."""
    return shipped + dt.timedelta(days=2)


def _script_moves(steps: Iterable[Step]) -> list[tuple[dt.datetime, ProductId, int]]:
    """The stock moves of the script's own steps, in their order: a Place takes its lines, a
    CancelOrder puts back the cancelled order's own lines, a Roast adds its bags."""
    lines: dict[str, tuple[tuple[ProductId, int], ...]] = {}
    moves: list[tuple[dt.datetime, ProductId, int]] = []
    for step in steps:
        match step.action:
            case Place(order, handle):
                made = tuple((item.product_id, item.qty.value) for item in order.items)
                lines[step.ids['order'][0] if 'order' in step.ids else handle] = made
                moves += [(step.at, product, -qty) for product, qty in made]
            case CancelOrder(ref):
                key = ref.value if isinstance(ref, OrderId) else ref
                if key not in lines:
                    raise ValueError(f'{key} is cancelled, never placed')
                moves += [(step.at, product, qty) for product, qty in lines[key]]
            case Roast(product, bags):
                moves.append((step.at, product, bags.value))
            case _:
                continue
    return moves


def _week_balance() -> dict[ProductId, int]:
    """The lowest balance of each product from the opening stocktakes to the restock after the
    window, with the week's own moves only (nothing generated moves stock in the window)."""
    level = {ProductId(p): n for p, n in OPENING.items()}
    low = dict(level)
    for at, product, qty in _script_moves(script.steps()):
        if OPENING_AT <= at < AFTER_WEEK:
            level[product] = level.get(product, 0) + qty
            low[product] = min(low.get(product, level[product]), level[product])
    return low


def feasibility(targets: Targets) -> Report:
    """Check the targets before any step is made; raises Infeasible naming the day and product,
    or the rule, that cannot be met."""
    return _check(targets, _fit(targets))[0]


def _check(targets: Targets, fit: _Fit) -> tuple[Report, dt.date]:
    """`feasibility` on a fit made once; the report and the day of order 300's sale."""
    bounds: list[Bound] = []
    by_lesson = {x.order_no: x for x in targets.lessons}

    # the filler: target less the lessons' consumer bags and C-01's year
    window = {k: v for k, v in fit.filler.items() if WINDOW[0] <= k[0] <= WINDOW[1]}
    zero = sorted(
        f'{day} {p}'
        for day in _days(*WINDOW)
        for p in _STOCKED
        if (day, p) not in window and targets.daily_sales.get((day, p.value)) is not None
    )
    bounds.append(
        Bound(
            'daily_sales filler >= 0',
            0 if zero else min(window.values()),
            tuple(zero),
            f'{len(zero)} day-products fully taken by lessons and the year; '
            f'{len(fit.misfits)} lesson orders moved to business accounts',
        )
    )
    if len(fit.misfits) != 13:
        raise Infeasible('V6', f'{len(fit.misfits)} misfit lesson orders, the owner named 13')

    # the panel: every reached-4 visit needs a bag of its day's filler
    anchors: dict[dt.date, int] = defaultdict(int)
    for v in targets.visits:
        if v.reached == 4:
            anchors[v.visit_date] += 1
    room = []
    for day, n in anchors.items():
        bags = sum(fit.filler.get((day, p), 0) for p in _STOCKED)
        room.append((bags - n, str(day)))
    room.sort()
    short = tuple(f'{d} short {-s}' for s, d in room if s < 0)
    bounds.append(
        Bound(
            'reached-4 anchors <= filler bags',
            room[0][0],
            short or tuple(d for s, d in room if s == room[0][0]),
            f'{sum(anchors.values())} anchors on {len(anchors)} days; an anchor the filler '
            "cannot hold is a business account's one-bag web order (out of daily_sales)",
        )
    )
    per_day = defaultdict(int)
    for v in targets.visits:
        per_day[v.visit_date] += 1
    busiest = max(per_day.values())
    last = 10 * 60 + (busiest - 1) * panel_plan.PANEL_SPREAD + 7
    bounds.append(
        Bound(
            'panel orders by 16:00 UTC',
            16 * 60 - last,
            tuple(str(d) for d, n in sorted(per_day.items()) if n == busiest),
            f'at most {busiest} visits a day, the last order at {last // 60}:{last % 60:02d}',
        )
    )

    # Finland's week: its four weeks around keep a mean of FINLAND_MEAN, the week below half
    weeks = _finland_estimate(targets, fit)
    around = [weeks[FINLAND_WEEK[0] + dt.timedelta(weeks=k)] for k in (-2, -1, 1, 2)]
    mean = sum(around) / 4
    drop = weeks[FINLAND_WEEK[0]]
    if mean < FINLAND_MEAN:
        raise Infeasible(f'{FINLAND_WEEK[0]} FI', f'the four weeks around have a mean {mean:.1f}')
    if drop >= mean / 2:
        raise Infeasible(f'{FINLAND_WEEK[0]} FI', f'the week has {drop:.1f}, not below half')
    bounds.append(
        Bound(
            'Finland: mean around 2026-W17 >= 12, W17 < half',
            math.floor(mean - FINLAND_MEAN),
            ('2026-W15', '2026-W16', '2026-W18', '2026-W19'),
            f'estimated mean {mean:.1f} orders a week, W17 {drop:.1f}',
        )
    )

    # the lesson parcels: each ships the day after its order, no step in the blackout
    for d in targets.deliveries:
        lesson = by_lesson[d.order_no]
        if d.shipped_on != _lesson_ship(lesson):
            raise Infeasible(f'order {d.order_no}', 'deliveries ships it on another day')
        arrives = d.shipped_on + dt.timedelta(days=d.days)
        for at in (_at(d.shipped_on, 9), _deliver_moment(arrives)):
            if BLACKOUT[0] <= at < BLACKOUT[1]:
                raise Infeasible(f'order {d.order_no}', f'a lesson step at {at}, in the blackout')
    last_in = max(d.shipped_on + dt.timedelta(days=d.days) for d in targets.deliveries)
    bounds.append(
        Bound(
            'lesson parcels: shipped the next day, none in the blackout',
            (QUIET[0].date() - last_in).days,
            (),
            f'the last lesson delivery is on {last_in}',
        )
    )

    # the week's stock: the opening stocktakes cover the cast's sales to the restock after
    low = _week_balance()
    least_stock = min(low.values())
    if least_stock < 0:
        raise Infeasible(f'{OPENING_AT} stock', f'the week takes the balance to {low}')
    bounds.append(
        Bound(
            "the opening stock covers the week's sales",
            least_stock,
            tuple(
                f'{p} {n}'
                for p, n in sorted(low.items(), key=lambda kv: kv[0].value)
                if n == least_stock
            ),
            'lowest balance per product: '
            + ', '.join(f'{p} {n}' for p, n in sorted(low.items(), key=lambda kv: kv[0].value)),
        )
    )

    # order 300: a Norwegian NOK sale of P-20, delivered before the counter credit
    credit_day = by_lesson[REFUND].order_date
    sale_days = [
        d for (d, p), n in fit.filler.items() if p == _P20 and d <= _sale_limit(credit_day)
    ]
    if not sale_days:
        raise Infeasible(f'{credit_day} P-20', 'no grinder sold before order 300 to credit')
    bounds.append(
        Bound(
            'order 300 has a P-20 sale to credit',
            len(sale_days) - 1,
            (str(max(sale_days)),),
            'the sale is the latest such filler day',
        )
    )
    sale_day = max(sale_days)

    # A14: the subscriber rule stays off C-01's list-price year, and off every lesson
    first_year = script.YEAR[0][0]
    first_lesson = min(x.order_date for x in targets.lessons)
    gap = min((first_year - RULE_DAYS[1]).days, (first_lesson - RULE_DAYS[1]).days)
    if gap < 0:
        raise Infeasible('A14', 'the subscriber rule overlaps a list-price order')
    bounds.append(
        Bound(
            'A14: the subscriber rule ends before list-price orders',
            gap,
            (f'rule ends {RULE_DAYS[1]}', f'first lesson {first_lesson}'),
            f"C-01's year starts {first_year}",
        )
    )

    # the subscribers: those that end on the 3rd skip that month's bag
    third = tuple(
        f'subscriber {s.subscription_id} ends {s.ended}'
        for s in targets.subscribers
        if s.ended is not None and s.ended.day == 3
    )
    if len(targets.subscribers) != 240:
        raise Infeasible('subscribers', f'{len(targets.subscribers)}, not 240')
    bounds.append(
        Bound(
            'subscribers: no bag on or after the end',
            0 if third else 1,
            third,
            'each ends at 12:00 on a day the 06:00 bag run already shipped: a skip on the 1st',
        )
    )
    return Report(tuple(bounds), fit.misfits), sale_day


def _sale_limit(credit_day: dt.date) -> dt.date:
    """The last day order 300's sale may be placed: delivered (creditable) a week before."""
    return credit_day - dt.timedelta(days=8)


def _finland_estimate(targets: Targets, fit: _Fit) -> dict[dt.date, float]:
    """Finland's consumer orders per ISO week near its week, as the draws give on average."""
    weeks: dict[dt.date, float] = defaultdict(float)
    for (day, _), bags in fit.filler.items():
        monday = day - dt.timedelta(days=day.weekday())
        if abs((monday - FINLAND_WEEK[0]).days) > 21:
            continue
        cut = FINLAND_WEEK[0] <= day <= FINLAND_WEEK[1]
        share = SHARE['FI'] / sum(SHARE.values()) / (FINLAND_CUT if cut else 1)
        weeks[monday] += bags / BAGS_PER_ORDER * share
    countries = {d.order_no: d.country for d in targets.deliveries}
    for x in targets.lessons:
        if x.order_no in fit.business or countries.get(x.order_no) != 'FI':
            continue
        weeks[x.order_date - dt.timedelta(days=x.order_date.weekday())] += 1
    return weeks


# The volume -----------------------------------------------------------


@dataclass(frozen=True)
class Key:
    """What the world planted on purpose, for the manifests' `scripted_events` (V13)."""

    finland_week: tuple[dt.date, dt.date]
    test_days: tuple[dt.date, dt.date]
    business: tuple[str, ...]
    """The business accounts' Register handles."""
    misfits: tuple[int, ...]
    lost_parcel: int
    refund: int


@dataclass(frozen=True)
class Volume(World):
    """The volume's World, with the facts `play` does not read and the map the extracts need.

    The tracker's panel events name their customer by its Register handle, as `lesson_ids`
    names its orders and subscriptions: `Played.handles` resolves both.
    """

    web_visits: tuple[WebVisit, ...] = ()
    weather: tuple[WeatherDay, ...] = ()
    door_counts: tuple[DoorCount, ...] = ()
    till_day_totals: tuple[TillDayTotal, ...] = ()
    lesson_ids: tuple[tuple[str, int, str], ...] = ()
    """(lesson_set, row_no, handle): the order or subscription each tier-3 row stands for."""
    key: Key | None = None


_PRIO: Final[Mapping[type, int]] = {
    Register: 0,
    SetCost: 1,
    SetSubscriberDiscount: 1,
    BuyGreen: 1,
    Subscribe: 2,
    Stocktake: 3,
    Roast: 3,
    WriteOff: 4,
    Place: 5,
    Pay: 6,
    Invoice: 6,
    Settle: 6,
    Credit: 7,
    Refund: 8,
    Ship: 9,
    Deliver: 10,
    Skip: 11,
    Pause: 11,
    Resume: 11,
    CancelSubscription: 11,
    ShipBags: 12,
    CountAtClose: 13,
    Relay: 14,
    NightlyExtract: 15,
    CsvExport: 16,
}


@dataclass
class _Sub:
    """What the bag run needs to know of one subscription."""

    product: ProductId
    start: dt.datetime
    end: dt.datetime | None
    skipped: set[dt.date]
    paused: list[tuple[dt.datetime, dt.datetime]]

    def owes(self, at: dt.datetime) -> bool:
        if self.start >= at or (self.end is not None and self.end <= at):
            return False
        if at.date().replace(day=1) in self.skipped:
            return False
        return not any(p <= at < r for p, r in self.paused)


class _Builder:
    """The generated steps, as they are made; the stock's moves, for the plan of step 9."""

    def __init__(self, targets: Targets, seed: int, fit: _Fit) -> None:
        self.targets = targets
        self.rng = Random(seed)
        self.fit = fit
        self.script = [
            s
            for s in script.steps()
            if not (
                s.at < script.SETUP + dt.timedelta(hours=1)
                and isinstance(s.action, Roast | Stocktake)
            )
        ]
        self.taken = frozenset(s.at for s in self.script)
        self.steps: list[tuple[dt.datetime, int, int, Step]] = []
        self.moves: list[tuple[dt.datetime, ProductId, int]] = []
        self.payments = 0
        self.orders = 0
        self.customers = 0
        self.pool: dict[str, list[str]] = {c: [] for c in COUNTRIES}
        self.first: dict[str, dt.datetime] = {}
        self.country: dict[str, str] = {}
        self.ordered: dict[str, dt.datetime] = {}
        """Each customer handle's first order."""
        self.web_orders: list[tuple[dt.datetime, str]] = []
        """Every generated web order's moment and customer handle (the web visits follow)."""
        self.fx = _Rates(series.fx(seed=seed))
        self.campaigns = [
            (a.first_day, a.last_day, frozenset(a.product_ids), a.discount_pct)
            for s in self.script
            if isinstance(a := s.action, AddCampaign)
        ]

    # moments and steps

    def free(self, at: dt.datetime) -> dt.datetime:
        """`at`, or the next minute no script step holds, past the blackout."""
        while at in self.taken or BLACKOUT[0] <= at < BLACKOUT[1]:
            at = BLACKOUT[1] if BLACKOUT[0] <= at < BLACKOUT[1] else at + dt.timedelta(minutes=1)
        return at

    def add(self, at: dt.datetime, action: Action) -> None:
        if at in self.taken:
            raise ValueError(f'a generated step at a script moment: {at} {action!r}')
        if BLACKOUT[0] <= at < BLACKOUT[1]:
            raise ValueError(f'a generated step in the blackout: {at} {action!r}')
        window = QUIET[0] <= at <= QUIET[1]
        if window and not isinstance(action, WINDOW_ACTIONS):
            raise ValueError(f'a generated step in the teaching window: {at} {action!r}')
        if window and isinstance(action, Place):
            if any(item.product_id not in _IN_WINDOW for item in action.order.items):
                raise ValueError(f'a P-10 or P-20 line in the teaching window: {at} {action!r}')
        if (window or not isinstance(action, Ship | Deliver)) and _CAST & set(names(action)):
            raise ValueError(f'a generated step names the cast: {at} {action!r}')
        self.steps.append((at, _PRIO[type(action)], len(self.steps), Step(at, 'simulator', action)))

    # customers

    def register(
        self,
        at: dt.datetime,
        handle: str,
        name: str,
        country: Country,
        postal: str,
        kind: AccountKind = 'consumer',
        email: str | None = None,
    ) -> None:
        self.customers += 1
        mail = Email(email or f'{name.lower()}.{self.customers:05d}@example.invalid')
        action = Register(name, mail, country, PostalCode(postal), kind, handle)
        self.add(at, action)
        self.country[handle] = country

    def consumer(self, country: str, at: dt.datetime) -> str:
        """A consumer of the pool: an earlier one, or now and then a new one; in the teaching
        window only one who first bought before it, so no one registers in it."""
        known = self.pool[country]
        if QUIET[0] <= at <= QUIET[1]:
            handle = self.rng.choice([h for h in known if self.first[h] < QUIET[0]])
            self.first[handle] = min(self.first[handle], at)
            return handle
        if not known or self.rng.random() < NEW_CUSTOMER:
            handle = f'consumer {sum(map(len, self.pool.values())) + 1}'
            known.append(handle)
            self.country[handle] = country
            self.first[handle] = at
            return handle
        handle = self.rng.choice(known)
        self.first[handle] = min(self.first[handle], at)
        return handle

    def register_pool(self) -> None:
        """Each pool consumer registers a while before the first web event that names them:
        their first order's view (`_FIRST_VIEW` before it, a direct or a panel visit; a browse
        by a known consumer comes after an order). The day is the view's or up to JOIN_DAYS
        before it, never one that touches the teaching window; the minute is drawn in
        CUSTOMER_HOURS and before the view, clear of the script's moments."""
        for country in COUNTRIES:
            for handle in self.pool[country]:
                at = self.joined(self.first[handle] - _FIRST_VIEW)
                name = self.rng.choice(_NAMES[country])
                self.register(at, handle, name, country, _postal(self.rng, country))

    def joined(self, view: dt.datetime) -> dt.datetime:
        """A registration moment before `view`, as `register_pool` draws it."""
        day = view.date() - dt.timedelta(days=self.rng.randrange(JOIN_DAYS + 1))
        opens, closes = (_at(day, h.hour, h.minute) for h in CUSTOMER_HOURS)
        if day < FIRST_DAY or (opens <= QUIET[1] and closes >= QUIET[0]):
            day = view.date()
            opens, closes = (_at(day, h.hour, h.minute) for h in CUSTOMER_HOURS)
        latest = min(closes, view - dt.timedelta(minutes=1))
        if latest < opens:
            raise Infeasible(f'{view}', 'no minute to register before the first view')
        at = opens + dt.timedelta(minutes=self.rng.randrange((latest - opens) // _MINUTE + 1))
        while at in self.taken:
            at -= _MINUTE
        if at < opens:
            raise Infeasible(f'{view}', "every minute before the first view is the script's")
        return at

    # orders

    def price(self, product: ProductId, day: dt.date) -> Decimal:
        """The unit price the app gives a web line with no hand price (no subscriber buys)."""
        price = script.list_price(product, day)
        held = [
            pct for first, last, ps, pct in self.campaigns if first <= day <= last and product in ps
        ]
        if held:
            price = Money(price * Decimal(100 - max(held)) / 100, 'NOK').to_ore().amount
        return price

    def place(
        self,
        at: dt.datetime,
        customer: str,
        channel: str,
        lines: Sequence[tuple[ProductId, int]],
        *,
        handle: str | None = None,
        hand: bool = False,
    ) -> tuple[str, Decimal]:
        """A Place; the handle and the order's total in NOK."""
        if handle is None:
            self.orders += 1
            handle = f'order {self.orders}'
        day = at.date()
        items = []
        total = Decimal('0.00')
        for product, qty in lines:
            price = script.list_price(product, day) if hand else self.price(product, day)
            items.append(Item(product, Qty(qty), Money(price, 'NOK') if hand else None))
            total += price * qty
            self.moves.append((at, product, -qty))
        order = PlaceOrder(PLACEHOLDER, channel, tuple(items))  # type: ignore[arg-type]
        self.add(at, Place(order, handle, customer))
        self.ordered[customer] = min(self.ordered.get(customer, at), at)
        if channel == 'web':
            self.web_orders.append((at, customer))
        return handle, total

    def payment_id(self) -> PaymentId:
        self.payments += 1
        return PaymentId(f'PAY-{PAYMENT_FIRST + self.payments - 1}')

    def amount(self, country: str, nok: Decimal, day: dt.date) -> Money:
        currency = CURRENCY[country]
        if currency == 'NOK':
            return Money(nok, 'NOK')
        rate = self.fx.on(currency, day)
        return Money((nok / rate).quantize(Decimal('0.01'), ROUND_HALF_UP), currency)

    def pay(self, at: dt.datetime, handle: str, country: str, nok: Decimal) -> None:
        money = self.amount(country, nok, at.date())
        self.add(at, Pay(self.payment_id(), handle, money, at.date()))

    def settle(self, at: dt.datetime, handle: str, country: str, nok: Decimal) -> None:
        money = self.amount(country, nok, at.date())
        self.add(at, Settle(self.payment_id(), handle, money, at.date()))

    def invoice_paid(
        self, ordered: dt.datetime, handle: str, country: str, nok: Decimal, *, status: str = ''
    ) -> None:
        """A business invoice, placed at `ordered`, settled on its settle day (`_settle_day`)
        at 14:00 UTC.

        A lesson `paid` settles by the counted day, at 14:00 or a minute after its order if
        that is later (an order of the counted day itself); one `unpaid` stays open that day
        and is settled late, on a weekday of 12 to 30 October at a drawn minute; nothing
        settles after LAST_DAY.
        """
        day = _settle_day(ordered.date())
        at = _at(day, 14)
        if status == 'paid':
            at = self.free(max(_at(min(day, COUNTED_ON), 14), ordered + dt.timedelta(minutes=1)))
            if at.date() > COUNTED_ON or at.time() > CUSTOMER_HOURS[1]:
                raise Infeasible(f'{handle} at {ordered}', 'a paid lesson settles after its day')
            self.settle(at, handle, country, nok)
            return
        if status == 'unpaid':
            late = [
                d for d in _days(dt.date(2026, 10, 12), dt.date(2026, 10, 30)) if d.weekday() < 5
            ]
            minute = self.rng.randrange(10 * 60, 15 * 60)
            at = _at(self.rng.choice(late), minute // 60, minute % 60)
        if at.date() > LAST_DAY:
            return
        self.settle(self.free(at), handle, country, nok)

    def ship(self, at: dt.datetime, handle: str | OrderId, days: int) -> dt.date:
        """Ship an order and deliver it `days` later at about noon; nothing after LAST_DAY."""
        if at.date() > LAST_DAY:
            return at.date()
        at = self.free(at)
        self.add(at, Ship(handle, promised_by=_promised(at.date())))
        arrives = self.free(_at(at.date() + dt.timedelta(days=days), 12, self.rng.randrange(60)))
        if arrives.date() <= LAST_DAY:
            self.add(arrives, Deliver(handle))
        return at.date()

    def business_order(
        self,
        at: dt.datetime,
        account: str,
        country: str,
        lines: Sequence[tuple[ProductId, int]] = ((_P10, 1),),
    ) -> None:
        """A business account's web order (one bag of P-10 unless told): invoiced at place,
        settled on its settle day, shipped the next day."""
        handle, total = self.place(at, account, 'web', lines)
        self.invoice_paid(at, handle, country, total)
        ship = _at(at.date() + dt.timedelta(days=1), 9, self.rng.randrange(60))
        self.ship(ship, handle, self.rng.choice(DELIVERY_DAYS[country]))

    def lines(self, left: dict[ProductId, int]) -> list[tuple[ProductId, int]]:
        """One or two lines of one or two bags, drawn from what the day has left."""
        products = [p for p in _STOCKED if left.get(p, 0) > 0]
        first = self.rng.choices(products, weights=[left[p] for p in products])[0]
        qty = 2 if left[first] >= 2 and self.rng.random() < TWO_BAGS else 1
        left[first] -= qty
        drawn = [(first, qty)]
        others = [p for p in _STOCKED if p != first and left.get(p, 0) > 0]
        if others and self.rng.random() < SECOND_LINE:
            second = self.rng.choice(others)
            left[second] -= 1
            drawn.append((second, 1))
        return drawn

    def filler_order(
        self, at: dt.datetime, country: str, lines: Sequence[tuple[ProductId, int]]
    ) -> str:
        """A paid web order of a consumer, shipped the next day."""
        customer = self.consumer(country, at)
        handle, total = self.place(at, customer, 'web', lines)
        self.pay(self.free(at + dt.timedelta(minutes=1)), handle, country, total)
        ship = _at(at.date() + dt.timedelta(days=1), 9, self.rng.randrange(60))
        self.ship(ship, handle, self.rng.choice(DELIVERY_DAYS[country]))
        return customer


class _Rates:
    """The bank's rates: the latest on or before a day."""

    def __init__(self, rates: Iterable[FxRate]) -> None:
        held: dict[str, list[tuple[dt.date, Decimal]]] = defaultdict(list)
        for r in rates:
            held[r.currency].append((r.rate_date, r.nok_per_unit))
        self.by: dict[str, tuple[tuple[dt.date, ...], tuple[Decimal, ...]]] = {}
        for currency, rows in held.items():
            rows.sort()
            self.by[currency] = (tuple(d for d, _ in rows), tuple(v for _, v in rows))

    def on(self, currency: str, day: dt.date) -> Decimal:
        days, values = self.by[currency]
        n = bisect.bisect_right(days, day)
        if n == 0:
            raise ValueError(f'no {currency} rate on or before {day}')
        return values[n - 1]


def _postal(rng: Random, country: str) -> str:
    match country:
        case 'NO':
            return rng.choice(
                (
                    '5003',
                    '5006',
                    '5011',
                    '5015',
                    '5020',
                    '5053',
                    '0150',
                    '0560',
                    '0661',
                    '7030',
                    '4006',
                    '9008',
                )
            )
        case 'SE':
            return f'{rng.randrange(10000, 98500)}'
        case 'DK':
            return f'{rng.randrange(1000, 9990)}'
        case _:
            return f'{rng.randrange(100, 99900):05d}'


# The ten steps ----------------------------------------------------------


def _business(b: _Builder) -> dict[str, list[str]]:
    """Step 4: the eight accounts' handles, by country (they register once their first order
    is known, `_register_business`)."""
    accounts: dict[str, list[str]] = defaultdict(list)
    for n, (_, country, _) in enumerate(_BUSINESS):
        accounts[country].append(f'business {n + 1}')
    return accounts


def _register_business(b: _Builder) -> None:
    """Each account registers three to five weeks before its first order, at 09:00 UTC."""
    for n, (name, country, postal) in enumerate(_BUSINESS):
        handle = f'business {n + 1}'
        first = b.ordered[handle].date() - dt.timedelta(days=b.rng.randrange(21, 36))
        at = b.free(max(_at(first, 9, n), _utc(2024, 1, 2, 9, n)))
        mail = f'orders.{name.lower().replace(" ", ".")}@example.invalid'
        b.register(at, handle, name, country, postal, 'business', mail)  # type: ignore[arg-type]


def _october_business(b: _Builder, accounts: Mapping[str, list[str]]) -> None:
    """Business trade after the week: on a weekday from 12 October each account orders with
    a chance of BUSINESS_DAILY, two to ten bags of a bean, now and then of both."""
    for day in _days(dt.date(2026, 10, 12), LAST_DAY):
        if day.weekday() > 4:
            continue
        for country in COUNTRIES:
            for account in accounts[country]:
                if b.rng.random() >= BUSINESS_DAILY:
                    continue
                minute = b.rng.randrange(9 * 60 + 30, 15 * 60 + 30)
                lines = [(b.rng.choice(_BEANS), b.rng.randrange(2, 11))]
                if b.rng.random() < SECOND_LINE:
                    other = _P11 if lines[0][0] == _P10 else _P10
                    lines.append((other, b.rng.randrange(1, 5)))
                at = b.free(_at(day, minute // 60, minute % 60))
                b.business_order(at, account, country, lines)


def _lessons(b: _Builder, accounts: Mapping[str, list[str]]) -> list[tuple[str, int, str]]:
    """Step 2: the 600 lesson orders; order 300 is a counter credit (W16)."""
    t = b.targets
    countries = {d.order_no: d.country for d in t.deliveries}
    days = {d.order_no: d.days for d in t.deliveries}
    ids: list[tuple[str, int, str]] = []
    turn: dict[str, int] = defaultdict(int)
    for lesson in t.lessons:
        i = lesson.order_no
        handle = f'lesson {i}'
        ids.append(('order_values', i, handle))
        if i == REFUND:
            continue
        country = countries.get(i, 'NO')
        at = b.free(_at(lesson.order_date, 10) + dt.timedelta(minutes=b.rng.randrange(300)))
        business = i in b.fit.business
        if i == CAFE:
            customer = accounts['NO'][0]
        elif business:
            customer = accounts[country][turn[country] % 2]
            turn[country] += 1
        else:
            customer = b.consumer(country, at)
        shop = lesson.channel == 'shop'
        _, total = b.place(
            at, customer, lesson.channel, _lesson_lines(lesson), handle=handle, hand=shop
        )
        if total != lesson.amount:
            raise Infeasible(f'order {i}', f'lines give {total}, order_values {lesson.amount}')
        after = b.free(at + dt.timedelta(minutes=1))
        if business:
            b.invoice_paid(at, handle, country, total, status=lesson.status)
        elif lesson.status == 'paid':
            b.pay(after, handle, country, total)
        elif lesson.status == 'unpaid':
            b.add(after, Invoice(handle))
        if shop:
            continue
        ship = b.free(_at(_lesson_ship(lesson), 9))
        b.add(ship, Ship(handle, promised_by=_promised(ship.date())))
        b.add(b.free(_deliver_moment(ship.date() + dt.timedelta(days=days[i]))), Deliver(handle))
    return ids


def _refund(b: _Builder, sale_day: dt.date) -> None:
    """Order 300: a Norwegian consumer's NOK grinder, credited at the counter, refunded (W16)."""
    credit_day = next(x.order_date for x in b.targets.lessons if x.order_no == REFUND)
    at = b.free(_at(sale_day, 11))
    customer = b.consumer('NO', at)
    handle, total = b.place(at, customer, 'web', [(_P20, 1)], handle='sale of lesson 300')
    b.pay(b.free(at + dt.timedelta(minutes=1)), handle, 'NO', total)
    ship = b.free(_at(sale_day + dt.timedelta(days=1), 9, 30))
    b.add(ship, Ship(handle, promised_by=_promised(ship.date())))
    b.add(b.free(_at(ship.date() + dt.timedelta(days=1), 12)), Deliver(handle))
    credit = b.free(_at(credit_day, 10, 30))
    b.add(credit, Credit(handle, 1, f'lesson {REFUND}'))
    b.moves.append((credit, _P20, 1))
    refund = b.free(credit + dt.timedelta(minutes=1))
    b.add(refund, Refund(f'lesson {REFUND}'))
    message = Money(-total, 'NOK')  # the sale's own line, as the provider refunds it
    b.add(
        b.free(refund + dt.timedelta(minutes=1)),
        Pay(REFUND_ID, f'lesson {REFUND}', message, credit_day),
    )


def _subscribers(b: _Builder) -> tuple[list[tuple[str, int, str]], list[_Sub]]:
    """Step 3: the 240, each by its own new consumer; skips, pauses, the cancels."""
    ids: list[tuple[str, int, str]] = []
    subs: list[_Sub] = []
    weights = [SHARE[c] for c in COUNTRIES]
    for s in b.targets.subscribers:
        n = s.subscription_id
        customer = f'subscriber {n}'
        handle = f'subscription {n}'
        ids.append(('subscribers', n, handle))
        country = b.rng.choices(COUNTRIES, weights=weights)[0]
        name = b.rng.choice(_NAMES[country])
        b.register(b.free(_at(s.started, 9, 30)), customer, name, country, _postal(b.rng, country))
        start = b.free(_at(s.started, 10))
        product = ProductId(s.product_id)
        b.add(start, Subscribe(customer, product, handle))
        end = None if s.ended is None else b.free(_at(s.ended, 12))
        sub = _Sub(product, start, end, set(), [])
        moved = b.rng.randrange(SUBSCRIPTION_MOVES) == 0
        if s.ended is not None and s.ended.day == 3 and s.started < s.ended:
            month = s.ended.replace(day=1)
            skip_at = b.free(_at(max(month, s.started), 10, 30))
            b.add(skip_at, Skip(handle, 'cancelling this month'))
            sub.skipped.add(month)
        elif moved:
            _move(b, s.started, s.ended, handle, sub)
        if end is not None:
            b.add(end, CancelSubscription(handle, b.rng.choice(_ENDS)))
        subs.append(sub)
    return ids, subs


_ENDS: Final = ('customer asked', 'moving abroad', 'too much coffee', 'price')


def _months_after(day: dt.date, n: int) -> dt.date:
    month = day.month - 1 + n
    return dt.date(day.year + month // 12, month % 12 + 1, 1)


def _move(b: _Builder, started: dt.date, ended: dt.date | None, handle: str, sub: _Sub) -> None:
    """A skip of a month's bag (on its 1st), or a pause on a 10th and a resume on a 20th."""
    last = min(ended or COUNTED_ON, COUNTED_ON)
    if b.rng.random() < 0.5:
        month = _months_after(started, b.rng.randrange(1, 6))
        if month >= last:
            return
        b.add(b.free(_at(month, 10, 30)), Skip(handle, b.rng.choice(('travelling', 'enough left'))))
        sub.skipped.add(month)
        return
    paused = _months_after(started, b.rng.randrange(1, 6)).replace(day=10)
    resumed = _months_after(paused, b.rng.randrange(1, 3)).replace(day=20)
    if resumed >= last:
        return
    pause_at = b.free(_at(paused, 10, 30))
    resume_at = b.free(_at(resumed, 10, 30))
    b.add(pause_at, Pause(handle, 'on holiday'))
    b.add(resume_at, Resume(handle, 'back home'))
    sub.paused.append((pause_at, resume_at))


def _cast_subs(steps: Sequence[Step]) -> list[_Sub]:
    """The cast's subscriptions as the bag run sees them, read from the script's steps."""
    subs: dict[str, _Sub] = {}
    owner: dict[str, list[str]] = defaultdict(list)
    for step in steps:
        match step.action:
            case Subscribe(customer, product):
                sid = step.ids['subscription'][0]
                subs[sid] = _Sub(product, step.at, None, set(), [])
                owner[_value(customer)].append(sid)
            case CancelSubscription(ref):
                subs[_value(ref)].end = step.at
            case Erase(customer):
                for sid in owner[_value(customer)]:
                    if subs[sid].end is None:
                        subs[sid].end = step.at
            case _:
                continue
    return list(subs.values())


def _value(ref: object) -> str:
    return ref.value if isinstance(ref, CustomerId | SubscriptionId) else str(ref)


def _filler(
    b: _Builder,
    anchors: Mapping[dt.date, list[panel_plan.PanelVisit]],
    accounts: Mapping[str, list[str]],
) -> dict[int, str]:
    """Step 5 and 6: per day and product, the bags left, the panel's anchors first.

    An anchor takes one bag when the day has few left for the anchors after it; when none is
    left, its order is a one-bag web order of a business account of the visit's country,
    which daily_sales does not count.
    """
    placed: dict[int, str] = {}
    by_day: dict[dt.date, dict[ProductId, int]] = defaultdict(dict)
    for (day, product), n in b.fit.filler.items():
        by_day[day][product] = n
    turn: dict[str, int] = defaultdict(int)
    for day in sorted(set(by_day) | set(anchors)):
        left = by_day[day]
        visits = anchors.get(day, [])
        for n, visit in enumerate(visits):
            at = visit.order_at
            assert at is not None
            if at in b.taken:
                raise Infeasible(f'{at}', 'a panel order at a script moment')
            spare = sum(left.values()) - (len(visits) - n - 1)
            if spare >= 3:
                placed[visit.visit_id] = b.filler_order(at, visit.country, b.lines(left))
            elif spare >= 1:
                products = [p for p in _STOCKED if left.get(p, 0) > 0]
                one = b.rng.choices(products, weights=[left[p] for p in products])[0]
                left[one] -= 1
                placed[visit.visit_id] = b.filler_order(at, visit.country, [(one, 1)])
            else:
                account = accounts[visit.country][turn[visit.country] % 2]
                turn[visit.country] += 1
                placed[visit.visit_id] = account
                b.business_order(at, account, visit.country)
        cut = FINLAND_WEEK[0] <= day <= FINLAND_WEEK[1]
        share = SHARE['FI'] / sum(SHARE.values())
        quota = round(sum(left.values()) / BAGS_PER_ORDER * share / FINLAND_CUT)
        weights = [0 if cut and c == 'FI' else SHARE[c] for c in COUNTRIES]
        latest = 11 * 60 + 55 if day == OPENING_AT.date() else 15 * 60 + 55
        while any(n > 0 for n in left.values()):
            minute = b.rng.randrange(9 * 60 + 10, latest + 1)
            at = b.free(_at(day, minute // 60, minute % 60))
            if BLACKOUT[0] - dt.timedelta(minutes=10) <= at < BLACKOUT[1] + dt.timedelta(minutes=5):
                continue  # the order and its payment keep clear of the blackout
            if cut and quota > 0 and b.rng.random() < share:
                country, quota = 'FI', quota - 1
            else:
                country = b.rng.choices(COUNTRIES, weights=weights)[0]
            b.filler_order(at, country, b.lines(left))
    return placed


def _week_visits(events: Sequence[WebEvent], first: int) -> tuple[list[WebEvent], list[WebVisit]]:
    """The week's tracker events with their visit ids by the 30-minute rule (S18)."""
    countries = {'C-01': 'NO', 'C-02': 'SE', 'C-04': 'FI'}
    by_visitor: dict[str, list[WebEvent]] = defaultdict(list)
    for e in events:
        by_visitor[e.visitor_id].append(e)
    numbered: dict[str, int] = {}
    visits: list[WebVisit] = []
    for visitor in sorted(by_visitor, key=lambda v: min(e.event_at for e in by_visitor[v])):
        before = None
        for e in sorted(by_visitor[visitor], key=lambda e: (e.event_at, e.event_id)):
            if before is None or e.event_at - before > dt.timedelta(minutes=30):
                visit_id = first + len(visits)
                country = countries.get(e.customer_id or '', 'NO')
                visits.append(WebVisit(visit_id, visitor, e.event_at.date(), country, None, None))
            numbered[e.event_id] = visits[-1].visit_id
            before = e.event_at
    return [replace(e, visit_id=numbered[e.event_id]) for e in events], visits


def _october_subscriptions(b: _Builder, subs: list[_Sub]) -> None:
    """Step 3 after the window: a few new subscriptions by pool consumers who already bought,
    and pauses of running ones (half resumed by the end). No skip: a skip is dated in the
    month whose bag it skips, and October's bags shipped on the 3rd."""
    weights = [SHARE[c] for c in COUNTRIES]
    taken: set[str] = set()
    for day in _days(QUIET[1].date(), LAST_DAY):
        if b.rng.random() >= OCTOBER_STARTS:
            continue
        at = b.free(_at(day, 10, b.rng.randrange(60)))
        country = b.rng.choices(COUNTRIES, weights=weights)[0]
        known = [h for h in b.pool[country] if b.first[h] < at - dt.timedelta(days=1)]
        customer = b.rng.choice([h for h in known if h not in taken])
        taken.add(customer)
        product = b.rng.choice(_BEANS)
        b.add(at, Subscribe(customer, product, f'october subscription {len(taken)}'))
        subs.append(_Sub(product, at, None, set(), []))
    for s, sub in zip(b.targets.subscribers, subs, strict=False):
        if s.ended is not None or b.rng.randrange(OCTOBER_PAUSES):
            continue
        handle = f'subscription {s.subscription_id}'
        paused = b.free(_at(dt.date(2026, 10, b.rng.randrange(12, 25)), 10, b.rng.randrange(60)))
        b.add(paused, Pause(handle, b.rng.choice(('on holiday', 'enough left'))))
        resumed = paused + dt.timedelta(days=b.rng.randrange(7, 15))
        until = _at(LAST_DAY + dt.timedelta(days=1), 0)
        if b.rng.random() < 0.5 and resumed.date() <= LAST_DAY:
            resumed = b.free(resumed)
            b.add(resumed, Resume(handle, 'back home'))
            until = resumed
        sub.paused.append((paused, until))


def _cast_parcels(b: _Builder) -> None:
    """The cast's parcels, in the volume only (U7): C-01's year orders ship the day after they
    are placed, O-103 and O-108 on 12 October; each is delivered one to three days on.
    O-107 is never paid, O-106 is cancelled and O-104 is a counter sale: none ships. O-105
    stays unshipped too: C-05 gave no address (the app refuses, NoAddress), and a generated
    step never changes the cast."""
    parcels: list[tuple[dt.date, str | OrderId]] = [
        (day + dt.timedelta(days=1), f'year {n}') for n, (day, _) in enumerate(script.YEAR, 1)
    ]
    parcels += [(dt.date(2026, 10, 12), OrderId(o)) for o in ('O-103', 'O-108')]
    for day, order in parcels:
        minute = b.rng.randrange(9 * 60, 16 * 60)
        b.ship(_at(day, minute // 60, minute % 60), order, b.rng.randrange(1, 4))


def _direct_visits(
    b: _Builder,
    anchored: set[tuple[dt.datetime, str]],
    first_visit: int,
    first_event: int,
    *,
    seed: int,
) -> tuple[list[WebVisit], list[WebEvent]]:
    """Step 7, the rest of the web: a direct visit behind each web order no panel visit
    anchors, and the direct visits that buy nothing; no referrer and no variant (V12 holds).

    The ordering customer views 7 minutes before the order, carts at 3 and checks out at 1.
    Beside each such order come one to three browse-only visits (a view, or a view and a cart)
    in the week up to it: on its day or up to _BROWSE_DAYS before, between 08:00 and 20:00 UTC,
    the view at least _BROWSE_BEFORE before the order, so the visit has ended before it and
    never runs into the order's own visit. Each is by a pool consumer who has bought before
    (and so is registered) or by an anonymous visitor (`AV-nnnnn`, no customer), so direct
    traffic converts at about a third; none falls in the teaching window. A customer is one
    visitor, DV-nnnnn. A visitor's events make one visit while no gap is over 30 minutes (the
    30-minute rule, S18); visits and events are numbered in time order.
    """
    rng = Random(f'browse {seed}')
    orders = sorted(o for o in b.web_orders if o not in anchored)
    bought = sorted((b.first[h], h) for hs in b.pool.values() for h in hs)
    firsts = [at for at, _ in bought]
    anonymous: list[tuple[str, str]] = []
    # (visitor key, customer, country) -> its events; a customer's key is the handle
    events: dict[tuple[str, str | None, str], list[tuple[dt.datetime, str]]] = defaultdict(list)
    for at, customer in orders:
        who = (customer, customer, b.country[customer])
        events[who] += [(at - dt.timedelta(minutes=before), kind) for kind, before in _DIRECT_STEPS]
        for _ in range(rng.choice(_BROWSE_PER_ORDER)):
            day = max(FIRST_DAY, at.date() - dt.timedelta(days=rng.randrange(_BROWSE_DAYS + 1)))
            opens = _at(day, _BROWSE_HOURS[0].hour)
            latest = min(_at(day, _BROWSE_HOURS[1].hour), at - _BROWSE_BEFORE)
            if latest < opens:
                raise ValueError(f'no minute for a browse visit before the order at {at}')
            view = opens + dt.timedelta(minutes=rng.randrange((latest - opens) // _MINUTE + 1))
            steps = [(view, 'view')]
            if rng.random() < _BROWSE_CART:
                steps.append((view + dt.timedelta(minutes=rng.randrange(1, 15)), 'cart'))
            if any(QUIET[0] <= m <= QUIET[1] for m, _ in steps):
                continue
            known = bisect.bisect_left(firsts, view)
            if known and rng.random() < _BROWSE_KNOWN:
                handle = bought[rng.randrange(known)][1]
                who = (handle, handle, b.country[handle])
            elif anonymous and rng.random() < _BROWSE_RETURN:
                visitor, country = anonymous[rng.randrange(len(anonymous))]
                who = (visitor, None, country)
            else:
                visitor = f'AV-{len(anonymous) + 1:05d}'
                country = rng.choices(COUNTRIES, [SHARE[c] for c in COUNTRIES])[0]
                anonymous.append((visitor, country))
                who = (visitor, None, country)
            events[who] += steps
    # each visitor's visits by the 30-minute rule, then numbered by their first event
    found: list[tuple[dt.datetime, str, str | None, str, list[tuple[dt.datetime, str]]]] = []
    for (key, customer, country), held in events.items():
        visit: list[tuple[dt.datetime, str]] = []
        for moment, kind in sorted(set(held), key=lambda e: (e[0], _KIND_ORDER[e[1]])):
            if visit and moment - visit[-1][0] > dt.timedelta(minutes=30):
                found.append((visit[0][0], key, customer, country, visit))
                visit = []
            visit.append((moment, kind))
        found.append((visit[0][0], key, customer, country, visit))
    found.sort(key=lambda v: (v[0], v[1]))
    visitors: dict[str, str] = {}
    visits: list[WebVisit] = []
    flat: list[tuple[dt.datetime, int, str, str | None, str, int]] = []
    for n, (start, key, customer, country, held) in enumerate(found):
        if customer is None:
            visitor = key
        else:
            visitor = visitors.setdefault(key, f'DV-{len(visitors) + 1:05d}')
        visit_id = first_visit + n
        visits.append(WebVisit(visit_id, visitor, start.date(), country, None, None))
        flat += [(m, _KIND_ORDER[k], visitor, customer, k, visit_id) for m, k in held]
    flat.sort(key=lambda e: (e[0], e[2], e[1]))
    return visits, [
        WebEvent(f'WE-{first_event + n:06d}', visitor, customer, kind, moment, visit_id)
        for n, (moment, _, visitor, customer, kind, visit_id) in enumerate(flat)
    ]


_DIRECT_STEPS: Final = (('view', 7), ('cart', 3), ('checkout', 1))
"""A direct visit's events, minutes before its order."""
_MINUTE: Final = dt.timedelta(minutes=1)
_FIRST_VIEW: Final = max(
    panel_plan.ORDER_AFTER, *(dt.timedelta(minutes=before) for _, before in _DIRECT_STEPS)
)
"""How long before an order its visit's first event is: a panel visit's or a direct one's."""
_KIND_ORDER: Final = {'view': 0, 'cart': 1, 'checkout': 2}
_BROWSE_PER_ORDER: Final = (1, 2, 2, 3)
"""Browse-only direct visits drawn beside each direct order: two on average, so a third of
the direct visits convert."""
_BROWSE_DAYS: Final = 6
"""A browse visit falls on its order's day or up to this many days before."""
_BROWSE_HOURS: Final = (dt.time(8, 0), dt.time(20, 0))
"""A browse visit's view is at or after the first and before the second, UTC."""
_BROWSE_BEFORE: Final = dt.timedelta(hours=1)
"""A browse visit's view is at least this long before its order: its cart (under 15 minutes
on) ends it well over 30 minutes before the order's own view (7 minutes before it)."""
_BROWSE_CART: Final = 0.4
"""The chance a browse-only visit puts a bag in the cart."""
_BROWSE_KNOWN: Final = 0.55
"""The chance a browse-only visit is a pool consumer's, signed in; else anonymous."""
_BROWSE_RETURN: Final = 0.3
"""The chance an anonymous browse visit is an earlier anonymous visitor's return."""


def _till(rng: Random, receipts: Sequence[TillReceipt]) -> list[TillLine]:
    """One or two lines for each walk-in receipt: loose P-11 by weight, or a pastry.

    Only what holds no bag of the app's stock: `stock_movements` counts whole bags and a loose
    sale is grams from the open bin, so the walk-ins move no stock (U7); the week's loose lines
    move none either. Loose beans cost the bag's list price of the day per kilo, as R-5002's.
    """
    lines = []
    for r in receipts:
        day = r.sold_at.date()
        for n in range(1, rng.choice((1, 1, 2)) + 1):
            if rng.random() < 0.7:
                grams = rng.choice(_LOOSE_GRAMS)
                price = script.list_price(_P11, day)
                amount = (grams * price / 1000).quantize(Decimal('0.01'), ROUND_HALF_UP)
                lines.append(TillLine(r.receipt_id, n, _LOOSE, grams, amount))
            else:
                ean, amount = _NO_PRODUCT
                lines.append(TillLine(r.receipt_id, n, ean, None, amount))
    return lines


def _stock(b: _Builder, subs: Sequence[_Sub]) -> None:
    """Step 9: the bag run, the roasts, the equipment counts, green beans, costs, write-offs."""
    bag_runs = []
    month = FIRST_DAY
    while month <= LAST_DAY:
        at = _at(month.replace(day=3), 6)
        bag_runs.append(at)
        for product in _BEANS:
            n = sum(1 for s in subs if s.product == product and s.owes(at))
            if n:
                b.moves.append((at, product, -n))
        month = _months_after(month, 1)
    for at in bag_runs:
        b.add(at, ShipBags())
    b.moves += _script_moves(b.script)  # the script's places, its roast and O-106's cancel
    for n, day in enumerate(_mondays()):  # write-offs in February, May, August, November
        if day.month in (2, 5, 8, 11) and day.day <= 7:
            product = _BEANS[n % 2]
            at = _at(day, 7, 30)
            qty = b.rng.randrange(1, 4)
            b.add(at, WriteOff(product, Qty(qty)))
            b.moves.append((at, product, -qty))

    points = [_utc(2024, 1, 1, 8, 40)] + [_at(d, 7) for d in _mondays() if d != WEEK[0]]
    points = sorted({*points, OPENING_AT, AFTER_WEEK})
    moves = sorted(b.moves, key=lambda m: m[0])
    times = [m[0] for m in moves]
    level = dict.fromkeys(_STOCKED, 0)
    roasted: dict[tuple[int, int], dict[ProductId, int]] = defaultdict(lambda: defaultdict(int))
    done = 0
    for i, point in enumerate(points):
        upto = bisect.bisect_left(times, point)
        for at, product, qty in moves[done:upto]:
            level[product] += qty
            if level[product] < 0:
                raise Infeasible(f'{at} {product}', f'the balance goes to {level[product]}')
        done = upto
        end = points[i + 1] if i + 1 < len(points) else _at(LAST_DAY + dt.timedelta(days=1), 0)
        need = dict.fromkeys(_STOCKED, 0)
        for _, product, qty in moves[upto : bisect.bisect_left(times, end)]:
            if qty < 0:
                need[product] -= qty
        for product in _STOCKED:
            want = need[product] + (need[product] // 5 + 4 if product in _BEANS else 1)
            if point == OPENING_AT:
                exact = product not in _IN_WINDOW
                count = OPENING[product.value] if exact else max(OPENING[product.value], want)
                b.add(point, Stocktake(product, count))
                level[product] = count
                continue
            if need[product] == 0 or want <= level[product]:
                continue
            if product in _BEANS:
                bags = want - level[product]
                b.add(point, Roast(product, Qty(bags)))
                roasted[point.year, (point.month - 1) // 3][product] += bags
            else:
                b.add(point, Stocktake(product, want))
            level[product] = want
    for at, product, qty in moves[done:]:
        level[product] += qty
        if level[product] < 0:
            raise Infeasible(f'{at} {product}', f'the balance goes to {level[product]}')
    for step in b.script:
        if isinstance(step.action, Roast):
            roasted[step.at.year, (step.at.month - 1) // 3][step.action.product_id] += (
                step.action.bags.value
            )

    weights = {p: Decimal(_weight(p)) / 1000 for p in _BEANS}
    last_quarter = (LAST_DAY.year, (LAST_DAY.month - 1) // 3)
    for (year, quarter), bags in sorted(roasted.items()):
        if (year, quarter) == last_quarter:  # the world ends a month in: buy for the quarter
            before = [roasted[q] for q in sorted(roasted) if q < last_quarter][-4:]
            bags = {p: max(bags[p], sum(x[p] for x in before) // len(before)) for p in _BEANS}
        day = dt.date(year, quarter * 3 + 1, 1)
        at = b.free(_utc(2024, 1, 1, 8, 35) if day == FIRST_DAY else _at(day, 9))
        for product in _BEANS:
            kg = Decimal(math.ceil(bags[product] * weights[product] * Decimal('1.08')))
            if kg <= 0:
                continue
            origin, base = _GREEN[product]
            price = base + Decimal(b.rng.randrange(-600, 601)) / 100
            b.add(at, BuyGreen(origin, kg, Money(price, 'NOK')))
    for year in (2024, 2025, 2026):
        day = dt.date(year, 1, 1)
        at = _utc(2024, 1, 1, 8, 30) if year == 2024 else b.free(_at(day, 9, 5))
        for product, (green, packaging, roasting) in _COSTS.items():
            up = Decimal(year - 2024) * Decimal('1.50')
            b.add(
                at,
                SetCost(
                    product,
                    day,
                    Money(green + up, 'NOK'),
                    Money(packaging, 'NOK'),
                    Money(roasting + up / 2, 'NOK'),
                ),
            )


def _weight(product: ProductId) -> int:
    for step in script.steps():
        if isinstance(step.action, AddProduct) and step.ids['product'][0] == product.value:
            details = step.action.details
            assert isinstance(details, BeanDetails)
            return details.weight_g
    raise ValueError(f'{product} is not a bean of the script')


def _mondays() -> list[dt.date]:
    return [d for d in _days(FIRST_DAY + dt.timedelta(days=7), LAST_DAY) if d.weekday() == 0]


def _jobs(b: _Builder) -> None:
    """Step 10: relays outside the window, a count every night, the October extracts."""
    for day in _days(FIRST_DAY, LAST_DAY):
        for hour, minute in ((6, 0), (12, 0), (18, 0), (23, 30)):
            at = _at(day, hour, minute)
            if (day, hour) == (FIRST_DAY, 6) or at in b.taken or QUIET[0] <= at <= QUIET[1]:
                continue
            b.add(at, Relay())
        count = _at(day, 1)
        if day != FIRST_DAY and count not in b.taken and not QUIET[0] <= count <= QUIET[1]:
            b.add(count, CountAtClose())
        if day.year == 2026 and day.month == 10:
            extract = _at(day, 21)
            if extract not in b.taken:
                b.add(extract, NightlyExtract())
            export = _at(day, 21, 5)
            if export not in b.taken and not QUIET[0] <= export <= QUIET[1]:
                b.add(export, CsvExport())


def build(targets: Targets, *, seed: int) -> Volume:
    """The volume's World: the script's steps and the generated trade around them, sorted.

    Raises Infeasible where `feasibility` does, or where the stock plan or Finland's week
    fails on the steps as drawn.
    """
    fit = _fit(targets)
    report, sale_day = _check(targets, fit)
    b = _Builder(targets, seed, fit)
    accounts = _business(b)
    order_ids = _lessons(b, accounts)
    filler = dict(fit.filler)
    filler[sale_day, _P20] -= 1
    b.fit = replace(fit, filler={k: v for k, v in filler.items() if v})
    _refund(b, sale_day)
    sub_ids, subs = _subscribers(b)
    b.add(_utc(2024, 5, 31, 9, 0), SetSubscriberDiscount(RULE_PERCENT, RULE_DAYS[0]))
    b.add(_utc(2025, 5, 31, 9, 0), SetSubscriberDiscount(None, RULE_DAYS[1]))

    plan = panel_plan.plan(targets.visits, targets.checkout_test, seed=seed)
    anchors: dict[dt.date, list[panel_plan.PanelVisit]] = defaultdict(list)
    for v in plan.visits:
        if v.reached == 4:
            anchors[v.visit_date].append(v)
    placed = _filler(b, anchors, accounts)
    _october_business(b, accounts)
    _october_subscriptions(b, subs)
    _cast_parcels(b)
    b.register_pool()
    _register_business(b)
    _finland_check(b)
    _stock(b, [*_cast_subs(b.script), *subs])
    _jobs(b)

    panel_visits, panel_events = panel_plan.facts(plan, placed)
    first_week_visit = panel_plan.PANEL_SIZE + len(plan.test) + 1
    week_events, week_visits = _week_visits(script.TRACKER, first_week_visit)
    anchored = {(v.order_at, placed[v.visit_id]) for v in plan.visits if v.order_at is not None}
    direct_visits, direct_events = _direct_visits(
        b, anchored, first_week_visit + len(week_visits), len(panel_events) + 1, seed=seed
    )
    walk_ins = series.walk_in_receipts(seed=seed)
    timed = [(s.at, -1, n, s) for n, s in enumerate(b.script)] + b.steps
    timed.sort(key=lambda t: (t[0], t[1], t[2]))
    return Volume(
        steps=tuple(t[3] for t in timed),
        refuse=script.REFUSE,
        refund_ids=(REFUND_ID,),
        fx=series.fx(seed=seed),
        managers=script.MANAGERS,
        tracker=(*week_events, *panel_events, *direct_events),
        till_codes=script.TILL_CODES,
        till_receipts=(*script.TILL_RECEIPTS, *walk_ins),
        till_lines=(*script.TILL_LINES, *_till(b.rng, walk_ins)),
        till_members=script.TILL_MEMBERS,
        web_visits=(*panel_visits, *week_visits, *direct_visits),
        weather=series.weather(),
        door_counts=series.door_counts(),
        till_day_totals=series.till_day_totals(),
        lesson_ids=(*order_ids, *sub_ids),
        key=Key(
            FINLAND_WEEK,
            TEST_DAYS,
            tuple(h for hs in accounts.values() for h in hs),
            report.misfits,
            LOST_PARCEL,
            REFUND,
        ),
    )


def _finland_check(b: _Builder) -> None:
    """Finland's consumer orders as drawn: the week below half the mean of the four around,
    and that mean at least the claim's DRAWN_MEAN (the estimate is held to FINLAND_MEAN)."""
    weeks: dict[dt.date, int] = defaultdict(int)
    for at, _, _, step in b.steps:
        action = step.action
        if not isinstance(action, Place) or action.customer is None:
            continue
        if b.country.get(action.customer) != 'FI' or action.customer.startswith('business'):
            continue
        day = at.date()
        weeks[day - dt.timedelta(days=day.weekday())] += 1
    around = [weeks[FINLAND_WEEK[0] + dt.timedelta(weeks=k)] for k in (-2, -1, 1, 2)]
    mean = sum(around) / 4
    if mean < DRAWN_MEAN or weeks[FINLAND_WEEK[0]] >= mean / 2:
        raise Infeasible(
            f'{FINLAND_WEEK[0]} FI', f'drawn: week {weeks[FINLAND_WEEK[0]]}, around {around}'
        )


def generated(world: World) -> list[Step]:
    """The steps of a world that are not the script's, in order."""
    held: dict[str, int] = defaultdict(int)
    for step in script.steps():
        held[repr(step)] += 1
    found = []
    for step in world.steps:
        key = repr(step)
        if held.get(key, 0) > 0:
            held[key] -= 1
            continue
        found.append(step)
    return found


def cast_ids() -> frozenset[str]:
    """The ids of the cast: customers, orders and subscriptions. A generated step names one only
    to ship or deliver a cast order after the teaching window."""
    return _CAST


def names(action: Action) -> Iterable[str]:
    """Every customer, order or subscription id or handle an action names."""
    for value in vars(action).values():
        if isinstance(value, CustomerId | OrderId | SubscriptionId):
            yield value.value
        elif isinstance(value, str):
            yield value
        elif isinstance(value, PlaceOrder):
            yield value.customer_id.value
