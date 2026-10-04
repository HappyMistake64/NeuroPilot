# NeuroPilot — audit zdrojového kódu a návrh dalšího vývoje

Datum: 3. října 2026. Vstup: `Neuropilot 3.zip`. Opravená verze: **3.1.0**.

## Výsledek

Původní projekt obsahuje dvě nespojené aplikace: Flask osobní plánovač a Python/Gradio AI aplikaci omylem uloženou jako `public/app.js`. V prohlížeči proto nefungují tlačítka. Lokální agent je soustava pravidlových funkcí, ne trénovaný jazykový model. Dokumentace o autonomním programování a plné funkčnosti byla nepřiměřená skutečné implementaci.

Opravená verze zachovává obě větve, rozděluje jejich vstupní soubory, opravuje ukládání a příkazy agenta, doplňuje funkční webové ovládání, dokončování a mazání úkolů a přidává testy. Základní plánovač lze používat bez stahování modelu.

## Co skutečně obsahoval původní projekt

| Oblast | Skutečná původní schopnost | Stav po opravě |
|---|---|---|
| Flask web | HTML formuláře a API; skript prohlížeče nebyl JavaScript | Funkční události rozhraní, stavové a chybové zprávy |
| Poznámky | Text zadání + odpověď ukládaná do JSON | Ukládání a mazání, bezpečné vykreslení jako text |
| Úkoly | Vytváření a seznam | Navíc dokončení, znovuotevření a smazání |
| Návyky | Vytváření a denní záznamy; statistiky padaly | Denní přepínač a součet za 7 dní, validace dat a rozsahu |
| Zálohy | API import/export s neúplnou validací | Ověřený roundtrip, stará číselná ID, nedestruktivní odmítnutí chybného importu |
| Lokální agent | Generické věty z klíčových slov, číselné preference | 15 registrovaných modulů, funkční příkazy, zachování pracovního stavu |
| Identita | Ruční JSON save/load, část stavu se ztrácela | Atomické save/load, konfigurace paměti a další pole zachována |
| Web lokálního agenta | Omezené načítání arXiv; konfigurace se nepředávala | Explicitní volitelné zapnutí, whitelist, limity, kontrola přesměrování |
| Gradio | Kód existoval, ale byl v `.js`, chyběl `app.py` | Samostatný `app.py`, import bez modelových downloadů a bez spuštění serveru |
| Modelový chat | Pokus o generování přes `distilgpt2`; chyby skryté jako nedostupnost | Explicitně nastavený model, řízená inicializace a limit kontextu |
| „Autonomie“ | Plán a další texty modelu; žádné skutečné provedení práce | Přesně označené textové návrhy kroků, validace 1–8 |
| Projekty ZIP | Parsování bloků textu modelu, bez bezpečných cest a ověření obsahu | Kontrola cest, jmen, duplicit a velikosti; žádný falešný „Empty project“ |
| Sebezlepšování | Změna několika čísel a nastavení | Zachováno jako experimentální preference, nikoliv trénování modelu |
| Obrázky | Placeholder | Explicitní oznámení, že analýza obrázků není implementována |

## Nalezené problémy a opravy

Závažnost je vztažena k této lokální aplikaci. Některé pády byly reprodukovány; další závěry vyplývají přímo z kontroly zdrojového kódu.

