import { useState } from 'react';
import { useLocation } from 'react-router-dom';

const LEGAL_ACK_KEY = 'medicore:legalWarningsAcknowledged:v1';

type HomeLocationState = {
  acknowledgementRequired?: boolean;
};

function readAcknowledged() {
  try {
    return localStorage.getItem(LEGAL_ACK_KEY) === 'true';
  } catch {
    return false;
  }
}

export default function HomePage() {
  const location = useLocation();
  const state = location.state as HomeLocationState | null;
  const [acknowledged, setAcknowledged] = useState(readAcknowledged);

  function acknowledgeWarnings() {
    try {
      localStorage.setItem(LEGAL_ACK_KEY, 'true');
    } catch {
      // The acknowledgement still updates for this page if storage is unavailable.
    }
    setAcknowledged(true);
  }

  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
          MediCore AI
        </p>
        <p className="mt-4 max-w-3xl text-lg font-medium leading-8 text-slate-800">
          Burada şikayetleriniz, muayene bulgularınız, öz ve aile geçmişiniz, kullandığınız ilaçlar ile laboratuvar, radyolojik ve diğer tetkiklerinizin eş zamanlı değerlendirilmesi amaçlanmıştır.
        </p>
        <p className="mt-4 max-w-3xl text-base leading-7 text-slate-600 lg:hidden">
          İşleme başlamak için aşağıdaki ilgili bölüme tıklayın.
        </p>
        <p className="mt-4 hidden max-w-3xl text-base leading-7 text-slate-600 lg:block">
          İşleme başlamak için soldaki ilgili bölüme tıklayın.
        </p>
      </header>

      {state?.acknowledgementRequired && !acknowledged ? (
        <div className="rounded-xl border border-amber-300 bg-amber-100 px-5 py-4 text-sm font-semibold text-amber-950">
          Klinik bölümlerde işlem yapabilmek için önce aşağıdaki önemli uyarıları okuyup “Okudum ve anladım” düğmesine basmanız gerekir.
        </div>
      ) : null}

      <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <h2 className="text-base font-semibold text-amber-950">Önemli Uyarılar</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-amber-900">
          <li>
            MediCore AI bir değerlendirme ve Klinik Karar Destek Sistemidir (KKDS); kesin tanı veya tedavi kararı vermez.
          </li>
          <li>
            Sistem çıktıları hatalı veya eksik olabilir ve hekim değerlendirmesinin yerine geçmez.
          </li>
          <li>
            Röntgen ve ultrason görüntülerinde sunulan AI (DL/ML) ön değerlendirmesi deneyseldir; resmi radyoloji raporu veya hekim/radyolog değerlendirmesinin yerine geçmez.
          </li>
          <li>
            Verileri yüklerken isim, soyisim, T.C. kimlik numarası ve benzeri doğrudan kişisel tanımlayıcıları içermeyecek şekilde yükleyiniz.
          </li>
          <li>Doktorunuza danışmadan ilaç başlamayın, bırakmayın veya doz değiştirmeyin.</li>
          <li>Yalnızca sistem çıktısına dayanarak tetkik veya tıbbi işlem kararı almayın.</li>
          <li>Acil veya ciddi bir sağlık sorunu şüphesinde doğrudan uygun sağlık kuruluşuna başvurun.</li>
        </ul>

        <button
          type="button"
          onClick={acknowledgeWarnings}
          disabled={acknowledged}
          className={`mt-5 rounded-lg px-5 py-2.5 text-sm font-semibold transition ${
            acknowledged
              ? 'cursor-default bg-emerald-100 text-emerald-800'
              : 'bg-amber-900 text-white hover:bg-amber-950'
          }`}
        >
          {acknowledged ? '✓ Okudum ve anladım' : 'Okudum ve anladım'}
        </button>
      </section>
    </div>
  );
}
