"""Realistic Turkish lab report fragments (e-Nabız + generic hospital LIS).

Every expected status is derived only from the reference printed on the same
row. ``UNKNOWN`` is expected exclusively where the source itself has no usable
reference (or needs patient context that is not supplied).
"""

from __future__ import annotations

# (case_id, value, unit, printed reference, patient_sex, expected status,
#  expected reference_low, expected reference_high)
CLASSIFY_CASES = [
    # Decimal comma / dot and dash variants
    ("potasyum_virgul", "4,2", "mmol/L", "3,5 - 5,1", None, "NORMAL", 3.5, 5.1),
    ("potasyum_endash", "5,6", "mmol/L", "3.5 – 5.1", None, "HIGH", 3.5, 5.1),
    ("sodyum_parantez", "132", "mmol/L", "(136-145)", None, "LOW", 136, 145),
    ("kreatinin_birimli_ref", "1,2", "mg/dL", "0.5-1.5 mg/dL", None, "NORMAL", 0.5, 1.5),
    ("albumin_ref_etiketi", "3,1", "g/dL", "Ref: 3,5-5,2", None, "LOW", 3.5, 5.2),
    ("tsh_referans_degeri", "6,8", "µIU/mL", "Referans Değeri: 0,27-4,2", None, "HIGH", 0.27, 4.2),
    # One-sided limits
    ("kolesterol_lt", "210", "mg/dL", "< 200", None, "HIGH", None, 200),
    ("crp_lte", "5", "mg/L", "<=5", None, "NORMAL", None, 5),
    ("crp_unicode_lte", "4,9", "mg/L", "≤ 5", None, "NORMAL", None, 5),
    ("hdl_gt", "38", "mg/dL", "> 40", None, "LOW", 40, None),
    ("crp_sansurlu", "<0,5", "mg/L", "0-5", None, "NORMAL", 0, 5),
    # Signed / base excess
    ("baz_acigi", "-1,5", "mmol/L", "-2 / +2", None, "NORMAL", -2, 2),
    ("baz_acigi_dusuk", "-3,4", "mmol/L", "-2 / +2", None, "LOW", -2, 2),
    # Sex-specific references
    ("hgb_kadin", "12,4", "g/dL", "Erkek: 13-17 Kadın: 12-15", "female", "NORMAL", 12, 15),
    ("hgb_erkek", "12,4", "g/dL", "Erkek: 13-17 Kadın: 12-15", "male", "LOW", 13, 17),
    ("hgb_cinsiyet_yok", "12,4", "g/dL", "Erkek: 13-17 Kadın: 12-15", None, "UNKNOWN", None, None),
    ("hdl_kadin_parantez", "45", "mg/dL", "> 40 (kadın > 50)", "female", "LOW", 50, None),
    ("hdl_erkek_parantez", "45", "mg/dL", "> 40 (kadın > 50)", "male", "NORMAL", 40, None),
    ("ferritin_e_k", "18", "ng/mL", "E: 30-400 K: 13-150", "female", "NORMAL", 13, 150),
    # Turkish thousands grouping in count units
    ("lokosit_binlik", "7.500", "/µL", "4.500-11.000", None, "NORMAL", 4500, 11000),
    ("trombosit_binlik", "250.000", "/mm³", "150.000-400.000", None, "NORMAL", 150000, 400000),
    ("trombosit_binlik_dusuk", "98.000", "/mm3", "150.000 - 400.000", None, "LOW", 150000, 400000),
    ("lokosit_karisik_gruplama", "12500", None, "4.500-11.000", None, "HIGH", 4500, 11000),
    ("b12_tr_tam_format", "1.234,5", "pg/mL", "197-771", None, "HIGH", 197, 771),
    ("dansite_ondalik", "1.038", None, "1.003-1.030", None, "HIGH", 1.003, 1.030),
    # Source flags appended to values
    ("glukoz_h_flag", "112 H", "mg/dL", "70-100", None, "HIGH", 70, 100),
    ("ferritin_l_flag", "8 L", "ng/mL", "13-150", None, "LOW", 13, 150),
    ("potasyum_yildiz", "5,9*", "mmol/L", "3,5-5,1", None, "HIGH", 3.5, 5.1),
    ("alt_ok", "68 ↑", "U/L", "0-41", None, "HIGH", 0, 41),
    # Unit aliases with factor 1 only
    ("wbc_10uzeri3", "7,5", "10^3/µL", "4,5-11 x10³/µL", None, "NORMAL", 4.5, 11),
    ("wbc_k_ul", "13,1", "K/uL", "4.5-11 10^3/uL", None, "HIGH", 4.5, 11),
    ("plt_10_9_l", "250", "10^9/L", "150-400 10³/µL", None, "NORMAL", 150, 400),
    ("sedim_saat", "28", "mm/saat", "0-20 mm/h", None, "HIGH", 0, 20),
    ("tsh_uiu_miu", "2,1", "µIU/mL", "0,27-4,2 mIU/L", None, "NORMAL", 0.27, 4.2),
    ("yuzde", "62", "%", "40-75 %", None, "NORMAL", 40, 75),
    # Qualitative e-Nabız rows
    ("bakteri_negatif", "Negatif", None, "Negatif", None, "NORMAL", None, None),
    # Truly unusable in the source: must stay UNKNOWN (never invented)
    ("ref_yok", "1,585", None, "", None, "UNKNOWN", None, None),
    ("ref_tire", "14", "U/L", "---", None, "UNKNOWN", None, None),
    ("ters_yon_belirsiz", "55", "mg/dL", "40 >", None, "UNKNOWN", None, None),
    ("birim_farkli_miu", "2,1", "mIU/mL", "0,27-4,2 µIU/mL", None, "UNKNOWN", 0.27, 4.2),
    ("pozitif_negatif_ref", "Pozitif", None, "Negatif", None, "UNKNOWN", None, None),
    ("yas_etiketi", "3", "mg/dL", "Yetişkin: 2-5 veya 8-10", None, "UNKNOWN", None, None),
]

