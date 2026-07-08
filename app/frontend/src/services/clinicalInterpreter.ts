import type { LabAnalysisResult, LabResultStatus } from './labAnalysisClient';

export type DoctorSignalSeverity = 'low' | 'moderate' | 'high';

export type DoctorInterpretationItem = {
  id: string;
  title: string;
  system: string;
  severity: DoctorSignalSeverity;
  markers: string[];
  interpretation: string;
  clinicalContext: string;
  suggestedDoctorAction: string;
};

export type DoctorInterpretationSummary = {
  abnormalCount: number;
  lowCount: number;
  highCount: number;
  items: DoctorInterpretationItem[];
  safetyNote: string;
};

type ResultLookup = {
  result: LabAnalysisResult;
  name: string;
  status: LabResultStatus | string;
  valueText: string;
};

function displayName(result: LabAnalysisResult): string {
  return result.canonical_name ?? result.raw_parameter_name;
}

function valueText(result: LabAnalysisResult): string {
  return `${result.normalized_value} ${result.unit}`.trim();
}

function normalizedName(result: LabAnalysisResult): string {
  return displayName(result)
    .toLocaleUpperCase('tr-TR')
    .replace(/İ/g, 'I')
    .replace(/ı/g, 'I')
    .replace(/Ş/g, 'S')
    .replace(/Ğ/g, 'G')
    .replace(/Ü/g, 'U')
    .replace(/Ö/g, 'O')
    .replace(/Ç/g, 'C')
    .replace(/[^A-Z0-9]+/g, '_');
}

function normalizeStatus(status: LabResultStatus | string): string {
  return status.toLowerCase();
}

function isLowOrHigh(result: LabAnalysisResult): boolean {
  const status = normalizeStatus(result.result_status);

  return status === 'low' || status === 'high';
}

function makeLookup(results: LabAnalysisResult[]): ResultLookup[] {
  return results.map((result) => ({
    result,
    name: normalizedName(result),
    status: normalizeStatus(result.result_status),
    valueText: valueText(result),
  }));
}

function findByAnyName(
  lookup: ResultLookup[],
  names: string[],
): ResultLookup | undefined {
  return lookup.find((item) => names.some((name) => item.name === name));
}

function findMatching(
  lookup: ResultLookup[],
  names: string[],
): ResultLookup[] {
  return lookup.filter((item) => names.some((name) => item.name === name));
}

function markerList(items: ResultLookup[]): string[] {
  return items.map((item) => `${displayName(item.result)} ${item.valueText}`);
}

function hasNormal(lookup: ResultLookup[], names: string[]): boolean {
  const item = findByAnyName(lookup, names);

  return item?.status === 'normal';
}

function abnormalWithin(lookup: ResultLookup[], names: string[]): ResultLookup[] {
  return findMatching(lookup, names).filter((item) => isLowOrHigh(item.result));
}

function createGenericItem(item: ResultLookup): DoctorInterpretationItem {
  const markerName = displayName(item.result);
  const status = item.status === 'high' ? 'yüksek' : 'düşük';

  return {
    id: `generic-${item.name}`,
    title: `${markerName} ${status} saptandı`,
    system: 'Genel laboratuvar değerlendirmesi',
    severity: 'moderate',
    markers: markerList([item]),
    interpretation: `${markerName} değeri referans aralığın ${status} tarafında saptanmıştır. Bu bulgu tek başına tanı koydurmaz; klinik öykü, muayene bulguları ve varsa önceki sonuçlarla birlikte değerlendirilmelidir.`,
    clinicalContext:
      'İzole laboratuvar sapmaları örnek alma zamanı, geçici fizyolojik değişkenlik, ilaç kullanımı, yakın dönem enfeksiyon veya altta yatan klinik durumlarla ilişkili olabilir.',
    suggestedDoctorAction:
      'Hekim tarafından klinik bağlamla birlikte değerlendirilmesi, gerekirse önceki testlerle karşılaştırılması ve uygun görülürse kontrol tetkiki planlanması önerilir.',
  };
}

