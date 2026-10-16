"""T1.2 adversarial testleri: ic ice (recursive) DICOM PHI temizligi.

Bu testler PHI'nin yalnizca ust seviyede degil, her derinlikteki
Sequence item'larinda, private (tek grup) elementlerde ve SR benzeri
yapilarda da temizlendigini dogrular.
"""
from __future__ import annotations

import io
import os

import pydicom
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from dicom_cleaner import clean_dicom_bytes, clean_dicom_dataset, scan_for_phi

os.environ.setdefault("ANON_SALT", "test-anon-salt")

PHI_MARKERS = (
    b"NESTED^PATIENT", b"999-NESTED", b"19700101",
    b"DEEP^PATIENT", b"DEEP-ID", b"SR^SECRET", b"SR-DEEP-ID",
    b"PRIV^PATIENT", b"PRIV-ID", b"UL^PATIENT", b"UL-ID",
    b"REPORT^AUTHOR", b"TEXT-PHI-SECRET",
)


def _sr_dataset(modality: str = "SR") -> FileDataset:
    """SR benzeri minimal bir FileDataset uretir (PHI'siz iskelet)."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.88.33"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = modality
    ds.SeriesInstanceUID = generate_uid()
    ds.StudyInstanceUID = generate_uid()
    return ds


def _to_bytes(ds: Dataset) -> bytes:
    buf = io.BytesIO()
    ds.save_as(buf, enforce_file_format=False)
    return buf.getvalue()


def _assert_no_phi_markers(out: bytes) -> None:
    for marker in PHI_MARKERS:
        assert marker not in out, f"PHI sizdi: {marker!r}"


def test_phi_nested_in_sequence_item_cleaned():
    """Sequence item icindeki PatientName/PatientID/BirthDate temizlenmeli."""
    ds = _sr_dataset()
    item = Dataset()
    item.PatientName = "NESTED^PATIENT"
    item.PatientID = "999-NESTED"
    item.PatientBirthDate = "19700101"
    ds.ReferencedStudySequence = Sequence([item])

    out, report = clean_dicom_bytes(_to_bytes(ds))

    # Kalan-PHI taramasi (pseudonymler kabul edilir) HICBIR sey bulmamali.
    assert scan_for_phi(out) == []
    _assert_no_phi_markers(out)
    assert "PatientName" in report["hashed"]
    assert "PatientID" in report["hashed"]
    assert "PatientBirthDate" in report["removed"]

    cleaned = pydicom.dcmread(io.BytesIO(out))
    nested = cleaned.ReferencedStudySequence[0]
    # hash aksiyonlu tag'ler yerinde kalir ama pseudonym'e donusur.
    assert nested.PatientName != "NESTED^PATIENT" and len(nested.PatientName) == 16
    assert nested.PatientID != "999-NESTED" and len(nested.PatientID) == 16
    # remove aksiyonlu tag tamamen silinir.
    assert "PatientBirthDate" not in nested


def test_phi_two_levels_deep_cleaned():
    """Iki seviye derinlikteki PHI de temizlenmeli."""
    ds = _sr_dataset()
    outer = Dataset()
    inner = Dataset()
    inner.PatientName = "DEEP^PATIENT"
    inner.PatientID = "DEEP-ID"
    inner.PatientSex = "M"
    outer.ReferencedStudySequence = Sequence([inner])
    ds.ReferencedStudySequence = Sequence([outer])

    out, report = clean_dicom_bytes(_to_bytes(ds))

    assert scan_for_phi(out) == []
    _assert_no_phi_markers(out)
    assert "PatientSex" in report["removed"]

    cleaned = pydicom.dcmread(io.BytesIO(out))
    deep = cleaned.ReferencedStudySequence[0].ReferencedStudySequence[0]
    assert deep.PatientName != "DEEP^PATIENT" and len(deep.PatientName) == 16
    assert deep.PatientID != "DEEP-ID" and len(deep.PatientID) == 16
    assert "PatientSex" not in deep


def test_private_sequence_phi_removed():
    """Private (tek grup) bir SQ elementinin icindeki PHI, tag'le birlikte silinir."""
    ds = _sr_dataset()
    private_item = Dataset()
    private_item.PatientName = "PRIV^PATIENT"
    private_item.PatientID = "PRIV-ID"
    ds.add_new((0x0011, 0x0010), "LO", "PRIVATE CREATOR")
    ds.add_new((0x0011, 0x1001), "SQ", Sequence([private_item]))

    out, report = clean_dicom_bytes(_to_bytes(ds))

    assert report["private_tags_removed"] >= 2
    assert scan_for_phi(out) == []
    _assert_no_phi_markers(out)

    cleaned = pydicom.dcmread(io.BytesIO(out))
    assert not [t for t in cleaned.keys() if t.is_private]


