"""Single registry of consistency thresholds, vocabularies and Turkish messages."""
DIFF_SUM_TOLERANCE = 5.0
ABS_PCT_TOLERANCE = 0.10
PROTEIN_TOLERANCE = 0.3
MAGNITUDE_FACTOR = 10.0
REFERENCE_DIVERGENCE_FACTOR = 5.0
CONSISTENCY_HEADING = "VERİ TUTARLILIK UYARILARI"
NO_INCONSISTENCY = "Tespit edilen veri tutarsızlığı yok."
DATE_FIELDS = ("event_date", "specimen_date", "measured_at", "result_date", "document_date", "report_date")
MESSAGES_TR = {
    "missing_parameter_name": "Parametre adı okunamadı.", "missing_observed_value": "Basılı sonuç değeri okunamadı.",
    "missing_unit": "Birim bulunamadı.", "low_input_confidence": "Satırın okunma güveni düşük; kaynakla karşılaştırılmalı.",
    "invalid_input_confidence": "Okunma güveni geçersiz.", "numeric_value_conflict": "Ham değer ile sayısal okuma uyuşmuyor.",
    "invalid_numeric_value": "Sayısal değer geçersiz.", "reference_unit_mismatch": "Sonuç ve basılı referans birimleri uyuşmuyor.",
    "unrecognized_source_status": "Kaynak durum işareti tanınamadı.", "invalid_reference_bounds": "Basılı referans sınırları geçersiz.",
    "conflicting_or_repeated_observation": "Aynı parametre için birden çok farklı gözlem var.",
    "visible_row_count_unverified": "Kaynak tablodaki toplam satır sayısı doğrulanamadı.",
    "visible_row_count_mismatch": "Görünen satır sayısı ile çıkarılan satır sayısı uyuşmuyor.",
    "no_lab_rows_on_page_review": "Sayfada laboratuvar satırı okunamadı.", "page_extraction_failed": "Sayfa okuması tamamlanamadı.",
    "image_completeness_audit_failed": "Görüntü tamamlık kontrolü tamamlanamadı.",
    "extraction_invalid_cells_review": "Okumada geçersiz hücreler var; kaynak satırlar kontrol edilmeli.",
    "low_resolution": "Sayfa çözünürlüğü düşük.", "blurred_image": "Sayfa görüntüsü bulanık.", "low_contrast": "Sayfa kontrastı düşük.",
    "claude_extraction_failed": "Claude okuyucusu tamamlanamadı.",
    "claude_lab_document_extraction": "Sayfa Claude okuyucusuyla okundu.", "openai_lab_document_extraction": "Sayfa OpenAI okuyucusuyla okundu.",
    "source_flag_status_conflict": "Basılı yüksek/düşük işareti ile kanonik durum çelişiyor.",
    "differential_sum_mismatch": "Beş lökosit yüzdesinin toplamı beklenen 100 sınırının dışında.",
    "absolute_percent_mismatch": "Mutlak hücre sayısı ile yüzde × WBC / 100 hesabı uyuşmuyor.",
    "protein_sum_mismatch": "Total protein ile albümin + globülin toplamı uyuşmuyor.",
    "value_outside_reference_no_flag": "Değer basılı referans dışında, ancak kaynak durum işareti yok.",
    "flag_without_reference_breach": "Değer basılı referans içinde, ancak yüksek/düşük işareti var.",
    "magnitude_suspect": "Değer referansa göre büyüklük açısından şüpheli; ondalık, virgül veya birim kontrol edilmeli.",
    "printed_reference_divergence": "Basılı referans ile aynı yaş/cinsiyet için veritabanı referansı belirgin farklı.",
    "consistency_unit_unresolved": "Birim güvenle normalize edilemedi; ilgili sayısal kural atlandı.",
    "report_findings_impression_conflict": "Bulgular ve sonuç bölümlerinde aynı kavram için karşıt ifadeler var.",
    "report_laterality_conflict": "Bulgular ve sonuç bölümlerinde aynı organın tarafı farklı.",
    "report_patient_sex_mismatch": "Rapordaki cinsiyete özgü organ terimi ile kayıtlı cinsiyet uyuşmuyor.",
    "report_date_in_future": "Rapor tarihi gelecekte.", "report_date_order_conflict": "Rapordaki tarih alanlarının sırası tutarsız.",
    "cross_read_unavailable": "Bağımsız okuyuculardan biri tamamlanamadı; tek okuma kullanıldı.",
    "cross_read_agreed": "İki bağımsız okuma değer, birim ve referansta aynı; bu, doğruluk garantisi değildir.",
    "cross_read_value_conflict": "İki bağımsız okuyucu farklı değer okudu; her iki okuma saklandı.",
    "cross_read_unit_or_reference_conflict": "İki okuyucunun birim veya referans okuması farklı.",
    "cross_read_single_reader_only": "Satır yalnızca bir okuyucuda bulundu; diğer okuyucunun görmemesi yokluk kanıtı değildir.",
}
HIGH_SEVERITY = frozenset({"magnitude_suspect", "report_patient_sex_mismatch"})
INFO_CODES = frozenset({"cross_read_agreed", "claude_lab_document_extraction", "openai_lab_document_extraction"})
EPSILON = 1e-9
SOURCE_DIRECTIONS = {"h": "HIGH", "high": "HIGH", "yuksek": "HIGH", "↑": "HIGH", "l": "LOW", "low": "LOW", "dusuk": "LOW", "↓": "LOW"}
DIFFERENTIAL_NAMES = ("Nötrofil", "Lenfosit", "Monosit", "Eozinofil", "Bazofil")
PROTEIN_NAMES = ("Total Protein", "Albümin", "Globülin")
CONSISTENCY_CURATED_ALIASES = {"Total Protein": ("Total protein", "Protein total", "Total protein (serum)"), "Albümin": ("Albumin", "Albümin"), "Globülin": ("Globulin", "Globülin")}
CELL_UNIT_FACTORS = {"10^3/ul": 1.0, "10³/ul": 1.0, "10*3/ul": 1.0, "x10^3/ul": 1.0, "k/ul": 1.0, "10^9/l": 1.0, "10⁹/l": 1.0, "x10^9/l": 1.0, "/ul": 0.001, "cells/ul": 0.001, "hucre/ul": 0.001, "/mm3": 0.001, "cells/mm3": 0.001}
PROTEIN_UNIT_FACTORS = {"g/dl": 1.0, "g/l": 0.1}
PERCENT_UNITS = frozenset({"%", "percent", "yuzde"})
KNOWN_UNITS = frozenset({"mg/dl", "mg/l", "g/dl", "g/l", "mmol/l", "umol/l", "u/l", "iu/l", "ng/ml", "ng/dl", "pg/ml", "ug/l", "ug/dl", "fl", "pg", "mm/h", "mm/hr", "miu/l", "uiu/ml", "iu/ml", "ng/l"}) | CELL_UNIT_FACTORS.keys() | PERCENT_UNITS
DERIVED_FIELDS = ("is_derived", "derived", "derived_from")
ANNOTATION_ONLY_CODES = frozenset(code for code in MESSAGES_TR if code.startswith(('source_flag_', 'differential_', 'absolute_percent_', 'protein_sum_', 'value_outside_', 'flag_without_', 'magnitude_', 'printed_reference_', 'consistency_unit_', 'report_', 'cross_read_')))
ANNOTATION_FEATURES = ('lab_consistency_rules_enabled', 'report_consistency_enabled', 'lab_cross_read_enabled')
CONCEPT_WINDOW = 70
CLINIC_TIMEZONE = 'Europe/Istanbul'
POLARITY_CLAUSE_SPLIT = r'[.;\n]+|,\s*(?:ancak|fakat)\s*'
ORGAN_TERMS = {'kidney': ('bobrek', 'renal'), 'lung': ('akciger', 'pulmoner', 'lung'), 'ovary': ('over', 'ovary', 'ovaries'),
               'testis': ('testis', 'testicle'), 'uterus': ('uterus', 'rahim'), 'prostate': ('prostat', 'prostate'), 'breast': ('meme', 'breast')}