| # | Závažnost | Problém v původní verzi | Oprava / důsledek |
|---|---|---|---|
| 1 | Kritická funkční | `public/app.js` obsahuje Python, Gradio a `demo.launch()` | Python přesunut do samostatné větve; skutečný JS obsluhuje web |
| 2 | Vysoká | V `requirements.txt` chybí Flask, přesto je to serverová závislost | Lehká základní instalace; modelové a vývojové závislosti odděleny |
| 3 | Vysoká | Konfigurace ukazuje na neexistující `app.py`, README popisuje jiný běh | Opraven vstupní soubor a dokumentace; odstraněna zavádějící metadata |
| 4 | Vysoká | `habit_stats` volá nenaimportovaný `timedelta` | Reprodukován `NameError`; endpoint nyní pokryt testem |
| 5 | Vysoká | Export používá zastaralý `attachment_filename` a relativní adresář | JSON odpověď se správným download headerem, nezávislá na cwd |
| 6 | Vysoká | `data.json`, statické soubory a další stavy závisejí na pracovním adresáři | Cesty ukotveny k projektu, explicitní cesta dat pro testy |
| 7 | Vysoká | JSON soubory se přepisují přímo, souběžné read/modify/write ztrácí změny | Sdílený `JsonStore`: zámek, dočasný soubor, fsync, atomická výměna |
| 8 | Střední | ID podle milisekund se mohou opakovat | UUID pro nové záznamy, zachována stará číselná ID |
| 9 | Vysoká | Import přijímá vadné záznamy a nemusí obsahovat `habits` | Validace kolekcí, typů, ID, dat návyků a boolean stavu úkolu |
| 10 | Vysoká | API volá `.strip()` i na netextové hodnotě; rozsahy a data nejsou kontrolovány | Jednotné chyby 400, limit požadavku i délky textu |
| 11 | Vysoká | Jeden neúspěšný import add-onů přeskočí další; chyby registrace se polykají | Explicitní jednotlivá registrace bez tichého maskování závad |
| 12 | Střední | `goal_gen.py` není registrován | Zaregistrován; kompatibilní zápis f-stringu i pro Python před 3.12 |
| 13 | Vysoká | `web_cfg`, `wm_cfg` a `cons_cfg` se nepředávají z konfigurace | Předání do stavu agenta |
| 14 | Vysoká | Pracovní paměť, její konfigurace a sociální paměť mizí po odpovědi | Uchování všech potřebných polí; samostatné pracovní kopie |
| 15 | Vysoká | `candidate_reply` vždy přebije odpověď příkazu `:save_all`, `fb`, `:self` atd. | Příkazová odpověď má přednost |
| 16 | Střední | `:load_all` neobnovuje kulturu, kontext a další pole; otevřené soubory bez context manageru | Plnější save/load, kompatibilita starých názvů `wm`/`culture` |
| 17 | Vysoká | `chat_wrapper.chat` po nové inicializaci vždy vrátí fallback, další větev je nedosažitelná | Jedna líná inicializace pod zámkem a jedno sériové pracovní vlákno |
| 18 | Střední | Opožděné výsledky po timeoutu zůstávají v `_res_map`; fronta není omezená | Future místo mapy, omezená fronta, zrušení čekajícího požadavku |
| 19 | Střední | Chybový fallback serveru odkazuje na proměnnou výjimky `e`, která po `except` zaniká | Odstraněno tiché maskování importu; přímý import a řízené chyby workeru |
| 20 | Střední | Řetězce používají různé Unicode normalizace; regexy mají navíc zpětná lomítka | NFC pro zadání; opraveno dělení vět a čištění HTML |
| 21 | Vysoká | `:read` umožňuje absolutní cestu a `../`, navíc mění velikost písmen cesty | Resolved cesta musí být uvnitř projektu včetně symlinků; zachována velikost písmen |
| 22 | Vysoká | Webový whitelist používá suffix bez hranice domény; přesměrování a interní adresy nejsou kontrolovány | Celá doména/subdoména, veřejné IP, schéma, porty, credentials a přesměrování ověřovány |
| 23 | Kritická při modelovém generování | Název ZIP a cesty souborů mohou uniknout mimo pracovní adresář | Validace jména a relativních cest; ZIP vzniká přímo bez rozbalování modelových cest |
| 24 | Vysoká | Neplatný výstup modelu je vydán jako falešný prázdný projekt; kolize ZIP názvů | Chyba místo neplatného projektu, unikátní názvy, limit počtu a velikosti souborů |
| 25 | Vysoká | Model se stahuje při importu a Gradio se automaticky spouští | Model až při první skutečné generaci; UI pouze v main guardu |
| 26 | Vysoká | `max_length` zahrnuje i dlouhý prompt; odpověď může padat ještě před generováním | `max_new_tokens`, rezervace kontextu a obnovení nastavení tokenizeru |
| 27 | Střední | Počet kroků může být 0, obrovské číslo nebo jiný typ | Výslovná validace 1–8; prázdný plán je chyba |
| 28 | Střední | Model vygeneruje URL a plánovač ji automaticky načte | Síťové načtení jen v explicitní webové funkci |
| 29 | Vysoká při přístupu ze sítě | Měnící API bez kontroly původu; služba není určena pro veřejnost | Loopback, kontrola Host/Origin; nadále pouze osobní lokální režim |
| 30 | Střední | Dokumentace zaměňuje textovou simulaci, čísla preferencí a placeholdery za plnou AI/autonomii | Pravdivý popis implementace a otevřených částí |

