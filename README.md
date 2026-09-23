# Mostkultura

Mostkultura je denní přehled kulturních a společenských akcí v okolí obce Mostek (okres Trutnov): dnes, zítra, víkend i celý týden. Akce jsou členěné podle typu a obce a k dispozici jsou také na mapě.

- Veřejná stránka: **https://ivolarys.github.io/mostkultura/**
- JSON pro Home Assistant: `https://ivolarys.github.io/mostkultura/summary.json`
- Kompaktní režim pro iframe: `?embed=1&tab=week`
- Zdroje podle obce: `https://ivolarys.github.io/mostkultura/zdroje.html`

## Jak to funguje

1. GitHub Actions každý den ráno stáhne akce ze zdrojů v `config.yaml` (obecní weby, kalendář Lázní Bělohrad, GoOut).
2. Akce se namapují na obce z whitelistu, sloučí se duplicity napříč zdroji a doplní se kategorie (nativní kategorie zdroje → LLM → klíčová slova). LLM je OpenAI (`gpt-6-luna`) nebo Anthropic (Claude Haiku) podle toho, který klíč je nastavený.
3. Vygeneruje se statický web (`site/`) a nasadí se na GitHub Pages. Klasifikace se ukládá do `cache/` v repu, takže se každá akce klasifikuje jen jednou.

Když nějaký zdroj spadne, použijí se jeho data z posledního úspěšného běhu (`cache/last_good/`), stav je vidět v hlavičce stránky a v `status.json`.

Hlavní automatický běh je naplánovaný na 04:30 UTC. Protože GitHub negarantuje přesný čas spuštění plánovaných workflow a může je zpozdit nebo vynechat, následují záložní pokusy v 05:17, 07:17 a 10:17 UTC (v českém letním čase 07:17, 09:17 a 12:17; v zimním 06:17, 08:17 a 11:17). Každý plánovaný pokus nejdřív ověří veřejné `status.json` a přeskočí se pouze tehdy, když už byl publikován úspěšný build od poslední hranice 04:30 UTC. Push a ruční spuštění tuto kontrolu nepoužívají a sestavení provedou vždy.

Na stránce **Zdroje** lze v každém prohlížeči samostatně skrýt celé obce i jednotlivé zdroje. Volba se ukládá jen lokálně do prohlížeče; neovlivní společná data ani Home Assistant.

Základní hradecký výběr tvoří Bio Central, CineStar, Klicperovo divadlo,
Divadlo DRAK, Náplavku, Nábleší a saunu NUUK. Kina, divadla a Náplavka
se načítají z vlastních programů; Nábleší a NUUK z městského kalendáře HKinfo
filtrovaného podle názvu nebo místa. Různé časy projekcí a různá kina zůstávají
samostatnými akcemi. Divadelní zájezdy, uzavřená a školní představení se vynechávají.
Podzimní snění načítá z aktuální homepage jeden vícedenní festivalový záznam.
Společenský dům Jilm v Jilemnici bere aktuální stránkovaný program včetně odkazů, obrázků,
popisů a kategorií; Kino 70 je součástí téhož programu, nikoli samostatný zdroj.
Výchozí zapnuté zdroje pokrývají také program kina Biograf Český ráj v Jičíně
a kulturní program Klubu Kus v Turnově.
Zapnuté jsou také Hrad Pecka, Spolek Bezdružic a Pouťová Pecka pod obcí Pecka.

Výběr „Další kultura v Hradci – HKinfo“ doplňuje zveřejněné akce PETROF Gallery,
filharmonie, Galerie moderního umění, Muzea východních Čech, hvězdárny a planetária,
Galerie Artičok, AC klubu a Adalbertina. Zrušené akce a běžné lekce tanečních kurzů
se do tohoto výběru nezařazují. Nabídka se aktualizuje při každém denním stažení.

Bajkazyl HK má samostatný zdroj z veřejného datového rozhraní svého programu
`bajkazylhk.cz/akce`. Načítají se začátky i konce akcí, popisy a dostupné obrázky.
Časy v UTC se převádějí na český čas; staré akce vyřazuje společný časový filtr.

## Lokální spuštění