export function buildDoctorInterpretation(
  results: LabAnalysisResult[],
): DoctorInterpretationSummary {
  const lookup = makeLookup(results);
  const abnormal = lookup.filter((item) => isLowOrHigh(item.result));
  const used = new Set<string>();
  const items: DoctorInterpretationItem[] = [];

  const addItem = (item: DoctorInterpretationItem, sourceItems: ResultLookup[]) => {
    items.push(item);
    sourceItems.forEach((source) => used.add(source.name));
  };

  const lipidSignals = abnormalWithin(lookup, [
    'TOTAL_KOLESTEROL',
    'HDL',
    'TRIGLISERIT',
    'LDL',
    'NON_HDL',
  ]);

  if (lipidSignals.length > 0) {
    const hdl = findByAnyName(lookup, ['HDL']);
    const lowHdl = hdl?.status === 'low';

    addItem(
      {
        id: 'lipid-profile',
        title: lowHdl
          ? 'HDL kolesterol düşüklüğü'
          : 'Lipid profilinde referans dışı bulgu',
        system: 'Kardiyometabolik risk',
        severity: lowHdl && lipidSignals.length === 1 ? 'moderate' : 'high',
        markers: markerList(lipidSignals),
        interpretation: lowHdl
          ? 'HDL kolesterol referans aralığın altında saptanmıştır. HDL düşüklüğü kardiyometabolik risk değerlendirmesinde dikkate alınmalıdır.'
          : 'Lipid profilinde referans dışı değerler saptanmıştır. Bulgular kardiyovasküler risk profili içinde birlikte değerlendirilmelidir.',
        clinicalContext:
          'Total kolesterol, LDL, HDL ve trigliserit değerleri tek tek değil, hastanın yaşı, aile öyküsü, tansiyon, sigara, diyabet ve diğer risk faktörleriyle birlikte yorumlanmalıdır.',
        suggestedDoctorAction:
          'Yaşam tarzı, beslenme, fiziksel aktivite ve kardiyovasküler risk skorlaması açısından hekim değerlendirmesi önerilir. Gerekirse lipid profili takibi planlanabilir.',
      },
      lipidSignals,
    );
  }

  const bilirubinSignals = abnormalWithin(lookup, [
    'TOTAL_BILIRUBIN',
    'DIREKT_BILIRUBIN',
    'BILIRUBIN_TOTAL',
    'DIRECT_BILIRUBIN',
  ]);

  if (bilirubinSignals.length > 0) {
    const liverEnzymesNormal =
      hasNormal(lookup, ['ALT']) &&
      hasNormal(lookup, ['AST']) &&
      hasNormal(lookup, ['ALP']) &&
      hasNormal(lookup, ['GGT']);

    addItem(
      {
        id: 'bilirubin',
        title: 'Bilirubin yüksekliği',
        system: 'Karaciğer / safra yolları',
        severity: 'moderate',
        markers: markerList(bilirubinSignals),
        interpretation:
          'Total ve/veya direkt bilirubin referans aralığın üzerinde saptanmıştır. Bu bulgu bilirubin metabolizması, karaciğer fonksiyonları veya safra akımı ile ilişkili süreçler açısından değerlendirilmelidir.',
        clinicalContext: liverEnzymesNormal
          ? 'ALT, AST, ALP ve GGT değerlerinin normal olması, bulgunun izole veya hafif bilirubin yüksekliği şeklinde ele alınabileceğini düşündürür; yine de klinik bağlam önemlidir.'
          : 'Karaciğer enzimleriyle birlikte değerlendirme gereklidir. Eşlik eden enzim yüksekliği varsa hepatobiliyer süreçler açısından dikkatli yorumlanmalıdır.',
        suggestedDoctorAction:
          'Semptomlar, ilaç kullanımı, sarılık öyküsü, açlık durumu ve önceki bilirubin sonuçlarıyla birlikte hekim değerlendirmesi önerilir. Gerekirse kontrol biyokimya paneli istenebilir.',
      },
      bilirubinSignals,
    );
  }

  const cbcSignals = abnormalWithin(lookup, [
    'LOKOSIT',
    'WBC',
    'NOTROFIL_MUTLAK',
    'NOTROFIL',
    'LENFOSIT_MUTLAK',
    'LENFOSIT',
    'MONOSIT_MUTLAK',
    'EOZINOFIL_MUTLAK',
    'BAZOFIL_MUTLAK',
    'HEMOGLOBIN',
    'HEMATOKRIT',
    'ERITROSIT',
    'TROMBOSIT',
  ]);

  if (cbcSignals.length > 0) {
    const wbc = findByAnyName(lookup, ['LOKOSIT', 'WBC']);
    const lowWbc = wbc?.status === 'low';

    addItem(
      {
        id: 'cbc',
        title: lowWbc ? 'Hafif lökopeni' : 'Hemogramda referans dışı bulgu',
        system: 'Hemogram / kan hücreleri',
        severity: 'moderate',
        markers: markerList(cbcSignals),
        interpretation: lowWbc
          ? 'Lökosit değeri referans aralığın hafif altında saptanmıştır. Bu durum hafif lökopeni olarak değerlendirilebilir.'
          : 'Hemogram parametrelerinde referans dışı değer saptanmıştır. Bulgular hücre serileri ve diferansiyel dağılım ile birlikte yorumlanmalıdır.',
        clinicalContext:
          'Hafif hemogram sapmaları yakın dönem viral enfeksiyon, ilaç kullanımı, bireysel varyasyon veya geçici kemik iliği yanıtları ile ilişkili olabilir. Tek ölçümle kesin klinik çıkarım yapılmamalıdır.',
        suggestedDoctorAction:
          'Hastanın semptomları, ateş/enfeksiyon bulguları, ilaç öyküsü ve önceki hemogramları ile birlikte değerlendirme önerilir. Gerekirse kontrol hemogram planlanabilir.',
      },
      cbcSignals,
    );
  }

  const plateletIndexSignals = abnormalWithin(lookup, ['P_LCR', 'PCT', 'MPV']);

  if (plateletIndexSignals.length > 0) {
    const plateletNormal = hasNormal(lookup, ['TROMBOSIT', 'PLATELET', 'PLT']);
    const mpvNormal = hasNormal(lookup, ['MPV']);

    addItem(
      {
        id: 'platelet-indices',
        title: 'Trombosit indekslerinde referans dışı bulgu',
        system: 'Trombosit parametreleri',
        severity: 'low',
        markers: markerList(plateletIndexSignals),
        interpretation:
          'P-LCR veya diğer trombosit indekslerinde referans dışı değer saptanmıştır. Bu parametreler trombosit boyutu ve dağılımı hakkında yardımcı bilgi verir.',
        clinicalContext:
          plateletNormal && mpvNormal
            ? 'Trombosit sayısı ve MPV normal aralıkta olduğunda P-LCR düşüklüğünün tek başına klinik anlamı sınırlı olabilir.'
            : 'Trombosit sayısı, MPV ve diğer hemogram parametreleriyle birlikte değerlendirilmelidir.',
        suggestedDoctorAction:
          'Tek başına karar verdirici değildir. Hemogram bütünlüğü, klinik bulgular ve gerekirse takip sonucu ile birlikte hekim tarafından yorumlanmalıdır.',
      },
      plateletIndexSignals,
    );
  }

  const folateSignals = abnormalWithin(lookup, ['FOLIK_ASIT', 'FOLATE', 'FOLIC_ACID']);

  if (folateSignals.length > 0) {
    const folateLow = folateSignals.some((item) => item.status === 'low');

    addItem(
      {
        id: 'folate',
        title: folateLow ? 'Folik asit düşüklüğü' : 'Folik asit yüksekliği',
        system: 'Vitamin / beslenme durumu',
        severity: 'moderate',
        markers: markerList(folateSignals),
        interpretation: folateLow
          ? 'Folik asit değeri referans aralığın altında saptanmıştır. Bu bulgu folat eksikliği açısından değerlendirilmelidir.'
          : 'Folik asit değeri referans aralığın üzerinde saptanmıştır. Takviye kullanımı veya yakın dönem alım öyküsü ile birlikte yorumlanmalıdır.',
        clinicalContext:
          'Folik asit sonucu hemoglobin, MCV, B12 düzeyi, beslenme öyküsü ve varsa takviye kullanımıyla birlikte değerlendirilmelidir.',
        suggestedDoctorAction:
          'Eksiklik şüphesinde hekim değerlendirmesi, beslenme/takviye öyküsünün sorgulanması ve gerekirse takip veya ek tetkik planlanması önerilir.',
      },
      folateSignals,
    );
  }

  const inflammationSignals = abnormalWithin(lookup, ['CRP', 'SEDIMENTASYON', 'ESR']);

  if (inflammationSignals.length > 0) {
    addItem(
      {
        id: 'inflammation',
        title: 'İnflamasyon belirteçlerinde artış',
        system: 'İnflamasyon / enfeksiyon',
        severity: 'moderate',
        markers: markerList(inflammationSignals),
        interpretation:
          'CRP ve/veya sedimentasyon değerinde yükseklik saptanmıştır. Bu bulgular inflamasyon veya enfeksiyon süreçleriyle ilişkili olabilir.',
        clinicalContext:
          'Bu belirteçler özgül değildir; enfeksiyon, inflamatuvar durumlar, travma veya başka klinik süreçlerde yükselebilir.',
        suggestedDoctorAction:
          'Ateş, ağrı, enfeksiyon bulguları ve muayene ile birlikte değerlendirme önerilir. Gerekirse klinik odağa göre ek tetkik planlanabilir.',
      },
      inflammationSignals,
    );
  }

  const thyroidSignals = abnormalWithin(lookup, ['TSH', 'FT3', 'FT4']);

  if (thyroidSignals.length > 0) {
    addItem(
      {
        id: 'thyroid',
        title: 'Tiroid fonksiyon testlerinde referans dışı bulgu',
        system: 'Endokrin / tiroid',
        severity: 'moderate',
        markers: markerList(thyroidSignals),
        interpretation:
          'TSH, FT3 veya FT4 parametrelerinden en az biri referans aralığın dışında saptanmıştır. Tiroid fonksiyonları eksen halinde yorumlanmalıdır.',
        clinicalContext:
          'TSH tek başına değil, serbest hormon düzeyleri, ilaç kullanımı, biyotin/takviye öyküsü ve klinik belirtilerle birlikte değerlendirilmelidir.',
        suggestedDoctorAction:
          'Hekim tarafından tiroid semptomları ve ilaç/takviye öyküsüyle birlikte değerlendirilmesi, gerekirse tekrar test veya ek inceleme planlanması önerilir.',
      },
      thyroidSignals,
    );
  }

  const kidneySignals = abnormalWithin(lookup, ['KREATININ', 'GFR', 'BUN']);

  if (kidneySignals.length > 0) {
    addItem(
      {
        id: 'kidney',
        title: 'Böbrek fonksiyon parametrelerinde referans dışı bulgu',
        system: 'Böbrek fonksiyonu',
        severity: 'high',
        markers: markerList(kidneySignals),
        interpretation:
          'Kreatinin, BUN veya GFR parametrelerinde referans dışı değer saptanmıştır. Böbrek fonksiyonları hidrasyon, kas kütlesi ve klinik durumla birlikte değerlendirilmelidir.',
        clinicalContext:
          'Tek ölçüm akut/kronik ayrımı yapmaz. Önceki sonuçlar, idrar bulguları, tansiyon ve ilaç kullanımı önemlidir.',
        suggestedDoctorAction:
          'Hekim değerlendirmesi ve gerekirse böbrek fonksiyon testlerinin tekrarı, idrar analizi veya ek inceleme önerilir.',
      },
      kidneySignals,
    );
  }

  abnormal
    .filter((item) => !used.has(item.name))
    .forEach((item) => addItem(createGenericItem(item), [item]));

  return {
    abnormalCount: abnormal.length,
    lowCount: abnormal.filter((item) => item.status === 'low').length,
    highCount: abnormal.filter((item) => item.status === 'high').length,
    items,
    safetyNote:
      'Bu bölüm klinik karar destek amaçlı ön yorumdur; tanı, tedavi veya nihai karar yerine geçmez. Son değerlendirme hekim tarafından yapılmalıdır.',
  };
}
