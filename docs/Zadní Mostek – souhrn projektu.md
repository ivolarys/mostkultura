---
tags: [projekt, mostkultura, home-assistant, python]
stav: běží
web: https://ivolarys.github.io/mostkultura/
repo: https://github.com/ivolarys/mostkultura
aktualizováno: 2026-09-12
---

# Zadní Mostek · střed vesmíru

Denní agregátor kulturních akcí kolem Mostku. Každé ráno GitHub Actions stáhne akce z ~27 webů, sloučí duplicity, doplní kategorii a polohu a vygeneruje statický web (seznam + mapa) a JSON pro Home Assistant. Vtip: Zadní Mostek je střed vesmíru, okolní města jsou planety.

## Kde co je

| Co | Kde |
|---|---|
| Veřejný web | https://ivolarys.github.io/mostkultura/ (mapa: `?view=map`, kompaktně pro HA: `?embed=1&tab=week`) |
| Zdroje podle obce | https://ivolarys.github.io/mostkultura/zdroje.html |
| JSON pro HA | `…/summary.json` (počty + top 10 na bucket), `…/events.json` (vše), `…/status.json` (stav zdrojů) |
| Repo | github.com/ivolarys/mostkultura, lokálně `~/_projects/mostek-kultura` |
| Běhy CI | github.com/ivolarys/mostkultura/actions (cron 04:30 UTC, tj. 6:30 léto / 5:30 zima) |
| HA konfigurace | `ha/configuration.yaml` (REST senzory), `ha/lovelace-card.yaml` (iframe), `ha/lovelace-markdown-card.yaml` |
| Pravidla pro Claude | `CLAUDE.md` (česky; sekce „Poznatky“ = hard-won detaily o každém webu) |
| Plán z návrhu | `~/.claude/plans/cht-l-bych-ud-lat-aplikaci-validated-quasar.md` |

## Jak to funguje (pipeline)

1. `config.yaml` – jediné místo, kde se rozšiřuje rozsah: `places` (whitelist obcí + aliasy), `sources` (zdroje: `type`, `url`, `place`, `priority`), `categories`, `category_map`.
2. `mostek_kultura/sources/*` – jeden modul na typ zdroje (CMS rodina nebo konkrétní web). Registr v `sources/__init__.py`.
3. `normalize.py` – přiřazení obce (venue → place_raw → název → výchozí obec zdroje), filtr rozsahu, sloučení duplicit napříč zdroji (datum + normalizovaný název + obec, vyšší `priority` vyhrává).
4. `classify.py` – kategorie: nativní kategorie zdroje → LLM (OpenAI `gpt-6-luna`, případně Anthropic) → klíčová slova. Výsledky v `cache/classifications.json` (commitované, každá akce jen jednou).
5. `geocode.py` – poloha přes Nominatim (OSM), cache `cache/geocode.json`. Přesnost `venue` / `place` (střed obce).
6. `render.py` + `templates/` – `index.html` (data inline), `zdroje.html`, JSONy, `manifest.webmanifest`, `icon.svg`, přibalený Leaflet.
7. `.github/workflows/build.yml` – testy → build → commit `cache/` zpět (`[skip ci]`) → deploy na Pages.

## Provoz a údržba

- **Lokálně**: `uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -e .[dev]`, pak `.venv/bin/pytest -q`, `.venv/bin/python -m mostek_kultura build --offline --no-llm` (z fixtures, bez sítě), naživo `build` (klíč `OPENAI_API_KEY` pro klasifikaci). Náhled: `python -m http.server -d site 8765 --bind 0.0.0.0` a otevřít přes Tailscale IP homeboxu.
- **Přidat obec**: položka v `places` (název + aliasy, jak se místo objevuje v textech).
- **Přidat zdroj existujícího typu**: jen záznam v `sources`, pak `build --record --source <name> --no-llm` nahraje fixture pro testy.
- **Nový typ zdroje**: modul v `sources/`, registrace, fixture, test v `tests/test_sources.py`.
- **Akce z Facebooku** (nejde stahovat): ručně do `manual_events.yaml`, další build je zobrazí.
- **Ruční oprava kategorie**: editovat `cache/classifications.json`.
- **Secrets v repu**: `OPENAI_API_KEY` (nastaveno). Volitelné proměnné `OPENAI_MODEL`, `LLM_PROVIDER`.
- **Testy jsou zmrazené na 11. 9. 2026** (`MOSTEK_NOW` v `tests/conftest.py`), fixtures se hledají i podle normalizované URL, takže CI nepadá s časem.

## Známé věci a rozhodnutí

- mestovrchlabi.cz a klasterhostinne.cz (hosting Wedos) jsou z GitHub runnerů občas nedostupné → použijí se záložní data z `cache/last_good/`. Rozhodnuto nechat být (bez timeru na homeboxu ani self-hosted runneru).
- Městský kalendář Jičína (mujicin.cz) je mrtvý od 2022, Jičín plní jen GoOut. Galerie plastik Hořice má prázdný kalendář. Muzeum Hořice nemá dopředný program (vynecháno).
- GoOut API ignoruje geo filtry, jde přes hledání venue podle města + `venueIds[]`; limit 48.
- Kina (Vrchlabí, UFFO, Biograf Hořice) dávají hodně položek, filtruje se chipem „Film“; UFFO má `max_events`.
- Preference: kódování delegovat na levnější modely (Sonnet/Haiku), Fable jen návrh a review.

## Nápady do budoucna

- Kudy z nudy (JSON-LD na detailech), Hankův dům a Kino Svět DK (bespoke parsery), ZOO Dvůr Králové, Public4u hkregion.cz (jiná šablona).
- Notifikace z HA (ranní přehled z `sensor.kultura_dnes`).
- Ikona `apple-touch-icon` jako PNG (iOS neumí SVG ikonu na ploše).