# Generic hospital LIS text (one row per line, previous results in between).
HOSPITAL_TEXT = """\
TETKIK ADI SONUC BIRIM ONCEKI SONUC REFERANS ARALIGI
FT4 (Serbest Tiroksin) 1,2 ng/dL 0,89-1,76
TSH 2,1 µIU/mL (0,27 - 4,2)
Lökosit 7500 /µL 4500-11000
Trombosit 250.000 /mm³ 150.000-400.000
Hemoglobin 12,4 g/dL Erkek: 13-17 Kadın: 12-15
HDL Kolesterol 45 mg/dL > 40 (Kadın > 50)
Glukoz 112 H mg/dL 70-100
CRP <0,5 mg/L < 5
Sedimantasyon Hızı 28 mm/saat 0-20
Kreatinin 0,9 mg/dL 0.5-1.5 mg/dL
Total Kolesterol 210 mg/dL < 200
ALT 31 U/L 28 (12.03.2025) 0-41
Folik Asit 2,9 ng/mL 3,1-20,5
Total Bilirubin 1,4 mg/dL 0,3-1,2
Vitamin B12 1.234,5 pg/mL 197-771
"""

# parameter -> (expected normalized value, unit, reference text, low, high,
#              expected status for a FEMALE patient)
HOSPITAL_EXPECTED = {
    "FT4": (1.2, "ng/dL", "0.89-1.76", 0.89, 1.76, "NORMAL"),
    "TSH": (2.1, "uIU/mL", "(0.27 - 4.2)", 0.27, 4.2, "NORMAL"),
    "Lökosit": (7500.0, "/uL", "4500-11000", 4500, 11000, "NORMAL"),
    "Trombosit": (250000.0, "/mm3", "150.000-400.000", 150000, 400000, "NORMAL"),
    "Hemoglobin": (12.4, "g/dL", "Erkek: 13-17 Kadin: 12-15", None, None, "NORMAL"),
    "HDL": (45.0, "mg/dL", "> 40 (Kadin > 50)", None, None, "LOW"),
    "Glukoz": (112.0, "mg/dL", "70-100", 70, 100, "HIGH"),
    "CRP": (None, "mg/L", "< 5", None, 5, "NORMAL"),
    "SEDIMENTASYON": (28.0, "mm/saat", "0-20", 0, 20, "HIGH"),
    "Kreatinin": (0.9, "mg/dL", "0.5-1.5", 0.5, 1.5, "NORMAL"),
    "Total Kolesterol": (210.0, "mg/dL", "< 200", None, 200, "HIGH"),
    "ALT": (31.0, "U/L", "0-41", 0, 41, "NORMAL"),
    "FOLIK_ASIT": (2.9, "ng/mL", "3.1-20.5", 3.1, 20.5, "LOW"),
    "Total Bilirubin": (1.4, "mg/dL", "0.3-1.2", 0.3, 1.2, "HIGH"),
    "Vitamin B12": (1234.5, "pg/mL", "197-771", 197, 771, "HIGH"),
}

# e-Nabız native table (PyMuPDF find_tables output shape), including references
# wrapped onto continuation rows in the reference column and the first column.
ENABIZ_TABLE = [
    ["Tarih", "Tahlil", "Sonuç", "Sonuç\nBirimi", "Referans\nDeğeri"],
    ["17.12.2025\n08:41", "Tam Kan Sayımı (hemogram)", None, None, None],
    ["", "WBC", "7,5", "10^3/µL", "4,5 - 11"],
    ["", "PLT", "250.000", "/mm³", "150.000 -\n400.000"],
    ["", "Hemoglobin", "12.4", "g/dL", "Erkek: 13 - 17"],
    ["", None, None, None, "Kadın: 12 - 15"],
    ["", "Kreatinin", "0,9", "mg/dL", "0,5 -"],
    ["", None, None, None, "1,2"],
    ["", "Glukoz", "112 H", "mg/dL", "70 - 100"],
    ["", "Sodyum", "132", "mmol/L", "(136-145)"],
    ["", "Baz açığı", "-1,5", "mmol/L", "-2 / +2"],
    ["", "Bakteri", "Negatif", "---", "Negatif"],
    ["", "Nötrofil Lenfosit Oranı", "1,585", "---", ""],
    ["", "Dansite", "1.038", "---", ""],
    ["1,003 - 1,030", None, None, None, None],
]

# parameter -> (reference text after wrapping, expected status for FEMALE)
ENABIZ_EXPECTED = {
    "WBC": ("4,5 - 11", "NORMAL"),
    "PLT": ("150.000 - 400.000", "NORMAL"),
    "Hemoglobin": ("Erkek: 13 - 17 Kadın: 12 - 15", "NORMAL"),
    "Kreatinin": ("0,5 - 1,2", "NORMAL"),
    "Glukoz": ("70 - 100", "HIGH"),
    "Sodyum": ("(136-145)", "LOW"),
    "Baz açığı": ("-2 / +2", "NORMAL"),
    "Bakteri": ("Negatif", "NORMAL"),
    # The source prints no reference here: UNKNOWN is the honest answer.
    "Nötrofil Lenfosit Oranı": (None, "UNKNOWN"),
    "Dansite": ("1,003 - 1,030", "HIGH"),
}
