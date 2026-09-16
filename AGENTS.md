# Pravidla pro Codex v tomto projektu

Komunikuj česky. Respektuj projektové postupy a technické poznatky v `CLAUDE.md`;
následující volba modelů má přednost před jeho staršími pokyny k modelům.

## Modely (preference uživatele, 2026-09-12)

- Hlavní model je GPT-6 Astra (`gpt-6-astra`): navrhuje, analyzuje, připravuje
  zadání, řídí práci, kontroluje, testuje a provádí UX/UI i code review.
- Samotné kódování deleguj levnějším modelům: GPT-5.6 Luna pro jednoduché
  úpravy, GPT-5.6 Terra nebo Sol pro složitější implementaci. Astra připraví
  konkrétní zadání a výsledek zkontroluje a ověří.
- Preference platí pro celý tento projekt všude, kde lze model zvolit.
  Netvrď, že se model běžícího tahu přepnul, pokud se to skutečně nestalo.

## UX/UI

- Nabídku přidání aplikace ukaž jen jednou na prohlížeč; nezobrazuj ji v iframe ani v samostatně spuštěné aplikaci. Na desktopu ji nabízej jen po skutečném nativním instalačním eventu prohlížeče.
- Schválená značka (2026-09-12): **Mostkultura**. Repo a veřejná URL používají
  název `mostkultura` (`https://ivolarys.github.io/mostkultura/`). Logo propojuje malé m,
  mostní oblouky a čtyřcípou jiskru;
  hlavní barva je korálová. Zachovej název repozitáře a existující URL.
- Web navrhuj primárně pro mobilní telefony, ve svěžím moderním stylu
  inspirovaném iOS. Zachovej přístupnost, tmavý režim a kompaktní iframe režim.
- Používej jednotné jednoduché obrysové ikony a dostatečně velké dotykové prvky.
- Výchozí seskupení akcí je podle **kategorie** (preference uživatele,
  2026-09-12). Zachovej možnost ručního seskupení podle dne a nastavení v URL.
- V kategorii zobraz běžné akce nejdřív a několikadenní právě probíhající akce
  až v oddělené, výchozím způsobem rozbalené podsekci.
- Odkaz „Zdroje“ patří do hlavičky.
- Kategorie se posouvají vodorovně a vybraná kategorie zůstává přímo v liště.
- Horní štítky kategorií jsou řazené abecedně podle českých popisků; ve
  seskupeném seznamu zůstává konfigurované pořadí a Sport je vždy poslední.
- V hlavičce jsou značka a odkaz „Zdroje“ na jednom horním řádku; metadata jsou jako menší druhý řádek pod nimi.
- Respektuj safe area nahoře i po stranách; sticky prvky musí zohlednit horní inset.
- Oddělení několikadenních akcí používá tenký cikcak se středovým textem a kompaktní mezery.
- Souhrn období zobrazuje datum před počtem; přepínač seznam/mapa používá pouze ikony.
- Stav zdrojů je kompaktní odznak vedle odkazu „Zdroje“ v hlavičce; uvádí počet vybraných zdrojů z dostupných. Popisek uvádí i zdraví vybraných zdrojů a jantarové zvýraznění se použije, jen pokud má vybraný zdroj záložní data nebo chybu.
- Výchozí období filtrů je „Dnes“ a výchozí kategorie „Vše“.
- Spodní lišta má na všech běžných šířkách čtyři korálové ikonové položky Dnes/Zítra/Víkend/Datum. Datum otevírá nativní dialog s kalendářem; vlastní den ukládej jako `tab=date&date=YYYY-MM-DD` a datum vždy zpracovávej jako ISO den bez posunu časovým pásmem. Staré odkazy `tab=week` a `tab=all` zachovej.
- Značka je výraznější; aktualizace a počet akcí se v hlavičce nikdy nezalamují.
- Hlavička má být kompaktní: Mostkultura a „Kultura okolo Mostku“ vlevo,
  „Zdroje“ vpravo na horním řádku a „Aktualizováno“ s počtem na druhém řádku.
  Nevracej „Kam vyrazíme?“ ani původní slogan. U akcí bez
  barevné svislé čárky; zdroj na desktopu napravo od štítku kategorie.
- V dialogu Filtry/Místa nezobrazuj města vypnutá na úrovni města; po jejich
  vypnutí odstraň jejich výběr z aktivních i rozpracovaných filtrů.

## Sdílení náhledů

- Pro náhledy dostupné z notebooku preferuj ověřenou Tailscale adresu.
- Zachovej existující Tailscale routy a zpřístupni jen zamýšlený náhled.
