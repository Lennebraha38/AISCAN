"""Pulsar-KKDS client-side DICOM anonymization.

KVKK uyumu için kritik modül: DICOM dosyasındaki tüm kişisel sağlık verisi
tag'leri, veri sunucuya gönderilmeden ÖNCE istemci tarafında temizlenir.
"""
from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass, field

import pydicom
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.tag import Tag
from pydicom.uid import ImplicitVRLittleEndian

# DICOM PS3.15 Table E.1-1 temel alınarak seçilmiş PHI tag'leri.
# (group, element) -> (keyword, aksiyon)
# Aksiyonlar:
#   remove  -> tag tamamen kaldırılır
#   hash    -> değer SHA256(salt + deger) pseudonym ile değiştirilir
PHI_TAGS: dict[Tag, tuple[str, str]] = {
    Tag(0x0008, 0x0050): ("AccessionNumber", "hash"),
    Tag(0x0008, 0x0080): ("InstitutionName", "remove"),
    Tag(0x0008, 0x0081): ("InstitutionAddress", "remove"),
    Tag(0x0008, 0x0090): ("ReferringPhysicianName", "remove"),
    Tag(0x0008, 0x0092): ("ReferringPhysicianAddress", "remove"),
    Tag(0x0008, 0x0094): ("ReferringPhysicianTelephoneNumbers", "remove"),
    Tag(0x0008, 0x1010): ("StationName", "remove"),
    Tag(0x0008, 0x1030): ("StudyDescription", "keep_or_remove"),
    Tag(0x0008, 0x103E): ("SeriesDescription", "keep_or_remove"),
    Tag(0x0008, 0x1040): ("InstitutionalDepartmentName", "remove"),
    Tag(0x0008, 0x1048): ("PhysiciansOfRecord", "remove"),
    Tag(0x0008, 0x1050): ("PerformingPhysicianName", "remove"),
    Tag(0x0008, 0x1060): ("NameOfPhysiciansReadingStudy", "remove"),
    Tag(0x0008, 0x1070): ("OperatorsName", "remove"),
    Tag(0x0010, 0x0010): ("PatientName", "hash"),
    Tag(0x0010, 0x0020): ("PatientID", "hash"),
    Tag(0x0010, 0x0030): ("PatientBirthDate", "remove"),
    Tag(0x0010, 0x0032): ("PatientBirthTime", "remove"),
    Tag(0x0010, 0x0040): ("PatientSex", "remove"),
    Tag(0x0010, 0x1000): ("OtherPatientIDs", "remove"),
    Tag(0x0010, 0x1001): ("OtherPatientNames", "remove"),
    Tag(0x0010, 0x1005): ("PatientBirthName", "remove"),
    Tag(0x0010, 0x1010): ("PatientAge", "remove"),
    Tag(0x0010, 0x1040): ("PatientAddress", "remove"),
    Tag(0x0010, 0x1060): ("PatientMotherBirthName", "remove"),
    Tag(0x0010, 0x2154): ("PhoneNumberHome", "remove"),
    Tag(0x0018, 0x1000): ("DeviceSerialNumber", "remove"),
    Tag(0x0020, 0x0010): ("StudyID", "hash"),
    Tag(0x0020, 0x4000): ("ImageComments", "remove"),
    Tag(0x0040, 0xA123): ("PersonName", "remove"),
}

# Değer taşıdığı anda PHI sayılan genel tag'ler (tümü remove).
VALUE_SCAN_KEYWORDS = {"PersonAddress", "PatientTelecomInformation",
                       "ResponsiblePerson", "ResponsibleOrganization"}


@dataclass
class CleanReport:
    """Temizlenen alanların şeffaflık raporu (UI'da kullanıcıya gösterilir)."""

    removed: list[str] = field(default_factory=list)
    hashed: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    private_removed: int = 0

    def to_dict(self) -> dict:
        return {
            "removed": self.removed,
            "hashed": self.hashed,
            "kept": self.kept,
            "private_tags_removed": self.private_removed,
        }


def _resolve_salt(salt: str | None) -> str:
    """Salt'ı çöz: açık değer yoksa ANON_SALT ortam değişkeni; yoksa hata.

    Kaynak koda gömülü varsayılan salt tahmin edilebilir olduğundan
    (pseudonym yeniden kimliklendirilebilir) zorunlu kılınmıştır.
    """
    resolved = salt if salt else os.getenv("ANON_SALT")
    if not resolved:
        raise ValueError("ANON_SALT (veya açık salt) zorunludur")
    return resolved


def _pseudonym(value: str, salt: str) -> str:
    # 16 karakter: DICOM SH VR uzunluk sinirini (16) asmamak icin.
    return hashlib.sha256((salt + value).encode("utf-8")).hexdigest()[:16]


def _nested_datasets(value: object) -> list[Dataset]:
    """Bir element değerinin içerdiği alt Dataset'leri döndür.

    Sequences (tanımlı veya tanımsız uzunluk/encapsulated olsun) pydicom
    tarafından okunurken ``Sequence`` nesnesine çözümlenir; her item bir
    ``Dataset``'tir. Tek başına ``Dataset`` taşıyan elementler de desteklenir.
    """
    if isinstance(value, Sequence):
        return [item for item in value if isinstance(item, Dataset)]
    if isinstance(value, Dataset):
        return [value]
    return []