def test_private_tag_nested_inside_public_sequence_removed():
    """Public bir Sequence item'i icindeki private tag de her derinlikte silinir."""
    ds = _sr_dataset()
    item = Dataset()
    item.PatientID = "NESTED-PUBLIC-ID"
    item.add_new((0x0009, 0x0001), "LO", "gizli-uretici-verisi")
    ds.ContentSequence = Sequence([item])

    out, report = clean_dicom_bytes(_to_bytes(ds))

    assert report["private_tags_removed"] >= 1
    assert scan_for_phi(out) == []
    assert b"gizli-uretici-verisi" not in out

    cleaned = pydicom.dcmread(io.BytesIO(out))
    nested = cleaned.ContentSequence[0]
    assert not [t for t in nested.keys() if t.is_private]


def test_sr_structured_report_text_phi_cleaned():
    """SR ContentSequence icindeki PersonName ve metin PHI temizlenmeli."""
    ds = _sr_dataset(modality="SR")
    ds.PatientName = "SR^SECRET"
    ds.PatientID = "SR-DEEP-ID"

    content_item = Dataset()
    content_item.PersonName = "REPORT^AUTHOR"          # (0040,A123) -> remove
    content_item.StudyDescription = "TEXT-PHI-SECRET"  # (0008,1030) -> remove
    content_item.SeriesDescription = "TEXT-PHI-SECRET"
    content_item.TextValue = "Nodule 8mm right lower lobe"  # klinik metin korunur
    deep = Dataset()
    deep.PatientName = "SR^DEEP"
    deep.PatientID = "SR-DEEP-ID"
    content_item.ContentSequence = Sequence([deep])
    ds.ContentSequence = Sequence([content_item])

    out, report = clean_dicom_bytes(_to_bytes(ds))

    assert scan_for_phi(out) == []
    _assert_no_phi_markers(out)
    assert "PersonName" in report["removed"]
    assert "StudyDescription" in report["removed"]
    assert "SeriesDescription" in report["removed"]

    cleaned = pydicom.dcmread(io.BytesIO(out))
    item = cleaned.ContentSequence[0]
    assert "PersonName" not in item
    assert "StudyDescription" not in item
    assert "SeriesDescription" not in item
    # Klinik serbest metin korunur (asiri temizlik yok).
    assert "Nodule 8mm right lower lobe" in _to_bytes(cleaned).decode(
        "latin-1", errors="ignore")
    deep_clean = item.ContentSequence[0]
    assert deep_clean.PatientName != "SR^DEEP" and len(deep_clean.PatientName) == 16
    assert deep_clean.PatientID != "SR-DEEP-ID" and len(deep_clean.PatientID) == 16