SEX_SPECIFIC_ORGANS = {'male': ('uterus','ovary'), 'female': ('prostate','testis')}
SIDE_TERMS = {'right': ('sag','right'), 'left': ('sol','left')}
REPORT_DATE_ORDER = (('exam_date','report_date'),('event_date','report_date'),('consultation_date','report_date'),('report_date','uploaded_at'),('document_date','uploaded_at'))

RADIOLOGY_CONCEPT_MARKERS = {
    "pneumothorax": ("pnömotoraks", "pnomotoraks", "pneumothorax"),
    "pleural_effusion": ("plevral efüzyon", "plevral sivi", "pleural effusion"),
    "airspace_opacity": ("opasite", "airspace opacity", "hava sahasi opasitesi"),
    "consolidation": ("konsolidasyon", "consolidation"),
    "atelectasis": ("atelektazi", "atelectasis"),
    "cardiomegaly": ("kardiyomegali", "kalp silueti genis", "cardiomegaly"),
    "pulmonary_edema": ("pulmoner ödem", "pulmoner odem", "pulmonary edema"),
    "free_air": (
        "serbest hava",
        "subdiyafragmatik hava",
        "subdiafragmatik hava",
        "free intraperitoneal air",
        "pneumoperitoneum",
    ),
    "bowel_dilatation": (
        "barsak dilat",
        "bağırsak dilat",
        "bagirsak dilat",
        "bowel dilat",
        "dilated bowel",
    ),
    "air_fluid_levels": ("hava-sıvı", "hava sivi", "air-fluid", "air fluid"),
    "fecal_burden": ("fekal yük", "fekal yuk", "dışkı yük", "diski yuk", "stool burden"),
    "fracture": ("kırık", "kirik", "fracture"),
    "dislocation": ("çıkık", "cikik", "dislocation"),
    "foreign_body": ("yabancı cisim", "yabanci cisim", "foreign body"),
    "calcification": ("kalsifik", "calcific", "calcification"),
    "hydronephrosis": ("hidronefroz", "hydronephrosis"),
}
RADIOLOGY_NEGATION_MARKERS = (
    " yok",
    " izlenmiyor",
    " gorulmuyor",
    " secilmiyor",
    " saptanmadi",
    " mevcut degil",
    " lehine bulgu yok",
    " no evidence",
    " not seen",
    " absent",
    " without evidence",
    " negative for",
)
RADIOLOGY_HIGH_ATTENTION_CONCEPTS = {
    "pneumothorax",
    "free_air",
    "fracture",
    "dislocation",
}
