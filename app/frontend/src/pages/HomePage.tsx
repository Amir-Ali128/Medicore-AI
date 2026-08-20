export default function HomePage() {
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

      <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <h2 className="text-base font-semibold text-amber-950">Önemli Uyarılar</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm leading-7 text-amber-900">
          <li>MediCore AI bir klinik karar destek sistemidir; kesin tanı veya tedavi kararı vermez.</li>
          <li>Sistem çıktıları hatalı veya eksik olabilir ve hekim değerlendirmesinin yerine geçmez.</li>
          <li>Doktorunuza danışmadan ilaç başlamayın, bırakmayın veya doz değiştirmeyin.</li>
          <li>Yalnızca sistem çıktısına dayanarak tetkik veya tıbbi işlem kararı almayın.</li>
          <li>Acil veya ciddi bir sağlık sorunu şüphesinde doğrudan uygun sağlık kuruluşuna başvurun.</li>
        </ul>
      </section>
    </div>
  );
}
