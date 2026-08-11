export default function HomePage() {
  return (
    <div className="space-y-6">
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-cyan-700">
          Medicore AI
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-950">
          Klinik Değerlendirme ve Karar Destek Sistemi
        </h1>
        <p className="mt-3 max-w-4xl text-sm leading-7 text-slate-600">
          Bu sistem; bireyin veya hastanın cinsiyet, yaş ve kilo bilgileri ile
          kişisel ve ailesel hastalıklar, ameliyatlar ve kullanılan ilaçlar gibi öz
          geçmiş ve soy geçmiş bilgilerini; laboratuvar, radyoloji, endoskopi ve
          benzeri tetkik bulgularıyla birlikte yorumlayarak olası hastalıkların
          saptanması, bilinen hastalıkların gidişatının değerlendirilmesi ve uygun
          bir yol haritası oluşturulması hakkında bilgilendirme sağlamayı
          amaçlamaktadır.
        </p>
      </header>

      <section className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <h2 className="text-base font-semibold text-amber-950">
          Yasal bilgilendirme
        </h2>
        <p className="mt-2 text-sm leading-7 text-amber-900">
          Sistemde sunulan tüm değerlendirme ve öneriler yalnızca tavsiye ve
          bilgilendirme amaçlıdır. Doktorunuza danışmadan tetkik yaptırma, ilaç
          dozunu değiştirme, ilaç bırakma veya yeni bir ilaç kullanma gibi herhangi
          bir tıbbi eylemde bulunmayınız. Nihai değerlendirme ve tedavi kararı
          hekiminize aittir.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-semibold text-slate-950">Nasıl kullanacaksınız?</h2>

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-base font-semibold text-slate-950">
              A. İlk defa giriş yapanlar
            </h3>
            <ol className="mt-3 list-decimal space-y-3 pl-5 text-sm leading-7 text-slate-600">
              <li>Hasta bilgileri ekranından gerekli klinik bilgileri girin.</li>
              <li>
                Laboratuvar, radyoloji ve diğer bulgulara ait mevcut sonuçları
                ilgili bölümlere aktarın ve analizi başlatın.
              </li>
              <li>Analiz sonuçlarını, klinik yorumları ve önerileri inceleyin.</li>
            </ol>
          </article>

          <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-base font-semibold text-slate-950">
              B. Tekrar giriş yapanlar
            </h3>
            <p className="mt-3 text-sm leading-7 text-slate-600">
              Değişen klinik bilgileri ve yeni tetkik sonuçlarını ilgili alanlarda
              güncelledikten sonra analiz ve değerlendirme adımlarına devam edin.
            </p>
          </article>
        </div>
      </section>
    </div>
  );
}
