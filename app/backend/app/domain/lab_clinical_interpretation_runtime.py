"""Add conservative clinical meaning to HIGH/LOW laboratory findings.

This layer does not diagnose. It enriches the deterministic abnormal-lab report with
short mechanism text and a small list of conditions that can be associated with the
same direction of change. The lists are intentionally broad, educational clinical
associations and always require physician correlation with symptoms, examination,
other labs, medications and imaging.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.domain.claude_clinical_hypothesis_service import ClaudeClinicalHypothesisService


_original_build_hypothesis = ClaudeClinicalHypothesisService._build_hypothesis


def _fold(value: object) -> str:
    text = str(value or "")
    translated = text.translate(
        str.maketrans(
            {
                "ı": "i",
                "İ": "i",
                "ş": "s",
                "Ş": "s",
                "ğ": "g",
                "Ğ": "g",
                "ü": "u",
                "Ü": "u",
                "ö": "o",
                "Ö": "o",
                "ç": "c",
                "Ç": "c",
            }
        )
    )
    normalized = unicodedata.normalize("NFKD", translated)
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-zA-Z0-9]+", " ", ascii_text).strip().lower()


def _matches(name: str, aliases: tuple[str, ...]) -> bool:
    padded = f" {name} "
    for alias in aliases:
        folded = _fold(alias)
        if not folded:
            continue
        if len(folded) <= 5 and " " not in folded:
            if f" {folded} " in padded:
                return True
        elif folded in name:
            return True
    return False


_ALIASES: dict[str, tuple[str, ...]] = {
    "alt": ("ALT", "alanin aminotransferaz", "alanine aminotransferase"),
    "ast": ("AST", "aspartat aminotransferaz", "aspartate aminotransferase"),
    "alp": ("ALP", "alkalen fosfataz", "alkaline phosphatase"),
    "ggt": ("GGT", "gama glutamil transferaz", "gamma glutamyl transferase"),
    "bilirubin": ("bilirubin", "total bilirubin", "direkt bilirubin", "indirekt bilirubin"),
    "creatinine": ("kreatinin", "creatinine"),
    "urea": ("üre", "urea", "BUN", "blood urea nitrogen"),
    "egfr": ("eGFR", "glomeruler filtrasyon", "glomerular filtration"),
    "sodium": ("sodyum", "sodium", "Na"),
    "potassium": ("potasyum", "potassium", "K"),
    "calcium": ("kalsiyum", "calcium", "Ca"),
    "magnesium": ("magnezyum", "magnesium", "Mg"),
    "glucose": ("glukoz", "glucose", "kan şekeri", "blood glucose"),
    "hba1c": ("HbA1c", "hemoglobin a1c", "glycated hemoglobin"),
    "crp": ("CRP", "c reactive protein", "c-reaktif protein"),
    "esr": ("ESR", "sedimantasyon", "erythrocyte sedimentation rate"),
    "wbc": ("WBC", "lökosit", "leukocyte", "white blood cell"),
    "neutrophil": ("nötrofil", "neutrophil", "NEU"),
    "lymphocyte": ("lenfosit", "lymphocyte", "LYM"),
    "hemoglobin": ("hemoglobin", "HGB", "Hb"),
    "hematocrit": ("hematokrit", "hematocrit", "HCT"),
    "platelet": ("trombosit", "platelet", "PLT"),
    "ferritin": ("ferritin",),
    "iron": ("serum demir", "iron", "Fe"),
    "b12": ("vitamin B12", "B12", "cobalamin"),
    "folate": ("folat", "folate", "folic acid"),
    "tsh": ("TSH", "thyroid stimulating hormone", "tiroid stimulan hormon"),
    "ft4": ("fT4", "free T4", "serbest T4"),
    "ldl": ("LDL", "ldl kolesterol", "ldl cholesterol"),
    "hdl": ("HDL", "hdl kolesterol", "hdl cholesterol"),
    "triglyceride": ("trigliserid", "triglyceride", "TG"),
    "cholesterol": ("total kolesterol", "total cholesterol", "kolesterol"),
    "uric_acid": ("ürik asit", "uric acid"),
    "albumin": ("albumin",),
    "total_protein": ("total protein", "toplam protein"),
    "ldh": ("LDH", "laktat dehidrogenaz", "lactate dehydrogenase"),
    "ck": ("CK", "kreatin kinaz", "creatine kinase", "CPK"),
}


# Each entry: direction -> (clinical mechanism, possible associated conditions)
_KNOWLEDGE: dict[str, dict[str, tuple[str, tuple[str, ...]]]] = {
    "alt": {
        "high": (
            "ALT karaciğer hücrelerinde yoğun bulunan bir enzimdir; hepatosit hasarında kana salınımı artabilir.",
            ("Karaciğer yağlanması / steatohepatit", "Viral hepatit", "İlaç veya toksine bağlı karaciğer hasarı", "İskemik veya inflamatuvar karaciğer hasarı"),
        ),
    },
    "ast": {
        "high": (
            "AST karaciğer yanında kas ve diğer dokularda da bulunur; hücresel hasarda kana geçişi artabilir.",
            ("Karaciğer hastalıkları", "Kas hasarı veya rabdomiyoliz", "Yoğun egzersiz / doku hasarı", "Hemoliz"),
        ),
    },
    "alp": {
        "high": (
            "ALP özellikle safra yolları ve kemik dokusuyla ilişkilidir; kolestaz veya artmış kemik dönüşümünde yükselebilir.",
            ("Safra yolu tıkanıklığı / kolestaz", "Karaciğer-safra yolu hastalıkları", "Kemik hastalıkları veya artmış kemik yapımı", "Gebelikte fizyolojik artış"),
        ),
    },
    "ggt": {
        "high": (
            "GGT safra yolu ve karaciğer enzim indüksiyonunu yansıtabilir; kolestaz ve bazı toksik etkilerde artabilir.",
            ("Kolestaz / safra yolu hastalıkları", "Alkole bağlı karaciğer etkilenimi", "İlaçlara bağlı enzim indüksiyonu", "Karaciğer yağlanması"),
        ),
    },
    "bilirubin": {
        "high": (
            "Bilirubin üretiminin artması, karaciğerde işlenmesinin azalması veya safra ile atılımın bozulması sonucu yükselebilir.",
            ("Hemoliz", "Hepatit veya hepatoselüler hasar", "Safra yolu tıkanıklığı", "Gilbert sendromu gibi konjugasyon bozuklukları"),
        ),
    },
    "creatinine": {
        "high": (
            "Kreatinin yükselmesi çoğunlukla böbrek filtrasyonunun azalmasını veya daha nadiren artmış kas kaynaklı üretimi düşündürür.",
            ("Akut böbrek hasarı", "Kronik böbrek hastalığı", "Dehidratasyon / böbrek perfüzyonunda azalma", "Kas hasarı veya rabdomiyoliz"),
        ),
        "low": (
            "Düşük kreatinin genellikle düşük kas kütlesi veya artmış filtrasyonla ilişkilidir.",
            ("Düşük kas kütlesi / malnütrisyon", "Gebelik", "İleri karaciğer hastalığında düşük kreatinin üretimi"),
        ),
    },
    "urea": {
        "high": (
            "Üre, böbrekten atılım azalması veya protein yıkımının artmasıyla yükselebilir.",
            ("Dehidratasyon", "Böbrek fonksiyon bozukluğu", "Gastrointestinal kanama", "Artmış protein katabolizması"),
        ),
        "low": (
            "Düşük üre, düşük protein üretimi/alımı veya artmış sıvı yüküyle ilişkili olabilir.",
            ("Düşük protein alımı / malnütrisyon", "İleri karaciğer fonksiyon bozukluğu", "Aşırı hidrasyon", "Gebelik"),
        ),
    },
    "egfr": {
        "low": (
            "Düşük eGFR böbreklerin tahmini filtrasyon kapasitesinin azaldığını gösterir; tek ölçüm kronik hastalık tanısı koydurmaz.",
            ("Akut böbrek hasarı", "Kronik böbrek hastalığı", "Dehidratasyon / geçici perfüzyon azalması", "Bazı ilaç veya hemodinamik etkiler"),
        ),
    },
    "sodium": {
        "high": (
            "Sodyum yüksekliği çoğunlukla serbest su kaybının sodyum kaybından fazla olmasıyla gelişir.",
            ("Dehidratasyon", "Diabetes insipidus", "Yetersiz su alımı", "Osmotik diürez"),
        ),
        "low": (
            "Sodyum düşüklüğü su fazlalığı, sodyum kaybı veya her ikisinin kombinasyonuyla oluşabilir.",
            ("SIADH", "Diüretik kullanımı", "Kalp yetmezliği / siroz gibi ödemli durumlar", "Kusma-ishal veya adrenal yetmezlik"),
        ),
    },
    "potassium": {
        "high": (
            "Potasyum yüksekliği böbrekten atılım azalması, hücre içinden dışına geçiş veya örnek hemoliziyle görülebilir.",
            ("Böbrek yetmezliği", "Asidoz veya doku yıkımı", "Potasyumu yükselten ilaçlar", "Numune hemolizi / psödohiperkalemi"),
        ),
        "low": (
            "Potasyum düşüklüğü gastrointestinal veya renal kayıp ya da hücre içine geçiş nedeniyle oluşabilir.",
            ("Kusma / ishal", "Diüretik kullanımı", "Hiperaldosteronizm", "İnsülin veya alkaloza bağlı hücre içine geçiş"),
        ),
    },
    "calcium": {
        "high": (
            "Kalsiyum yüksekliği paratiroid aktivitesi, malignite veya artmış kemik/vitamin D etkisiyle ilişkili olabilir.",
            ("Primer hiperparatiroidi", "Malignite ilişkili hiperkalsemi", "Vitamin D fazlalığı / granülomatöz hastalık", "Dehidratasyon"),
        ),
        "low": (
            "Kalsiyum düşüklüğü albümin düşüklüğü, vitamin D/paratiroid bozukluğu veya böbrek hastalığıyla ilişkili olabilir.",
            ("Vitamin D eksikliği", "Hipoparatiroidi", "Kronik böbrek hastalığı", "Hipoalbüminemi"),
        ),
    },
    "magnesium": {
        "high": (
            "Magnezyum yüksekliği en sık böbrekten atılımın azalması veya fazla magnezyum alımıyla ilişkilidir.",
            ("Böbrek yetmezliği", "Magnezyum içeren ilaç/antiasit fazlalığı", "Nadir endokrin veya hücresel yıkım durumları"),
        ),
        "low": (
            "Magnezyum düşüklüğü gastrointestinal kayıp, renal kayıp veya yetersiz alımla gelişebilir.",
            ("Kronik ishal / malabsorpsiyon", "Diüretik kullanımı", "Alkol kullanım bozukluğu", "Yetersiz beslenme"),
        ),
    },
    "glucose": {
        "high": (
            "Glukoz yüksekliği insülin etkisinin yetersizliği veya stres hormonlarının artmasıyla ortaya çıkabilir.",
            ("Diabetes mellitus", "Stres hiperglisemisi / akut hastalık", "Kortikosteroid etkisi", "Endokrin bozukluklar"),
        ),
        "low": (
            "Glukoz düşüklüğü fazla insülin etkisi, yetersiz alım veya ağır sistemik hastalıkla ilişkili olabilir.",
            ("İnsülin veya antidiyabetik ilaç etkisi", "Uzun açlık / yetersiz beslenme", "Karaciğer yetmezliği", "Sepsis veya adrenal yetmezlik"),
        ),
    },
    "hba1c": {
        "high": (
            "HbA1c son haftalar-aylardaki ortalama gliseminin yüksek olduğunu düşündürür.",
            ("Prediyabet", "Diabetes mellitus", "Yetersiz glisemik kontrol"),
        ),
    },
    "crp": {
        "high": (
            "CRP karaciğerin inflamasyona yanıt olarak ürettiği akut faz proteinidir; enfeksiyon veya doku inflamasyonunda artabilir.",
            ("Bakteriyel veya viral enfeksiyonlar", "Otoimmün / inflamatuvar hastalıklar", "Doku hasarı, cerrahi veya travma", "Bazı maligniteler"),
        ),
    },
    "esr": {
        "high": (
            "Sedimantasyon, plazma proteinleri ve eritrosit özelliklerinden etkilenir; inflamatuvar süreçlerde hızlanabilir.",
            ("Enfeksiyon", "Otoimmün / inflamatuvar hastalık", "Anemi", "Bazı maligniteler"),
        ),
    },
    "wbc": {
        "high": (
            "Lökosit yüksekliği kemik iliğinin enfeksiyon, inflamasyon veya stres yanıtıyla hücre üretimini/salınımını artırmasıyla görülebilir.",
            ("Enfeksiyon", "Akut inflamasyon / stres", "Kortikosteroid etkisi", "Lösemi veya diğer miyeloproliferatif hastalıklar"),
        ),
        "low": (
            "Lökosit düşüklüğü üretim azalması, tüketim artışı veya ilaç/enfeksiyon etkisiyle oluşabilir.",
            ("Viral enfeksiyonlar", "Kemik iliği baskılanması", "İlaç veya kemoterapi etkisi", "Otoimmün hastalıklar"),
        ),
    },
    "neutrophil": {
        "high": (
            "Nötrofil yüksekliği sıklıkla akut enfeksiyon, inflamasyon veya stres yanıtında görülür.",
            ("Bakteriyel enfeksiyon", "Akut inflamasyon / doku hasarı", "Kortikosteroid veya stres yanıtı", "Miyeloproliferatif hastalıklar"),
        ),
        "low": (
            "Nötrofil düşüklüğü üretim azalması veya artmış yıkım/tüketim nedeniyle gelişebilir.",
            ("Viral enfeksiyon", "İlaç/kemoterapiye bağlı kemik iliği baskılanması", "Otoimmün nötropeni", "Kemik iliği hastalıkları"),
        ),
    },
    "lymphocyte": {
        "high": (
            "Lenfosit yüksekliği özellikle bazı viral enfeksiyonlarda veya lenfoid hücre çoğalmasında görülebilir.",
            ("Viral enfeksiyonlar", "Boğmaca gibi bazı enfeksiyonlar", "Kronik lenfositik lösemi / lenfoproliferatif hastalıklar"),
        ),
        "low": (
            "Lenfosit düşüklüğü stres, kortikosteroid etkisi veya immün baskılanmayla ilişkili olabilir.",
            ("Akut stres / ağır enfeksiyon", "Kortikosteroid kullanımı", "İmmün yetmezlik", "Kemoterapi veya immünsüpresif tedavi"),
        ),
    },
    "hemoglobin": {
        "high": (
            "Hemoglobin yüksekliği kanın yoğunlaşması veya eritrosit kütlesinin gerçekten artmasıyla oluşabilir.",
            ("Dehidratasyona bağlı hemokonsantrasyon", "Kronik hipoksi / akciğer hastalığı", "Yüksek rakım", "Polisitemia vera"),
        ),
        "low": (
            "Hemoglobin düşüklüğü anemi göstergesidir; üretim azalması, kayıp veya eritrosit yıkımı neden olabilir.",
            ("Demir eksikliği anemisi", "Kan kaybı", "Kronik hastalık veya böbrek hastalığı anemisi", "B12/folat eksikliği veya hemoliz"),
        ),
    },
    "hematocrit": {
        "high": (
            "Hematokrit yüksekliği hemokonsantrasyon veya eritrosit kütlesi artışıyla ilişkilidir.",
            ("Dehidratasyon", "Kronik hipoksi", "Yüksek rakım", "Polisitemia vera"),
        ),
        "low": (
            "Hematokrit düşüklüğü çoğunlukla anemi veya hemodilüsyonla birlikte görülür.",
            ("Demir eksikliği veya diğer anemiler", "Kan kaybı", "Kronik hastalık", "Aşırı sıvı yükü / hemodilüsyon"),
        ),
    },
    "platelet": {
        "high": (
            "Trombosit yüksekliği reaktif inflamasyon/demir eksikliği yanıtı veya kemik iliği kaynaklı artışla görülebilir.",
            ("Enfeksiyon / inflamasyon", "Demir eksikliği", "Cerrahi veya splenektomi sonrası", "Esansiyel trombositemi gibi miyeloproliferatif hastalıklar"),
        ),
        "low": (
            "Trombosit düşüklüğü üretim azalması, tüketim/yıkım artışı veya dalakta tutulma nedeniyle olabilir.",
            ("Viral enfeksiyonlar", "İlaç veya kemik iliği baskılanması", "İmmün trombositopeni", "DIC / TTP gibi tüketim tabloları veya hipersplenizm"),
        ),
    },
    "ferritin": {
        "high": (
            "Ferritin demir deposunu yansıtır ancak aynı zamanda akut faz reaktanıdır; inflamasyonda demir fazlalığı olmadan da yükselebilir.",
            ("Enfeksiyon / inflamasyon", "Karaciğer hastalığı", "Demir yüklenmesi / hemokromatozis", "Bazı maligniteler"),
        ),
        "low": (
            "Düşük ferritin çoğunlukla vücut demir depolarının azaldığını gösterir.",
            ("Demir eksikliği", "Kronik kan kaybı", "Yetersiz demir alımı", "Malabsorpsiyon"),
        ),
    },
    "iron": {
        "high": (
            "Serum demiri yüksekliği artmış demir yükü veya hücresel demir salınımıyla görülebilir.",
            ("Demir yüklenmesi / hemokromatozis", "Demir takviyesi fazlalığı", "Hemoliz", "Bazı karaciğer hastalıkları"),
        ),
        "low": (
            "Serum demiri düşüklüğü demir eksikliği veya inflamasyonda demirin dolaşımdan çekilmesiyle görülebilir.",
            ("Demir eksikliği", "Kronik kan kaybı", "Kronik inflamasyon", "Malabsorpsiyon / yetersiz alım"),
        ),
    },
    "b12": {
        "high": (
            "B12 yüksekliği takviye kullanımına bağlı olabileceği gibi bazı karaciğer, böbrek veya hematolojik durumlarda da görülebilir.",
            ("B12 takviyesi", "Karaciğer hastalıkları", "Böbrek fonksiyon bozukluğu", "Bazı miyeloproliferatif hastalıklar"),
        ),
        "low": (
            "B12 düşüklüğü yetersiz alım veya emilim bozukluğuna bağlı olabilir ve megaloblastik anemi/nörolojik bulgularla ilişkili olabilir.",
            ("Pernisiyöz anemi", "Malabsorpsiyon / mide-bağırsak hastalıkları", "Vegan veya yetersiz beslenme", "Bazı ilaçlara bağlı emilim bozukluğu"),
        ),
    },
    "folate": {
        "low": (
            "Folat düşüklüğü yetersiz alım, artmış gereksinim veya emilim bozukluğuyla ilişkili olabilir.",
            ("Yetersiz beslenme", "Malabsorpsiyon", "Gebelikte artmış gereksinim", "Bazı ilaçlara bağlı folat metabolizması bozukluğu"),
        ),
    },
    "tsh": {
        "high": (
            "TSH yüksekliği çoğunlukla tiroid bezinin yetersiz hormon üretimine karşı hipofiz yanıtını yansıtır.",
            ("Primer hipotiroidi", "Hashimoto tiroiditi", "Tiroid cerrahisi/radyoiyot sonrası durum", "Bazı ilaçların tiroid etkileri"),
        ),
        "low": (
            "TSH düşüklüğü aşırı tiroid hormonu etkisi veya daha nadiren hipofiz/hipotalamus bozukluğuyla ilişkili olabilir.",
            ("Hipertiroidi / Graves hastalığı", "Tiroidit", "Fazla tiroid hormonu kullanımı", "Santral hipotiroidi için fT4 ile birlikte değerlendirme gereksinimi"),
        ),
    },
    "ft4": {
        "high": (
            "Serbest T4 yüksekliği dolaşımdaki aktif tiroid hormonunun arttığını gösterir; TSH ile birlikte yorumlanmalıdır.",
            ("Graves hastalığı / hipertiroidi", "Tiroidit", "Fazla tiroid hormonu kullanımı"),
        ),
        "low": (
            "Serbest T4 düşüklüğü tiroid hormon üretiminin azalmasıyla ilişkili olabilir; TSH ile birlikte yorumlanmalıdır.",
            ("Primer hipotiroidi", "Santral hipotiroidi", "Ağır sistemik hastalıkta tiroid test değişiklikleri"),
        ),
    },
    "ldl": {
        "high": (
            "LDL yüksekliği aterojenik kolesterol yükünün arttığını gösterir ve kardiyovasküler risk değerlendirmesinde önemlidir.",
            ("Primer/familial hiperkolesterolemi", "Hipotiroidi", "Nefrotik sendrom", "Diyet/metabolik faktörler"),
        ),
    },
    "hdl": {
        "low": (
            "HDL düşüklüğü ters kolesterol taşınmasının daha düşük olmasıyla ilişkilidir ve metabolik/kardiyovasküler risk belirteçlerinden biridir.",
            ("Metabolik sendrom / insülin direnci", "Obezite", "Sigara kullanımı", "Hipertrigliseridemi"),
        ),
    },
    "triglyceride": {
        "high": (
            "Trigliserid yüksekliği karaciğerden VLDL üretiminin artması veya yağların temizlenmesinin azalmasıyla görülebilir.",
            ("İnsülin direnci / diabetes mellitus", "Obezite / metabolik sendrom", "Alkol kullanımı", "Hipotiroidi veya bazı ilaçlar"),
        ),
    },
    "cholesterol": {
        "high": (
            "Total kolesterol yüksekliği LDL başta olmak üzere aterojenik lipoprotein artışını yansıtabilir; fraksiyonlarla birlikte yorumlanmalıdır.",
            ("Primer hiperlipidemi", "Hipotiroidi", "Nefrotik sendrom", "Diyet ve metabolik faktörler"),
        ),
    },
    "uric_acid": {
        "high": (
            "Ürik asit yüksekliği üretim artışı veya böbrekten atılım azalmasıyla gelişebilir.",
            ("Gut / hiperürisemi", "Böbrek fonksiyon bozukluğu", "Diüretik kullanımı", "Yüksek hücre yıkımı / tümör lizisi"),
        ),
        "low": (
            "Düşük ürik asit artmış renal atılım veya azalmış üretimle ilişkili olabilir.",
            ("SIADH", "Bazı ilaçlar", "Nadir tübüler bozukluklar", "Ağır karaciğer hastalığı"),
        ),
    },
    "albumin": {
        "high": (
            "Albumin yüksekliği çoğunlukla plazma suyunun azalmasına bağlı göreceli artıştır.",
            ("Dehidratasyon / hemokonsantrasyon",),
        ),
        "low": (
            "Albumin düşüklüğü sentez azalması, kayıp, inflamasyon veya dilüsyonla gelişebilir.",
            ("Karaciğer yetmezliği / siroz", "Nefrotik sendrom veya renal protein kaybı", "Malnütrisyon / malabsorpsiyon", "Kronik inflamasyon veya protein kaybettiren enteropati"),
        ),
    },
    "total_protein": {
        "high": (
            "Toplam protein yüksekliği dehidratasyon veya immünoglobulin artışıyla ilişkili olabilir.",
            ("Dehidratasyon", "Monoklonal gammopati / multipl miyelom", "Kronik inflamasyon veya enfeksiyon"),
        ),
        "low": (
            "Toplam protein düşüklüğü protein sentezinin azalması, kayıp veya yetersiz alımla ilişkili olabilir.",
            ("Karaciğer hastalığı", "Nefrotik sendrom", "Malnütrisyon / malabsorpsiyon", "Protein kaybettiren enteropati"),
        ),
    },
    "ldh": {
        "high": (
            "LDH birçok dokuda bulunan bir enzimdir; hücre hasarı veya hızlı hücre dönüşümünde yükselebilir ve özgül değildir.",
            ("Hemoliz", "Karaciğer veya kas doku hasarı", "Enfeksiyon / inflamasyon", "Bazı hematolojik veya solid maligniteler"),
        ),
    },
    "ck": {
        "high": (
            "CK kas hücresi hasarında kana salınır; yükselme çoğunlukla iskelet veya kalp kası kaynaklı olabilir.",
            ("Yoğun egzersiz / kas travması", "Rabdomiyoliz", "Miyozit", "İlaçlara bağlı kas hasarı"),
        ),
    },
}


def _lookup(name: str, status: str) -> tuple[str | None, list[str]]:
    normalized = _fold(name)
    for key, aliases in _ALIASES.items():
        if not _matches(normalized, aliases):
            continue
        entry = _KNOWLEDGE.get(key, {}).get(status)
        if entry is None:
            return None, []
        interpretation, causes = entry
        return interpretation, list(causes[:5])
    return None, []


def _build_hypothesis_with_clinical_interpretation(
    self: ClaudeClinicalHypothesisService,
    run: Any,
    *,
    risk: int,
    summary: str,
    flags: list[str],
    symptoms: list[str],
    evidence: list[dict[str, Any]],
    ai_called: bool,
):
    hypothesis = _original_build_hypothesis(
        self,
        run,
        risk=risk,
        summary=summary,
        flags=flags,
        symptoms=symptoms,
        evidence=evidence,
        ai_called=ai_called,
    )

    metadata = dict(hypothesis.metadata_json or {})
    findings = list(metadata.get("pathological_findings") or [])
    enriched = 0

    for finding in findings:
        if not isinstance(finding, dict) or finding.get("source") != "laboratory":
            continue
        status = str(finding.get("status") or "").lower()
        if status not in {"high", "low"}:
            continue
        interpretation, causes = _lookup(str(finding.get("name") or ""), status)
        finding["clinical_interpretation"] = interpretation
        finding["possible_causes"] = causes
        finding["clinical_note"] = (
            "Bu ilişkiler olasılık düzeyindedir; tek laboratuvar sonucu tanı koydurmaz. "
            "Klinik öykü, muayene, diğer tetkikler ve ilaçlarla birlikte hekim tarafından değerlendirilmelidir."
        )
        if interpretation or causes:
            enriched += 1

    metadata["pathological_findings"] = findings
    metadata["clinical_interpretation_count"] = enriched
    metadata["clinical_interpretation_source"] = "curated_general_associations_v1"
    hypothesis.metadata_json = metadata
    return hypothesis


ClaudeClinicalHypothesisService._build_hypothesis = _build_hypothesis_with_clinical_interpretation
