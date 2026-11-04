# 0014. Settings

Status: accepted, 2026-11-04 (step 6.2, decision C15)

## Context

The app needs a few values that differ by place: where the database is, where the payment provider is and its key, how long a price is cached, the shop's time zone, how many rows the relay sends at once.

Read badly, settings spread: `os.environ` read in many modules, a missing value found at the first request that needs it, a typo silently ignored, a key printed in a log. The `configuration` page shows the other way: read once, at the edge, parsed by type, every problem at once.

The DevOps route (phase 8) deploys the app to three environments, and sets these values from Helm values and a vault. The names must be the app's own and stable.

The teaching app today, `firm`, has `Settings.from_env(mapping)` with a `FIRM_` prefix, a parser per field type, one `SettingsError` and its URLs out of the repr. Its parser for `str` is `url`, which fits no key or zone name.

## Decision

### The six settings

Every name starts with `ROASTERY_`. A field's name in capitals, after the prefix, is its variable: `price_ttl` is `ROASTERY_PRICE_TTL`.

| variable | field type | default | parsed as |
|---|---|---|---|
| `ROASTERY_DATABASE_URL` | `Url` | required | a URL with a scheme; hidden from the repr |
| `ROASTERY_PROVIDER_URL` | `Url` | required | a URL with a scheme; hidden from the repr |
| `ROASTERY_PROVIDER_KEY` | `Secret` | required | any text that is not empty; hidden from the repr |
| `ROASTERY_PRICE_TTL` | `int` | `300` | seconds, a whole number of 0 or more |
| `ROASTERY_SHOP_ZONE` | `ZoneInfo` | `Europe/Oslo` | a zone name `zoneinfo` knows |
| `ROASTERY_RELAY_BATCH` | `Positive` | `5` | a whole number of 1 or more |

`ROASTERY_SHOP_ZONE` gives the local date of a counter sale (ADR 0008). `ROASTERY_RELAY_BATCH` is the relay's batch size (ADR 0009); 5 is the plan's default.

### The dataclass

```python
Url = NewType('Url', str)
"""A URL with a scheme; it may hold a password."""

Secret = NewType('Secret', str)
"""A key or a password: never shown."""

Positive = NewType('Positive', int)
"""A whole number of 1 or more."""


def oslo() -> ZoneInfo:
    """The shop's zone when none is set: Bergen keeps Oslo's."""
    return ZoneInfo('Europe/Oslo')


@dataclass(frozen=True)
class Settings:
    """The shop's settings; a field with a default is optional.

    The URLs and the key are left out of repr and str.
    """

    database_url: Url = field(repr=False)
    provider_url: Url = field(repr=False)
    provider_key: Secret = field(repr=False)
    price_ttl: int = 300
    shop_zone: ZoneInfo = field(default_factory=oslo)
    relay_batch: Positive = Positive(5)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> Self:
        """The settings in `env`, each parsed by its field's type.

        Raises SettingsError naming every problem: the fields'
        in their order, then the ROASTERY_ names no field reads.
        """
        ...
```

Each field is parsed by its type, through one table:

```python
PARSERS: Final[Mapping[object, Callable[[str], object]]] = (
    MappingProxyType(
        {
            Url: url,
            Secret: secret,
            int: whole,
            Positive: positive,
            ZoneInfo: zone,
        }
    )
)
"""How a setting's text is parsed, by the type of its field."""
```

A field type the table lacks is a bug, and raises `KeyError`.

### One error, every problem

```python
class SettingsError(ValueError):
    """Settings missing or malformed: all of them, at once."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__('; '.join(problems))
        self.problems = tuple(problems)
```

`from_env` collects every problem before it raises:

- a required variable that is missing;
- a value its parser refuses;
- a `ROASTERY_` name that no field reads (most are typos), sorted.

A message never shows the value of a `Url` or a `Secret`: it names the variable and what was wrong. A deploy fails once, with the whole list.

### Read once, at the edge

`from_env` takes the environment as an argument. Nothing in `roastery` reads `os.environ`, except the script entry in `bootstrap`, which passes it to `main` (ADR 0013). A test passes a dict. `wire` gets the `Settings` object, never the mapping.

### VAT is never a setting

VAT rates are dated rows by country and kind in the app database (ADR 0010). A setting is one value for the whole run; a rate changes on a date and differs by country. Phase 8's change is code and data, not "a config change". There is no `ROASTERY_VAT*` variable, and one in the environment is reported as not a setting.

Open question (for phase 8): C15 says these are "the same names as the DevOps settings table". The map's shared case (`map-patterns-devops.md` §3) names `DB_NAME`, `DB_PASSWORD`, `PROVIDER_URL` and `PROVIDER_API_KEY`. The app reads `ROASTERY_DATABASE_URL` (the name and the password are parts of it) and `ROASTERY_PROVIDER_KEY`. Phase 8's Helm values and vault entries must set the app's names, or the DevOps table must be re-said in them.

## Alternatives refused

| alternative | why not |
|---|---|
| `os.environ` read where a value is needed | A missing value surfaces at the first request that needs it, in production. A test must patch the environment. The `configuration` page's twin is exactly this. |
| Pydantic `BaseSettings` | A dependency (ADR 0002), and the parsing the page shows would sit inside the library. |
| `str` parsed as a URL, as in firm | The key and the zone are `str` too, and are not URLs. A type per kind of text keeps "parsed by type" true. |
| Raise at the first problem | A deploy with three mistakes fails three times. One error with every problem is one fix. |
| A settings file (TOML) in the repo | Settings differ by environment and the key is a secret; neither belongs in the repo. Helm and the vault set variables. |
| VAT rates as settings | A rate per country per date is a table, not a value. A setting would hide which rate an old order had (ADR 0010). |
| `PRICE_TTL` as a `timedelta` text (`5m`) | A parser for a small language. Seconds as a whole number is enough, and the name says the unit in the docs. |

## Consequences

- One place lists every setting; a new one is a field and a parser, nothing else.
- The repr of `Settings` is safe to log.
- `ROASTERY_SHOP_ZONE` needs `zoneinfo` to know the zone. On Windows that needs `tzdata` (ADR 0002's open question).
- The simulator and the tests build `Settings` directly, or pass a dict to `from_env`. Values for the provider that the fake does not use are read and checked, not used, as in firm.

## Pages served

| page | what it shows |
|---|---|
| `configuration` | `Settings.from_env` on a dict; a missing key and a typo in one `SettingsError`; `ROASTERY_PROVIDER_KEY` kept out of the repr; VAT as a table, not a setting |
| `ports-and-adapters` | `Settings` handed to `wire` (ADR 0013) |
| `cache-aside` | `ROASTERY_PRICE_TTL` as the cache's TTL |
| `outbox` | `ROASTERY_RELAY_BATCH` as the batch size |
