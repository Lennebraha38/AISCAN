"""T1.2 birim testleri: Türkçe PII maskeleme (20+ gerçekçi epikriz vakası)."""
from __future__ import annotations

import pytest

from pii_nlp import contains_pii, mask
from pii_nlp.patterns import tc_kimlik_gecerli


def _masked(text: str, **kw):
    return mask(text, **kw).masked_text


# --- TC Kimlik checksum algoritması ---
def test_tc_checksum_gecerli():
    assert tc_kimlik_gecerli("10000000146")


def test_tc_checksum_gecersiz():
    assert not tc_kimlik_gecerli("10000000147")
    assert not tc_kimlik_gecerli("00000000000")


# --- Bireysel desenler ---
def test_tc_maskelenir():
    out = _masked("Hastanın T.C. Kimlik No: 10000000146'dır.")
    assert "10000000146" not in out and "[TC_KIMLIK]" in out


def test_tc_ciplak_11_hane():
    out = _masked("Kimlik 10000000146 olarak doğrulandı.")
    assert "[TC_KIMLIK]" in out


def test_telefon_5xx():
    out = _masked("İletişim: 0532 123 45 67 arayınız.")
    assert "0532" not in out or "[TELEFON]" in out
    assert "[TELEFON]" in out


def test_telefon_uluslarasi():
    out = _masked("+90 532 123 45 67 numarasından ulaşın.")
    assert "[TELEFON]" in out


def test_eposta():
    out = _masked("Rapor ahmet.yilmaz@ornek.com.tr adresine gönderildi.")
    assert "[EPOSTA]" in out and "yilmaz@" not in out


def test_pasaport():
    out = _masked("Pasaport no U+A1234567 kontrol edildi.")
    assert "[PASAPORT]" in out


def test_iban():
    out = _masked("Ödeme TR33 0006 1005 1978 6457 8413 26 hesabına.")
    assert "[IBAN]" in out


def test_plaka():
    out = _masked("Ambulans 34 ABC 123 plakalı araçla geldi.")
    assert "[PLAKA]" in out


def test_dob_baglam():
    out = _masked("Doğum tarihi 01.01.1980 olan hasta...")
    assert "[TARIH]" in out


def test_dob_kisa():
    out = _masked("D.T.: 01/01/1980")
    assert "[TARIH]" in out


def test_genel_tarih_varsayilan_maskelenmez():
    out = _masked("12.08.2026 tarihinde çekilen grafide...")
    assert "12.08.2026" in out


def test_genel_tarih_opsiyonel():
    out = _masked("12.08.2026 tarihinde çekilen grafide...", mask_dates=True)
    assert "12.08.2026" not in out and "[TARIH]" in out


def test_unvanli_hekim_adi():
    out = _masked("İnceleyen: Op. Dr. Ayşe Demir")
    assert "[KISI_ADI]" in out and "Ayşe Demir" not in out


def test_prof_dr():
    out = _masked("Prof. Dr. Mehmet Kaya tarafından raporlandı.")
    assert "[KISI_ADI]" in out


def test_buyuk_harf_ad_soyad():
    out = _masked("Hasta AHMET YILMAZ taburcu edildi.")
    assert "[KISI_ADI]" in out and "YILMAZ" not in out


def test_kurum():
    out = _masked("Memorial Şişli Hastanesi'nde takip edilmektedir.")
    assert "[KURUM]" in out


def test_universite_hastanesi():
    out = _masked("Hacettepe Üniversitesi Tıp Fakültesi Hastanesi kayıtları.")
    assert "[KURUM]" in out


def test_adres():
    out = _masked("İkamet: Bağdat Caddesi No:112 Kat 3 Kadıköy")
    assert "[ADRES]" in out


def test_span_bilgisi_tutarlari():
    r = mask("T.C. 10000000146, tel 0532 123 45 67")
    for f in r.findings:
        assert f.start < f.end <= r.original_length
        assert f.label.startswith("[")


def test_maskeleme_metni_korur():
    text = "Akciğer grafisinde sağ bazalde konsolidasyon. T.C. Kimlik No 10000000146."
    r = mask(text)
    assert "konsolidasyon" in r.masked_text
    assert "[TC_KIMLIK]" in r.masked_text


# --- Gerçekçi epikriz vakaları (recall) ---
EPIKRIZLER = [
    ("Hasta Ahmet Yılmaz, 0532 111 22 33 numaralı telefondan başvurdu.", ["TELEFON"]),
    ("T.C. Kimlik No 10000000146 olan hastada göğüs ağrısı.", ["TC_KIMLIK"]),
    ("İletişim e-posta: deneme.hasta@hastane.gov.tr", ["EPOSTA"]),
    ("Op. Dr. Zeynep Ak tarafından muayene edildi.", ["KISI_ADI"]),
    ("Ankara Atatürk Sanatoryum Eğitim ve Araştırma Hastanesi'ne sevk.", ["KURUM"]),
    ("Adres: Cumhuriyet Mahallesi Atatürk Caddesi No 15", ["ADRES"]),
    ("Araç plakası 06 BKM 412 kayıtlara geçti.", ["PLAKA"]),
    ("Doğum tarihi 15.03.1972, emekli öğretmen.", ["TARIH"]),
    ("AHMET YILMAZ isimli hasta acile başvurdu.", ["KISI_ADI"]),
    ("Dr. Kerem Soylu operasyona girdi.", ["KISI_ADI"]),
]


@pytest.mark.parametrize("text,expected_types", EPIKRIZLER)
def test_epikriz_recall(text, expected_types):
    r = mask(text)
    found = {f.type for f in r.findings}
    for t in expected_types:
        assert t in found, f"{t} bulunamadı -> {r.masked_text}"


def test_contains_pii_helper():
    assert contains_pii("T.C. 10000000146 hastası")
    assert not contains_pii("Bilateral akciğer alanları doğaldır.")


def test_temiz_metin_degismez():
    text = "Toraks BT'de sağ akciğer alt lobda 8 mm boyutlu nodül saptandı."
    r = mask(text)
    assert r.masked_text == text and r.findings == []
