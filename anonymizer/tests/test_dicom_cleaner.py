"""T1.1 birim testleri: DICOM PHI temizliği."""
from __future__ import annotations

import io

import pydicom
import pytest
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from dicom_cleaner import clean_dicom_bytes, scan_for_phi


def _make_dicom() -> bytes:
    """Gerçekçi PHI dolu bir akciğer X-Ray DICOM'u üretir."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.7"
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
    ds.PatientID = "12345678901"
    ds.PatientBirthDate = "19800101"
    ds.PatientSex = "M"
    ds.PatientAddress = "Kadikoy/Istanbul"
    ds.InstitutionName = "Ozel Saglik Hastanesi"
    ds.ReferringPhysicianName = "DEMIR^AYSE"
    ds.AccessionNumber = "ACC-2026-0001"
    ds.StudyID = "ST-991"
    ds.OtherPatientIDs = "TC-12345678901"
    ds.StationName = "RAD-01"
    ds.add_new((0x0009, 0x0001), "LO", "gizli-uretici-verisi")  # private tag
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=False)
    return buf.getvalue()


def test_all_phi_removed():
    raw = _make_dicom()
    out, report = clean_dicom_bytes(raw)
    assert isinstance(out, bytes) and len(out) > 0
    assert "PatientName" in report["hashed"]
    assert "PatientID" in report["hashed"]
    for kw in ("PatientBirthDate", "PatientSex", "InstitutionName",
               "ReferringPhysicianName", "OtherPatientIDs"):
        assert kw in report["removed"], f"{kw} raporlanmadi"


def test_pseudonym_deterministic_and_salts():
    raw = _make_dicom()
    out1, _ = clean_dicom_bytes(raw, salt="salt-a")
    out2, _ = clean_dicom_bytes(raw, salt="salt-a")
    out3, _ = clean_dicom_bytes(raw, salt="salt-b")
    ds1 = pydicom.dcmread(io.BytesIO(out1))
    ds2 = pydicom.dcmread(io.BytesIO(out2))
    ds3 = pydicom.dcmread(io.BytesIO(out3))
    assert ds1.PatientID == ds2.PatientID != "12345678901"
    assert ds1.PatientID != ds3.PatientID
    assert len(ds1.PatientID) == 16


def test_no_phi_leak_after_clean():
    out, _ = clean_dicom_bytes(_make_dicom())
    assert scan_for_phi(out) == []


def test_private_tags_removed():
    out, report = clean_dicom_bytes(_make_dicom())
    ds = pydicom.dcmread(io.BytesIO(out))
    assert not [t for t in ds.keys() if t.is_private]
    assert report["private_tags_removed"] >= 1


def test_minimal_dataset_survives():
    ds = Dataset()
    ds.Modality = "CT"
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta = meta
    buf = io.BytesIO()
    ds.save_as(buf)
    out, report = clean_dicom_bytes(buf.getvalue())
    assert scan_for_phi(out) == []
    assert report["removed"] == []


@pytest.mark.parametrize("keyword", ["PatientName", "PatientID", "AccessionNumber", "StudyID"])
def test_hashed_keywords_listed(keyword):
    _, report = clean_dicom_bytes(_make_dicom())
    assert keyword in report["hashed"]