def _clean_dataset_recursive(ds: Dataset, salt: str, report: CleanReport) -> None:
    """Bir Dataset'i ve içindeki TÜM iç içe sequence'leri yerinde temizler."""
    # 1) PHI tag haritası (remove / hash / keep_or_remove) bu seviyede uygula.
    for tag, (keyword, action) in PHI_TAGS.items():
        if tag not in ds:
            continue
        raw_value = ds.get(tag)
        has_value = raw_value not in (None, "", b"")
        if action == "remove":
            del ds[tag]
            if has_value:
                report.removed.append(keyword)
        elif action == "hash":
            if has_value:
                ds[tag].value = _pseudonym(str(raw_value), salt)
                report.hashed.append(keyword)
            else:
                del ds[tag]
        elif action == "keep_or_remove":
            # Klinik açıklama içerebilir; varsayılan davranış kaldırmaktır.
            del ds[tag]
            if has_value:
                report.removed.append(keyword)

    # 2) Değer taraması: bilinen keyword'lerde kalan dolu alanları boşalt.
    for elem in list(ds):
        if elem.keyword in VALUE_SCAN_KEYWORDS and elem.value:
            del ds[elem.tag]
            report.removed.append(elem.keyword)

    # 3) İç içe sequence'lere in (private tag'ler 4. adımda tümüyle kaldırılır;
    #    onların altındaki veriyi işlemeye gerek yoktur).
    for elem in list(ds):
        if elem.tag.is_private:
            continue
        for child in _nested_datasets(elem.value):
            _clean_dataset_recursive(child, salt, report)

    # 4) Özel (private) tag'ler üretici tanımlı olabilir -> her seviyede
    #    tamamen kaldır. Private bir sequence ise alt ağacıyla birlikte gider.
    private_elems = [t for t in ds.keys() if t.is_private]
    report.private_removed += len(private_elems)
    for t in private_elems:
        del ds[t]


def clean_dicom_dataset(ds: Dataset, salt: str | None = None) -> tuple[Dataset, CleanReport]:
    """Dataset üzerindeki PHI tag'lerini yerinde ve özyinelemeli temizler.

    Üst seviyeye ek olarak, her derinlikteki iç içe ``Sequence`` item'ları da
    aynı PHI tag haritası ve private-tag kaldırma kurallarıyla temizlenir.
    """
    salt = _resolve_salt(salt)
    report = CleanReport()
    _clean_dataset_recursive(ds, salt, report)
    return ds, report


def clean_dicom_bytes(data: bytes, salt: str | None = None) -> tuple[bytes, dict]:
    """Ham DICOM byte stream'i anonimleştirir.

    Dönüş: (anonim_dicom_bytes, rapor_dict)
    """
    salt = _resolve_salt(salt)
    ds = pydicom.dcmread(io.BytesIO(data), force=True)
    ds, report = clean_dicom_dataset(ds, salt=salt)
    buf = io.BytesIO()
    if not getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", None):
        ds.ensure_file_meta()
        ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    ds.save_as(buf)
    return buf.getvalue(), report.to_dict()


def _scan_dataset_recursive(ds: Dataset, include_pseudonyms: bool, leaked: list[str]) -> None:
    """Bir Dataset'i tarar ve iç içe sequence'lere özyinelemeli olarak iner.

    ``clean_dicom_dataset`` ile AYNI gezinme mantığını kullanır; böylece
    yalnızca üst seviyedeki değil, her derinlikteki PHI de yakalanır.
    """
    for tag, (keyword, action) in PHI_TAGS.items():
        if action == "hash" and not include_pseudonyms:
            continue
        if tag in ds and ds.get(tag) not in (None, "", b""):
            leaked.append(keyword)

    for elem in ds:
        if elem.tag.is_private:
            # Private tag'ler üretici tanımlı olabilir ve PHI içerebilir.
            leaked.append("PrivateTag")
            continue
        if elem.keyword in VALUE_SCAN_KEYWORDS and elem.value:
            leaked.append(elem.keyword)
        for child in _nested_datasets(elem.value):
            _scan_dataset_recursive(child, include_pseudonyms, leaked)


def scan_for_phi(data: bytes, include_pseudonyms: bool = False) -> list[str]:
    """Anonimleştirme sonrası doğrulama (özyinelemeli).

    Varsayılan olarak yalnız 'remove' aksiyonlu tag'lerde kalan değerleri
    raporlar; SHA256 pseudonym'ler (hash aksiyonu) KVKK açısından kabul
    edilebilir olduğundan leak sayılmaz. İç içe sequence'lerdeki PHI ve
    kalan private tag'ler de tespit edilir.
    """
    ds = pydicom.dcmread(io.BytesIO(data), force=True)
    leaked: list[str] = []
    _scan_dataset_recursive(ds, include_pseudonyms, leaked)
    return sorted(set(leaked))