## Přehled kontroly všech původních zdrojů

| Soubor / modul | Posouzená role a výsledek |
|---|---|
| `server.py` | Všechny routy, validace, cwd, chybové stavy, ukládání, export/import; opraveno |
| `chat_wrapper.py` | Inicializace, závody, fronta, timeout a zpracování chyb; opraveno |
| `run_chat.py` | Konfigurace, importy a registrace, fallback, CLI; zpřehledněno |
| `agent_test.py` | Pouhé výpisy bez ověření, běh při importu; změněno na izolovaný smoke test |
| `public/index.html` | Základní formuláře; doplněny chybové stavy, zálohy a popisky |
| `public/app.js` | Špatný jazyk souboru; nahrazen funkčním JS |
| `core.py` | Modulový tok, priority odpovědí a životnost stavu; opraveno |
| `language_module.py` | Náhodně volené obecné šablony; zachováno a přiznáno jako pravidlový modul |
| `working_memory.py` | Vážený omezený seznam vstupů; potřeboval trvalý stav v core |
| `consolidation.py` | Jednoduché shrnutí textu a posun preferencí; opraven regex |
| `relevance_filter.py` | Heuristická relevance podle slov, extraktivní text; opraven regex |
| `internet_sensor.py` | Jedno téma, arXiv, limity; opraven whitelist, stavy a čtení webu |
| `internet_batch.py` | Dávkové varianty arXiv; stejné opravy, sdílené síťové funkce |
| `identity_persistence.py` | Ruční save/load; opraveno uchování polí a zápis |
| `other_self.py` | Evidence textů s prefixem `AI-1:`/`AI-2:`; není komunikací dvou agentů |
| `goal_gen.py` | Návrh jednoduchého cíle; původně se nespouštěl, nyní registrován |
| `feedback_learning.py` | Posun čísel; doplněna validace přesně -1/0/1 |
| `self_mod_module.py` | Změna tří čísel preferencí; odmítá NaN/nekonečno |
| `self_rewrite.py` | Změna dovolených parametrů; odmítá NaN/nekonečno; žádná změna kódu |
| `future_sim_module.py` | Výběr z tří předdefinovaných vět; není skutečným simulátorem následků |
| `metapref_module.py` | Statická poznámka podle konfigurace; bez samostatného učení |
| `sensors_module.py` | Čas, omezené čtení souboru a placeholder obrázku; opravené cesty |
| `config.json`, `requirements.txt`, `README.md` | Nesoulad s implementací, chybějící závislost, přehnaná tvrzení; nahrazeno |
| `data.json`, `agent_error.log` | Data prázdná; log ukazuje inicializace, ne úspěšné end-to-end testy. Původní data zachována; historický log vynechán z nové distribuce |

## Ověření

