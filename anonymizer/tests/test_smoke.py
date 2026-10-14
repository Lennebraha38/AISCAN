"""End-to-end smoke tests for the anonymizer pillar (DICOM + PII + ECG .hea).

Amaç: üç anonimleştirme modülünün (dicom_cleaner, pii_nlp, ecg_deid) birlikte
yüklendiğini ve temel KVKK garantilerini hızlıca doğrulamak. Detaylı birim
testler ilgili *_test.py dosyalarındadır.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _pkg_dir in ("dicom_cleaner", "pii_nlp", "ecg_deid"):
    sys.path.insert(0, str(_ROOT / _pkg_dir))

import pydicom
import pytest
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from dicom_cleaner import clean_dicom_bytes, scan_for_phi
from pii_nlp import contains_pii, mask
from pii_nlp.patterns import tc_kimlik_gecerli
from ecg_deid import deidentify_hea, scan_hea_leaks


# --------------------------------------------------------------- fixtures ----
def _make_dicom() -> bytes:
    """PHI ile dolu gerçekçi bir CR (X-Ray) DICOM'u üretir."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.1"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "CR"
    ds.StudyDate = "20260821"
    ds.SeriesInstanceUID = generate_uid()
    ds.StudyInstanceUID = generate_uid()
    ds.PatientName = "YILMAZ; AHMET"
    ds.PatientID = "10000000146"
    ds.PatientBirthDate = "19800101"
    ds.PatientSex = "M"
    ds.PatientAddress = "Kadıköy/İstanbul"
    ds.InstitutionName = "Özel Sağlık Hastanesi"
    ds.ReferringPhysicianName = "DEMIR^AYSE"
    ds.AccessionNumber = "ACC-2026-0001"
    ds.StudyID = "ST-991"
    ds.OtherPatientIDs = "TC-10000000146"
    ds.add_new((0x0009, 0x0001), "LO", "gizli-uretici-verisi")  # private tag
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=False)
    return buf.getvalue()


HEA_SAMPLE = """JS00001 12 500 5000
JS00001.mat 16+24 1000/mV 16 0 -254 21756 0 I
JS00001.mat 16+24 1000/mV 16 0 264 -599 0 II
#Age: 85
#Sex: Male
#Dx: 164889003,59118001
#Rx: Unknown
#Hx: Hasta Ahmet Yilmaz, TC: 10000000146
"""


# ----------------------------------------------------------- TC / checksum ----
def test_tc_kimlik_checksum():
    assert tc_kimlik_gecerli("10000000146")
    assert not tc_kimlik_gecerli("10000000147")   # yanlış checksum
    assert not tc_kimlik_gecerli("00000000000")   # baştan 0 olamaz
    assert not tc_kimlik_gecerli("1234567890")    # 10 hane
    assert not tc_kimlik_gecerli("abcdefghijk")   # rakam değil
    print("[OK] test_tc_kimlik_checksum")


# --------------------------------------------------------------- pii_nlp ------
def test_mask_epikriz_core_entities():
    text = ("Hasta T.C. Kimlik No: 10000000146, tel 0532 123 45 67, "
            "e-posta hasta@hastane.com, IBAN TR33 0006 1005 1978 6457 8413 26.")
    out = mask(text).masked_text
    assert "[TC_KIMLIK]" in out and "10000000146" not in out
    assert "[TELEFON]" in out and "0532" not in out
    assert "[EPOSTA]" in out and "hasta@hastane.com" not in out
    assert "[IBAN]" in out
    print("[OK] test_mask_epikriz_core_entities")


def test_mask_names_and_institutions():
    out = mask("Op. Dr. Ayşe Demir, Memorial Şişli Hastanesi'nde.").masked_text
    assert "[KISI_ADI]" in out and "Ayşe Demir" not in out
    assert "[KURUM]" in out
    print("[OK] test_mask_names_and_institutions")


