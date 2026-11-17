r"""The single project map shared by all games.

Laid out as a 5x3 grid (north to south, west to east); every grid neighbour is adjacent and
three diagonals are added:

    skali ------- dunavia ---- zhitno-pole --- madara -------- kaliakra
      |       \      |              |             |      \         |
    sredets ---- balkania ------ leventa ----- pelikania --- zlaten-grozd
      |              |              |      \      |                |
    pirina ------- ezera ----- rozova-dolina -- chuden-krai ---- tsarevo
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TerritoryDefinition:
    slug: str
    name: str


@dataclass(frozen=True)
class MapDefinition:
    territories: tuple[TerritoryDefinition, ...]
    edges: tuple[tuple[str, str], ...]


PROJECT_MAP = MapDefinition(
    territories=(
        TerritoryDefinition("skali", "Скали"),
        TerritoryDefinition("dunavia", "Дунавия"),
        TerritoryDefinition("zhitno-pole", "Житно поле"),
        TerritoryDefinition("madara", "Мадара"),
        TerritoryDefinition("kaliakra", "Калиакра"),
        TerritoryDefinition("sredets", "Средец"),
        TerritoryDefinition("balkania", "Балкания"),
        TerritoryDefinition("leventa", "Левента"),
        TerritoryDefinition("pelikania", "Пеликания"),
        TerritoryDefinition("zlaten-grozd", "Златен грозд"),
        TerritoryDefinition("pirina", "Пирина"),
        TerritoryDefinition("ezera", "Езера"),
        TerritoryDefinition("rozova-dolina", "Розова долина"),
        TerritoryDefinition("chuden-krai", "Чуден край"),
        TerritoryDefinition("tsarevo", "Царево"),
    ),
    edges=(
        ("skali", "dunavia"),
        ("dunavia", "zhitno-pole"),
        ("zhitno-pole", "madara"),
        ("madara", "kaliakra"),
        ("sredets", "balkania"),
        ("balkania", "leventa"),
        ("leventa", "pelikania"),
        ("pelikania", "zlaten-grozd"),
        ("pirina", "ezera"),
        ("ezera", "rozova-dolina"),
        ("rozova-dolina", "chuden-krai"),
        ("chuden-krai", "tsarevo"),
        ("skali", "sredets"),
        ("sredets", "pirina"),
        ("dunavia", "balkania"),
        ("balkania", "ezera"),
        ("zhitno-pole", "leventa"),
        ("leventa", "rozova-dolina"),
        ("madara", "pelikania"),
        ("pelikania", "chuden-krai"),
        ("kaliakra", "zlaten-grozd"),
        ("zlaten-grozd", "tsarevo"),
        ("skali", "balkania"),
        ("madara", "zlaten-grozd"),
        ("leventa", "chuden-krai"),
    ),
)
