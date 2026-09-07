"""Gregorian <-> Hijri date conversion.

Direct port of the tabular Islamic calendar algorithm used by
https://github.com/mygulamali/mumineen_calendar_js (source/assets/javascripts/_lib/hijri_date.js),
which is itself the standard 30-year-cycle tabular Hijri calendar (11 leap
years per cycle) driven through the Astronomical Julian Day.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

# Hijri year remainders (year % 30) that are Kabisa (leap) years.
KABISA_YEAR_REMAINDERS = {2, 5, 8, 10, 13, 16, 19, 21, 24, 27, 29}

# Cumulative days elapsed at the *start* of each month (index 0 = Muharram).
DAYS_IN_YEAR = [0, 30, 59, 89, 118, 148, 177, 207, 236, 266, 295, 325]
# Same data, but "cumulative at end of month" indexed 0..10 (Muharram..Zilqadah) -
# matches the shape used by the original JS lookup in from_ajd().
DAYS_IN_YEAR_END = DAYS_IN_YEAR[1:]

# Cumulative days elapsed within a 30-year cycle at the end of each year.
DAYS_IN_30_YEARS = [
    354, 708, 1063, 1417, 1771, 2126, 2480, 2834, 3189, 3543,
    3898, 4252, 4606, 4961, 5315, 5669, 6024, 6378, 6732, 7087,
    7441, 7796, 8150, 8504, 8859, 9213, 9567, 9922, 10276, 10631,
]

MONTH_NAMES = [
    "Moharram al-Haraam",
    "Safar al-Muzaffar",
    "Rabi al-Awwal",
    "Rabi al-Aakhar",
    "Jumada al-Ula",
    "Jumada al-Ukhra",
    "Rajab al-Asab",
    "Shabaan al-Karim",
    "Ramadaan al-Moazzam",
    "Shawwal al-Mukarram",
    "Zilqadah al-Haraam",
    "Zilhaj al-Haraam",
]

MONTH_NAMES_SHORT = [
    "Moharram", "Safar", "Rabi I", "Rabi II", "Jumada I", "Jumada II",
    "Rajab", "Shabaan", "Ramadaan", "Shawwal", "Zilqadah", "Zilhaj",
]


def is_kabisa(year: int) -> bool:
    return (year % 30) in KABISA_YEAR_REMAINDERS


def days_in_month(year: int, month: int) -> int:
    """month is 0-indexed (0 = Moharram)."""
    if month == 11 and is_kabisa(year):
        return 30
    return 30 if month % 2 == 0 else 29


def _is_julian(d: date) -> bool:
    return (d.year, d.month, d.day) < (1582, 10, 5)


def _gregorian_to_ajd(d: date) -> float:
    year, month, day = d.year, d.month, d.day
    if month < 3:
        year -= 1
        month += 12
    if _is_julian(d):
        b = 0
    else:
        a = year // 100
        b = 2 - a + a // 4
    return math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + b - 1524.5


def _ajd_to_gregorian(ajd: float) -> date:
    z = math.floor(ajd + 0.5)
    if z < 2299161:
        a = z
    else:
        alpha = math.floor((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - math.floor(0.25 * alpha)
    b = a + 1524
    c = math.floor((b - 122.1) / 365.25)
    d = math.floor(365.25 * c)
    e = math.floor((b - d) / 30.6001)

    day = b - d - math.floor(30.6001 * e)
    month = (e - 2) if e < 14 else (e - 14)
    year = (c - 4715) if month < 2 else (c - 4716)
    return date(int(year), int(month) + 1, int(day))


@dataclass(frozen=True)
class HijriDate:
    year: int
    month: int  # 0-indexed, 0 = Moharram
    day: int

    @property
    def month_name(self) -> str:
        return MONTH_NAMES[self.month]

    @property
    def month_name_short(self) -> str:
        return MONTH_NAMES_SHORT[self.month]

    def day_of_year(self) -> int:
        return DAYS_IN_YEAR[self.month] + self.day

    @staticmethod
    def from_ajd(ajd: float) -> "HijriDate":
        left = math.floor(ajd - 1948083.5)
        y30 = left // 10631
        left -= y30 * 10631

        i = 0
        while i < len(DAYS_IN_30_YEARS) and left > DAYS_IN_30_YEARS[i]:
            i += 1

        year = round(y30 * 30.0 + i)
        if i > 0:
            left -= DAYS_IN_30_YEARS[i - 1]

        j = 0
        while j < len(DAYS_IN_YEAR_END) and left > DAYS_IN_YEAR_END[j]:
            j += 1

        month = j
        day = (left - DAYS_IN_YEAR_END[j - 1]) if j > 0 else left
        return HijriDate(int(year), int(month), int(round(day)))

    @staticmethod
    def from_gregorian(d: date) -> "HijriDate":
        return HijriDate.from_ajd(_gregorian_to_ajd(d))

    def to_ajd(self) -> float:
        y30 = self.year // 30
        ajd = 1948083.5 + y30 * 10631 + self.day_of_year()
        if self.year % 30 != 0:
            ajd += DAYS_IN_30_YEARS[self.year - y30 * 30 - 1]
        return ajd

    def to_gregorian(self) -> date:
        return _ajd_to_gregorian(self.to_ajd())