- **46 pytest případů prošlo** na Pythonu 3.12: API, poznámky, dokončování úkolů, návyky, import/export, původní číselná ID, vadné požadavky, Host/Origin, současné zápisy 200 změn, ochrana poškozeného JSON před přepsáním, všech 15 modulů, paměť a příkazy, cesty senzorů, HTML/regex, URL/whitelist, ZIP, časový limit a kontext modelu.
- **Integrační test DOM proti skutečnému izolovanému Flask serveru prošel:** chat → poznámka, úkol → dokončení → export, návyk → statistika, import a smazání; žádné JS chyby. Vstup obsahující `<script>` zůstává textem. Je přiložen jako `tests/test_frontend.cjs`.
- Python soubory prošly kompilací a `public/app.js` kontrolou syntaxe Node.js.
- Volitelné Gradio rozhraní se sestavilo se 29 komponentami na Gradio 6.29.1; lokální HTTP smoke test vrátil **200**.
- Rozlišené omezení: test DOM není grafický test skutečného prohlížeče. Chromium se v testovacím prostředí nepodařilo stáhnout. Mobilní layout a Safari nejsou vizuálně potvrzeny.
- Inference modelu, kvalita češtiny, reálný webový výzkum přes veřejnou síť a kompatibilita Pythonisty/iOS nebyly ověřeny. Modelové nástroje jsou testovány s náhradními modelovými odpověďmi; neslibujeme tak jejich praktickou kvalitu.

## Co ještě není dokončeno

Není zde skutečný autonomní programátor, bezpečný terminálový runtime, testování vygenerovaných projektů, provádění úkolů, modelové učení z feedbacku, vektorový retrieval, uživatelské účty nebo synchronizace. Základní a modelová větev mají stále oddělené paměti. Ruční `:save_all`/`:load_all` není automatická obnova konverzací. Paměť preferencí ani údaje o dalších „AI“ nedokládají vědomí nebo spolupracující agenty.

## Navržená roadmapa

Doporučuji NeuroPilot nejdřív rozvinout do kvalitního **osobního asistenta pro plánování a vedení projektů**. Hotové poznámky, úkoly a návyky tuto roli podporují. Přechod k autonomnímu programování by potřeboval zcela nový runtime a výrazně širší testování.

| Verze | Konkrétní rozsah | Podmínka dokončení |
|---|---|---|
| 3.2 — jednotná aplikace | Jedno UI, jedna SQLite databáze, sdílená historie, migrace JSON, filtrace a editace úkolů | Staré zálohy migrují bez ztráty dat; celý průchod funguje v Safari/iPhone a na desktopu |
| 3.3 — skutečný modelový asistent | Jasně volitelný lokální nebo API provider, stav dostupnosti, streamování, měřený kontext a paměť | Na cílovém 8GB zařízení změřit RAM/latenci; sada českých zadání a jasné chyby nedostupnosti |
| 3.4 — projekty a plánování | Cíl → návrh úkolů → uživatelské přijetí → evidence postupu, termíny a vazby | Asistent skutečně vytvoří schválené úkoly; návrh nezamění s provedením |
| 3.5 — výzkum s důkazy | Zdroje, citace, datum načtení, přehled studií, kontrolovaná fronta | Každé důležité tvrzení má ověřitelný zdroj; síťové a chybové scénáře mají integrační testy |
| 3.6 — generátor ověřených projektů | Nejprve vymezený HTML/CSS/JS profil, validace souborů, build a kontrola v sandboxu | ZIP má spuštěný build a alespoň jeden funkční průchod; neúspěch je jasně označen |
| 4.0 — řízené akce | Omezené nástroje, schvalování, pracovní kopie, testy, rollback, audit akcí | Jedna konkrétní podporovaná úloha projde změnou → testem → kontrolou → vratným výsledkem |

Pořadí drží současný projekt pohromadě: nejdřív data a uživatelský průchod, potom skutečný model, teprve následně provádění akcí. Pro nejbližší verzi nedoporučuji přidávat další osobnostní moduly bez měřitelného užitku.
