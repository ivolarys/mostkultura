# Pravidla pro Codex v tomto projektu

Komunikuj česky. Respektuj projektové postupy a technické poznatky v `CLAUDE.md`;
následující volba modelů má přednost před jeho staršími pokyny k modelům.

## Modely (preference uživatele, 2026-09-23)

- Hlavní model je GPT-6 Astra (`gpt-6-astra`): navrhuje, analyzuje, připravuje
  zadání, řídí práci, kontroluje, testuje a provádí UX/UI i code review.
- Samotné kódování deleguj levnějším modelům: GPT-6 Luna (`gpt-6-luna`) pro jednoduché
  úpravy, GPT-6 Sol (`gpt-6-sol`) pro složitější implementaci. Astra připraví
  konkrétní zadání a výsledek zkontroluje a ověří.
- Pro agenty používej pouze rodinu GPT-6. Pokud preferovaný model není dostupný,
  zvol jiný dostupný model GPT-6 odpovídající úloze; nepřecházej automaticky na starší generace.
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
  2026-09-12). Ovládání ručního seskupení ve filtru je odstraněné; staré
  nastavení `group` v URL zůstává podporované.
- V kategorii zobraz běžné akce nejdřív a několikadenní právě probíhající akce
  až v oddělené, výchozím způsobem rozbalené podsekci.
- Odkaz „Zdroje“ patří vedle vyhledávání.
- Kategorie se posouvají vodorovně a vybraná kategorie zůstává přímo v liště.
- Horní štítky kategorií jsou řazené abecedně podle českých popisků; ve
  seskupeném seznamu zůstává konfigurované pořadí a Sport je vždy poslední.
- V hlavičce jsou na širších displejích metadata vpravo ve stejné řádce jako značka; na úzkých displejích jsou pod značkou.
- Respektuj safe area nahoře i po stranách; sticky prvky musí zohlednit horní inset.
- Oddělení několikadenních akcí používá tenký cikcak se středovým textem a kompaktní mezery.
- Souhrn období zobrazuje datum před počtem; přepínač seznam/mapa používá pouze ikony.
- Stav zdrojů je kompaktní odznak u odkazu „Zdroje“ vedle vyhledávání; uvádí počet vybraných zdrojů z dostupných. Popisek uvádí i zdraví vybraných zdrojů a jantarové zvýraznění se použije, jen pokud má vybraný zdroj záložní data nebo chybu.
- Výchozí období filtrů je „Dnes“ a výchozí kategorie „Vše“.
- Spodní lišta má na všech běžných šířkách čtyři korálové ikonové volby Dnes/Zítra/Pá–Ne/Datum a vedle nich vizuálně oddělenou volbu Oblíbené. Pá–Ne zahrnuje pátek až neděli. Datum otevírá nativní dialog „Vybrat dny“ pro jeden den i souvislý rozsah; vlastní rozsah ukládej jako `tab=date&date=YYYY-MM-DD&end=YYYY-MM-DD`, oba konce vždy zpracovávej jako ISO den bez posunu časovým pásmem a při obráceném pořadí je normalizuj. Staré odkazy `tab=week` a `tab=all` zachovej. (Upřesnění 2026-09-21.)
- Každá akce má samostatné ovládání hvězdičkou pro přidání či odebrání z Oblíbených. Oblíbené se ukládají místně v daném prohlížeči a mezi zařízeními se nesynchronizují. Seznam Oblíbených řaď chronologicky a ignoruj v něm filtry data, zdroje, kategorie a hledání. Zobrazuj pouze aktuálně dostupné akce, které ještě nezačaly nebo neskončily: akce s uvedeným koncem zůstává dostupná až do konce, celodenní akce po celý den a akce bez konce přestává být dostupná po začátku. Ukládej identifikátor akce a termín, ne archivní kopii či snímek. Pokud akce ze zdroje zmizí, nezobrazuj ji, ale její uložený identifikátor ponech pro případ, že se vrátí.
- Značka je výraznější; aktualizace a počet akcí se v hlavičce nikdy nezalamují.
- Hlavička má být kompaktní: Mostkultura a „Kultura okolo Mostku“ vlevo a metadata vpravo ve stejné řádce na širších displejích; na úzkých displejích jsou metadata pod značkou.
  Nevracej „Kam vyrazíme?“ ani původní slogan. U akcí bez
  barevné svislé čárky; zdroj na desktopu napravo od štítku kategorie.
- Města a místa se vybírají přes Zdroje; po vypnutí města odstraň jeho výběr
  z aktivních filtrů.
- Karty akcí jsou kompaktní: obrázek nebo tónovaná ikona kategorie je vlevo,
  zarovnaná s názvem; název má nejvýše dva řádky a pod ním je
  jednořádkové místo. Dole je jednotně sázený termín (datum před časem,
  13 px, tučný řez (700), tabulkové číslice a výraznější barvu textu) a vpravo
  vedle sebe samostatná tlačítka
  Oblíbené a Sdílet, každé s dotykovou plochou alespoň 44 × 44 px. Karty mají
  zaoblení 12 px a náhledy 8 px. Termín se
  může zalomit mezi celými částmi, ale nesmí oříznout datum ani osamostatnit
  oddělovací tečku. V denním výpisu stačí čas nebo „Celý den“; právě probíhající
  akce uvádějí konec. Štítek kategorie nezdvojuj v seznamu seskupeném podle
  kategorií, ale zachovej jej v denním výpisu, Oblíbených a mapovém detailu.
  Na mobilu je termín s akcemi ve spodním řádku karty; na desktopu jsou vpravo
  vedle hlavního obsahu. Zdroj zůstává v metadatech na desktopu. Mapový dialog
  i kompaktní iframe zachovávají mobilní rozložení; v iframe se obrázek vynechává.

## Sdílení náhledů

- Pro náhledy dostupné z notebooku preferuj ověřenou Tailscale adresu.
- Zachovej existující Tailscale routy a zpřístupni jen zamýšlený náhled.
