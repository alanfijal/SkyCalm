from collections import Counter
from datetime import date

import pytest

from ml.pireps import Rejected, archive_rows, read_awc, read_iem, unique_reports
from scripts.pirep_census import months


def bulletin(tb="MOD", **fields):
    return {
        "VALID": "202601151131",
        "AIRCRAFT": "A339",
        "FL": "34000",
        "REPORT": f"UA /OV 5418N00318E/TM 1131/FL 340/TP A339/TB {tb}/RM TEST",
        "TURBULENCE": tb,
        "LAT": "54.3",
        "LON": "3.3",
        **fields,
    }


def test_explicit_negatives_ranges_and_exact_flight_levels():
    assert read_iem(bulletin("NEG CHOP")).label == "smooth"
    assert read_iem(bulletin("SMOOTH", TURBULENCE="None", FL="None")).label == "smooth"
    assert read_iem(bulletin("OCNL LGT-MOD")).label == "moderate"
    for text in ("CHOP", "NEG TO MOD", "MOD 250-310", "MOD BLO 340"):
        with pytest.raises(Rejected):
            read_iem(bulletin(text))
    with pytest.raises(Rejected):
        read_iem(bulletin(REPORT="UA /OV 5418N00318E/TM 1131 /FL340", TURBULENCE="None"))


def test_position_audit_and_cruise_jet_boundary():
    with pytest.raises(Rejected, match="position"):
        read_iem(bulletin(REPORT="UA /OV 3929N 073W/TM 1827/FL340", LAT="39.4833", LON="-0.12166"))
    with pytest.raises(Rejected, match="flight_level"):
        read_iem(bulletin(FL="340"))
    for aircraft in ("AT72", "C172", "ZZZZ", "Q400"):
        with pytest.raises(Rejected):
            read_iem(bulletin(AIRCRAFT=aircraft))
    raw = "UA /OV 5418N00318E/TM 1131/FL200/TB MOD"
    assert read_iem(bulletin(REPORT=raw, FL="20000")).cohort == "cruise"
    assert (
        read_iem(bulletin(REPORT=raw.replace("200", "199"), FL="19900", AIRCRAFT="AT72")).cohort
        == "lower"
    )


def test_duplicates_and_conflicting_corrections_are_order_independent():
    moderate = read_iem(bulletin())
    light = read_iem(bulletin("LGT"))
    assert len(unique_reports([moderate, moderate], Counter())) == 1
    for rows in ((light, moderate, moderate), (moderate, moderate, light)):
        assert unique_reports(rows, Counter()) == []


def test_awc_uses_matching_encounter_and_rejects_callsign_as_type():
    example = bulletin()
    row = {
        "obsTime": 1768476660,
        "pirepType": "PIREP",
        "rawOb": example["REPORT"],
        "lat": 54.3,
        "lon": 3.3,
        "fltLvl": 340,
        "acType": "A339",
        "tbInt1": "MOD",
    }
    row["obsTime"] = read_iem(example).time.timestamp()
    assert read_awc(row).key == read_iem(example).key
    with pytest.raises(Rejected):
        read_awc(row | {"pirepType": "AIREP", "rawOb": "", "acType": "BAW3G"})
    with pytest.raises(Rejected):
        read_awc(row | {"tbTop1": 380})


def test_calendar_census_has_bounded_nonoverlapping_months():
    assert months(date(2024, 2, 1), 2) == [
        (date(2024, 2, 1), date(2024, 3, 1)),
        (date(2024, 3, 1), date(2024, 4, 1)),
    ]
    for first, count in ((date(2024, 2, 2), 1), (date(2024, 2, 1), 13), (date(2014, 1, 1), 1)):
        with pytest.raises(ValueError):
            months(first, count)


def test_damaged_quotes_do_not_consume_subsequent_reports_and_midnight_is_excluded(tmp_path):
    path = tmp_path / "2026-01.csv"
    path.write_text(
        "VALID,AIRCRAFT,REPORT,TURBULENCE,FL,LAT,LON\n"
        '202601011100,A320,"unclosed quote,MOD,34000,54,3\n'
        '202601011101,A320,"valid remark, with comma",MOD,34000,54,3\n'
        "202602010000,A320,after month,MOD,34000,54,3\n"
    )
    counts = Counter()
    assert [r["VALID"] for r in archive_rows(path, counts)] == ["202601011101"]
    assert counts == {"malformed_csv": 1, "outside_requested_period": 1}


def test_awc_formatted_airep_needs_a_verified_type_and_consistent_position_and_time():
    from datetime import UTC, datetime

    row = {
        "obsTime": datetime(2026, 11, 26, 9, 37, tzinfo=UTC).timestamp(),
        "pirepType": "AIREP",
        "acType": "SWR3KH",
        "fltLvl": 340,
        "lat": 50.0667,
        "lon": 11.7333,
        "rawOb": "ARP SWR3KH 5004N 01144E 0937 F340 TB CONT MOD CAT IC RM BCS3",
        "tbInt1": "MOD",
    }
    assert read_awc(row).aircraft == "BCS3"
    assert read_awc(row).label == "moderate"
    with pytest.raises(Rejected):
        read_awc(row | {"rawOb": row["rawOb"].replace("BCS3", "UNKNOWN")})
    with pytest.raises(Rejected):
        read_awc(row | {"lon": -11.7333})