def test_undefined_length_sequence_traversed():
    """Tanimsiz uzunluklu (undefined-length) Sequence de ozyinelemeli taranmali."""
    ds = _sr_dataset()
    item = Dataset()
    item.PatientName = "UL^PATIENT"
    item.PatientID = "UL-ID"
    item.PatientBirthDate = "19851231"
    ds.add_new((0x0008, 0x1110), "SQ", Sequence([item]))
    ds[0x0008, 0x1110].is_undefined_length = True

    raw = _to_bytes(ds)
    # On kosul: dosya gercekten tanimsiz uzunlukta yazildi.
    assert pydicom.dcmread(io.BytesIO(raw))[0x0008, 0x1110].is_undefined_length

    out, _ = clean_dicom_bytes(raw)

    assert scan_for_phi(out) == []
    _assert_no_phi_markers(out)

    cleaned = pydicom.dcmread(io.BytesIO(out))
    nested = cleaned.ReferencedStudySequence[0]
    assert nested.PatientName != "UL^PATIENT" and len(nested.PatientName) == 16
    assert nested.PatientID != "UL-ID" and len(nested.PatientID) == 16
    assert "PatientBirthDate" not in nested


def test_scan_detects_nested_phi_before_clean():
    """Temizlik ONCESI tarama da ic ice PHI'yi gormeli (ayni gezinme mantigi)."""
    ds = _sr_dataset()
    item = Dataset()
    item.PatientName = "NESTED^PATIENT"
    item.PatientBirthDate = "19700101"
    item.PatientSex = "F"
    ds.ReferencedStudySequence = Sequence([item])

    raw = _to_bytes(ds)
    leaked = scan_for_phi(raw)
    assert "PatientBirthDate" in leaked
    assert "PatientSex" in leaked
    # hash aksiyonlu tag'ler varsayilan taramada leak sayilmaz...
    assert "PatientName" not in leaked
    # ...ama include_pseudonyms ile gorunur.
    assert "PatientName" in scan_for_phi(raw, include_pseudonyms=True)


def test_scan_reports_residual_private_tag():
    """Kalan bir private tag (herhangi bir derinlikte) taramada isaretlenmeli."""
    ds = _sr_dataset()
    ds.add_new((0x0009, 0x0001), "LO", "gizli")
    assert "PrivateTag" in scan_for_phi(_to_bytes(ds))


def test_clinical_tags_and_fake_pixel_array_survive():
    """PHI temizlenirken klinik tag'ler ve sahte pixel dizisi korunmali."""
    ds = _sr_dataset(modality="CR")
    ds.StudyDate = "20260821"
    item = Dataset()
    item.PatientID = "999-NESTED"
    item.Modality = "CR"
    item.PatientName = "NESTED^PATIENT"
    ds.ReferencedStudySequence = Sequence([item])
    pixels = bytes(range(256)) * 4
    ds.Rows = 16
    ds.Columns = 64
    ds.BitsAllocated = 8
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = pixels

    out, _ = clean_dicom_bytes(_to_bytes(ds))

    assert scan_for_phi(out) == []
    cleaned = pydicom.dcmread(io.BytesIO(out))
    assert cleaned.Modality == "CR"
    assert cleaned.StudyDate == "20260821"
    assert cleaned.PixelData == pixels
    nested = cleaned.ReferencedStudySequence[0]
    assert nested.Modality == "CR"       # klinik tag korunur
    assert nested.PatientID != "999-NESTED"   # PHI pseudonymize edilir
    assert nested.PatientName != "NESTED^PATIENT"


def test_clean_dicom_dataset_api_is_backward_compatible():
    """clean_dicom_dataset ayni imza/donus sekliyle calismali (yerinde temizlik)."""
    ds = _sr_dataset()
    item = Dataset()
    item.PatientID = "999-NESTED"
    ds.ReferencedStudySequence = Sequence([item])

    returned_ds, report = clean_dicom_dataset(ds, salt="test-anon-salt")

    assert returned_ds is ds
    assert hasattr(report, "to_dict")
    assert "PatientID" in report.to_dict()["hashed"]
    assert ds.ReferencedStudySequence[0].PatientID != "999-NESTED"