```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -e .[dev]
.venv/bin/pytest -q
.venv/bin/python -m mostek_kultura build --offline --no-llm   # z fixtures, bez sítě
.venv/bin/python -m mostek_kultura build                      # naživo; OPENAI_API_KEY nebo ANTHROPIC_API_KEY pro klasifikaci
python -m http.server -d site 8000                            # http://localhost:8000/?embed=1
```

## Jak přidat obec nebo zdroj

- **Obec / venue:** přidej položku do `places` (název + aliasy, jak se místo objevuje v textech) nebo do `venues_allow` (konkrétní místo bez ohledu na obec).
- **Zdroj existujícího typu** (`galileo`, `antee_rss`, `public4u`, `goout`, `drupal_events`, `lodzie_program`, `npu_events`, `josefa_events`, `vismo`, `vismo6`, `kultura_novapaka`, `uffo`, `sd_jilm`, `mojekino`, `epo1_calendar`, `epo1_exhibitions`, `webnode_program`, `koruna_program`, `simcal_calendar`, `klaster_hostinne`, `trut_program`, `podzimni_sneni`, `manual`): přidej záznam do `sources` s `url`, `place` (výchozí obec) a `priority`. Pak `build --record --source <name> --no-llm` nahraje fixture pro testy (u `manual` fixture není potřeba, čte se přímo `manual_events.yaml`).
- **Nový typ zdroje:** modul v `mostek_kultura/sources/` s třídou odvozenou od `Source` (metoda `fetch(http) -> list[Event]`), registrace v `sources/__init__.py`, fixture a test v `tests/test_sources.py`.

## Ruční akce (Facebook apod.)

Akce, které se propagují jen přes Facebook (nedají se automaticky stahovat), se doplňují ručně do `manual_events.yaml` v kořeni repa – formát a příklad položky jsou v komentáři na začátku souboru. Po commitu a pushi je vyzvedne nejbližší denní build (zdroj `rucne`, typ `manual`), není potřeba nic dalšího spouštět.

## Mapa

Přepínač „Seznam / Mapa“ nad výpisem zobrazí stejné (filtrované) akce na mapě okolí Mostku (Leaflet, vendorovaný v `mostek_kultura/static/leaflet/`, žádná JS závislost stahovaná za běhu). Akce se geokódují při buildu (`mostek_kultura/geocode.py`) na úroveň konkrétního místa konání (venue) nebo aspoň obce (centroid), výsledek se cachuje do `cache/geocode.json` (commitovaná, stejně jako `cache/classifications.json`) – při běžném denním buildu se tak dotazuje jen pár nových venue navíc, ne celá databáze znovu. Jediná externí síťová závislost za běhu stránky jsou dlaždice `tile.openstreetmap.org`; samotné vyhledávání (Nominatim) běží jen při buildu.

## Instalace na plochu

Při první návštěvě na telefonu se ukáže nenápadná nabídka přidání na plochu. Na iPhonu a iPadu vede na návod přes nabídku Sdílet, v Androidu použije nativní výběr instalace, když ho prohlížeč zpřístupní. Desktopovou nabídku zobrazí jen prohlížeč, který skutečně poskytne nativní instalaci. Stav první nabídky se ukládá lokálně v prohlížeči; v instalované aplikaci, iframe a nepodporovaných vestavěných prohlížečích se nezobrazuje.

## Home Assistant

- REST senzory: `ha/configuration.yaml` (stav = počet akcí, atribut `events` = seznam).
- Iframe karta: `ha/lovelace-card.yaml`. Markdown karta bez iframe: `ha/lovelace-markdown-card.yaml`.

Senzory se obnovují každou hodinu, data na Pages jednou denně ráno. Stránka sama počítá „dnes/zítra“ z aktuálního času v prohlížeči, takže je správně i po půlnoci.

## Nasazení

```bash
gh repo create ivolarys/mostkultura --public --source . --push
gh secret set OPENAI_API_KEY        # nebo ANTHROPIC_API_KEY; oba = přednost má OpenAI, přepíná LLM_PROVIDER
# Settings → Pages → Source: GitHub Actions
gh workflow run build.yml && gh run watch
```