def test_mask_spans_are_consistent():
    r = mask("T.C. 10000000146, tel 0532 123 45 67")
    for f in r.findings:
        assert 0 <= f.start < f.end <= r.original_length
        assert f.label.startswith("[") and f.label.endswith("]")
    print("[OK] test_mask_spans_are_consistent")


def test_clean_text_is_untouched():
    text = "Toraks BT'de sağ akciğer alt lobda 8 mm nodül."
    r = mask(text)
    assert r.masked_text == text and r.findings == []
    assert not contains_pii(text)
    assert contains_pii("T.C. 10000000146")
    print("[OK] test_clean_text_is_untouched")


# ----------------------------------------------------------- dicom_cleaner ---
def test_dicom_all_phi_removed():
    out, report = clean_dicom_bytes(_make_dicom())
    assert isinstance(out, bytes) and len(out) > 0
    # hash'lenen kimlikler
    assert "PatientName" in report["hashed"]
    assert "PatientID" in report["hashed"]
    # kaldırılan alanlar
    for kw in ("PatientBirthDate", "PatientSex", "InstitutionName",
               "ReferringPhysicianName", "OtherPatientIDs", "PatientAddress"):
        assert kw in report["removed"], f"{kw} raporlanmadı"
    assert report["private_tags_removed"] >= 1
    print("[OK] test_dicom_all_phi_removed")


def test_dicom_no_phi_leak_and_pseudonym_deterministic():
    raw = _make_dicom()
    out1, _ = clean_dicom_bytes(raw, salt="salt-a")
    out3, _ = clean_dicom_bytes(raw, salt="salt-b")
    assert scan_for_phi(out1) == []

    ds1 = pydicom.dcmread(io.BytesIO(out1))
    ds3 = pydicom.dcmread(io.BytesIO(out3))
    assert ds1.PatientID != "10000000146"
    assert len(ds1.PatientID) == 16
    assert ds1.PatientID != ds3.PatientID  # farklı salt -> farklı pseudonym
    # private tag kalmadı
    assert not [t for t in ds1.keys() if t.is_private]
    print("[OK] test_dicom_no_phi_leak_and_pseudonym_deterministic")


# --------------------------------------------------------------- ecg_deid ----
def test_hea_record_id_and_age_sex():
    r = deidentify_hea(HEA_SAMPLE)
    assert "JS00001" not in r.content
    assert r.pseudonym and len(r.pseudonym) == 16
    assert r.content.splitlines()[0].startswith(r.pseudonym)
    assert "#Age: 80-89" in r.content
    assert "#Sex" not in r.content
    print("[OK] test_hea_record_id_and_age_sex")


def test_hea_dx_preserved_and_pii_masked():
    r = deidentify_hea(HEA_SAMPLE)
    assert "#Dx: 164889003,59118001" in r.content  # klinik kod korunur
    hx = [ln for ln in r.content.splitlines() if ln.startswith("#Hx")]
    assert hx and "Ahmet" not in hx[0] and "10000000146" not in hx[0]
    assert r.is_clean and not scan_hea_leaks(r.content)
    print("[OK] test_hea_dx_preserved_and_pii_masked")


def test_hea_pseudonym_deterministic_and_salted():
    a = deidentify_hea(HEA_SAMPLE).pseudonym
    b = deidentify_hea(HEA_SAMPLE).pseudonym
    c = deidentify_hea(HEA_SAMPLE, salt="baska-salt").pseudonym
    assert a == b and a != c
    print("[OK] test_hea_pseudonym_deterministic_and_salted")


if __name__ == "__main__":
    test_tc_kimlik_checksum()
    test_mask_epikriz_core_entities()
    test_mask_names_and_institutions()
    test_mask_spans_are_consistent()
    test_clean_text_is_untouched()
    test_dicom_all_phi_removed()
    test_dicom_no_phi_leak_and_pseudonym_deterministic()
    test_hea_record_id_and_age_sex()
    test_hea_dx_preserved_and_pii_masked()
    test_hea_pseudonym_deterministic_and_salted()
    print("\n[OK] All anonymizer smoke tests passed!")
