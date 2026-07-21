from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.api.routes.combined_case_import import (
    _parse_clinical_context,
    _split_sections,
)


class CombinedCaseImportTests(unittest.TestCase):
    def test_split_sections_keeps_each_part_isolated(self) -> None:
        document = """
        HASTA BİLGİLERİ VE KLİNİK BULGULAR
        HASTA ADI SOYADI: ELIF YALCIN
        ANA ŞİKAYET: Sağ üst kadran ağrısı

        KAN TAHLİLLERİ
        WBC 17.8 K/mm3 4.50 - 11.00
        CRP 168 mg/L 0 - 5

        RADYOLOJİ RAPORU
        Ultrasonografide safra kesesi duvar kalınlığı 5 mm ölçüldü.
        """

        sections = _split_sections(document)

        self.assertIn("ELIF YALCIN", sections["clinical"])
        self.assertIn("WBC 17.8", sections["laboratory"])
        self.assertNotIn("WBC 17.8", sections["clinical"])
        self.assertIn("safra kesesi", sections["radiology"])

    def test_missing_section_returns_clear_bad_request(self) -> None:
        document = """
        HASTA BİLGİLERİ VE KLİNİK BULGULAR
        HASTA ADI SOYADI: ELIF YALCIN
        KAN TAHLİLLERİ
        WBC 17.8 K/mm3 4.50 - 11.00
        """

        with self.assertRaises(HTTPException) as raised:
            _split_sections(document)

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("RADYOLOJİ RAPORU", str(raised.exception.detail))

    def test_clinical_labels_fill_structured_context(self) -> None:
        clinical_text = """
        HASTA ADI SOYADI: ELIF YALCIN
        YAŞ: 52
        CİNSİYET: Kadın
        ANA ŞİKAYET: Sağ üst kadran ağrısı
        ŞİKAYET SÜRESİ: 18 saat
        AĞRI ŞİDDETİ: 8
        EŞLİK EDEN BELİRTİLER: Ateş, bulantı ve kusma
        TANSİYON: 105/68 mmHg
        NABIZ: 108 /dk
        ATEŞ: 38.4 C
        SOLUNUM SAYISI: 22 /dk
        SPO2: 96 %
        MUAYENE BULGULARI: Murphy bulgusu pozitif.
        """

        context = _parse_clinical_context(clinical_text)

        self.assertEqual(context.patient_information.full_name, "ELIF YALCIN")
        self.assertEqual(context.patient_information.age, 52)
        self.assertEqual(context.patient_information.sex, "female")
        self.assertEqual(context.presenting_complaint.severity_score, 8)
        self.assertEqual(context.physical_exam.blood_pressure_systolic, 105)
        self.assertEqual(context.physical_exam.blood_pressure_diastolic, 68)
        self.assertEqual(context.physical_exam.pulse_bpm, 108)
        self.assertEqual(float(context.physical_exam.temperature_c), 38.4)
        self.assertIn("Murphy", context.physical_exam.examination_findings or "")


if __name__ == "__main__":
    unittest.main()
