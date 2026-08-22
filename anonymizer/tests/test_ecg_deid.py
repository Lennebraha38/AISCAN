"""ecg_deid modulu testleri."""
import pytest

from ecg_deid import deidentify_hea, scan_hea_leaks

SAMPLE = """JS00001 12 500 5000
JS00001.mat 16+24 1000/mV 16 0 -254 21756 0 I
JS00001.mat 16+24 1000/mV 16 0 264 -599 0 II
#Age: 85
#Sex: Male
#Dx: 164889003,59118001
#Rx: Unknown
#Hx: Hasta Ahmet Yilmaz, TC: 12345678902
"""


def test_record_id_pseudonymized_everywhere():
    r = deidentify_hea(SAMPLE)
    assert "JS00001" not in r.content
    assert r.pseudonym and len(r.pseudonym) == 16
    assert r.content.splitlines()[1].startswith(r.pseudonym + ".mat")


def test_age_banded_sex_removed():
    r = deidentify_hea(SAMPLE)
    assert "#Age: 80-89" in r.content
    assert "#Sex" not in r.content


def test_dx_preserved():
    r = deidentify_hea(SAMPLE)
    assert "#Dx: 164889003,59118001" in r.content


def test_free_text_pii_masked():
    r = deidentify_hea(SAMPLE)
    hx = [l for l in r.content.splitlines() if l.startswith("#Hx")]
    assert hx and "Ahmet" not in hx[0] and "12345678902" not in hx[0]


def test_deterministic_pseudonym():
    a = deidentify_hea(SAMPLE).pseudonym
    b = deidentify_hea(SAMPLE).pseudonym
    assert a == b
    c = deidentify_hea(SAMPLE, salt="baska").pseudonym
    assert a != c


def test_leak_scan_finds_leftover_pii():
    dirty = "#Dx: 426783006\n#Hx: TC 10000000146\n"
    assert scan_hea_leaks(dirty), "PII yakalanmali"
    clean_res = deidentify_hea(SAMPLE)
    assert not scan_hea_leaks(clean_res.content)


def test_technical_lines_intact():
    r = deidentify_hea(SAMPLE)
    assert "12 500 5000" in r.content.splitlines()[0]
