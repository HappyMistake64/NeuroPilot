# NeuroPilot 3.4.0 — experimentální RSI 0.3

Tato verze přidává implementaci částí RSI-0 až RSI-6 k původnímu plánovači. Umí řídit vlastní změny jednoho Python modulu agenta, měřit jejich výsledky, přijímat ověřené kandidáty a použít přijatou verzi v dalším experimentu.

**Stav ověření:** 202 automatických testů prošlo. Prošly také dva integrační testy DOM proti skutečnému Flask serveru. Modelová orchestrace a rekurzivní scénáře byly testovány výslovně označenými testovacími náhradami. Reálný model v tomto prostředí není nakonfigurován a systémové sandboxy zde nejsou funkční. Skutečná baseline schopností ani sebezdokonalení proto zatím změřeny nejsou. Produkční běh při chybějícím modelu nebo izolaci skončí stavem `blocked`.

## Rychlé spuštění na Fedoře / Linuxu

Pracuj v rozbalené složce projektu. Potřebuješ Python 3.10+, buď přihlášení ChatGPT podle `OPENAI_README.md`, nebo běžící lokální Ollamu s již staženým modelem; dále funkční Podman, Docker nebo Bubblewrap. RSI nepoužívá balíčky Torch/Transformers v Python prostředí aplikace; model obsluhuje Ollama nebo OpenAI.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m rsi init
python server.py
```

Otevři **http://127.0.0.1:5000/rsi**. Základní plánovač zůstává na **http://127.0.0.1:5000/**. Připravit laboratoř a prohlížet stav lze i bez modelu; skutečné experimenty vyžadují další nastavení.

## OpenAI přes předplatné ChatGPT

Na `/rsi` otevři **Continue with ChatGPT**, dokonči přihlášení na stejném počítači, načti modely a klikni **Použít pro RSI**. Tlačítko **Otestovat spojení · 1 dotaz** ověří inferenci bez spouštění kódu. Připojení má vlastní bezpečně uložené OAuth tokeny, nepoužívá API klíče. Podrobnosti, omezení tokenového rozpočtu a reprodukovatelnosti jsou v `OPENAI_README.md`.

## Nastavení lokálního modelu Ollama

Zjisti název již nainstalovaného modelu:

```bash
ollama list
```

Do následujícího příkazu vlož skutečný název modelu z tohoto výpisu:

```bash
python -m rsi config --set model=NAZEV_TVEHO_MODELU
```

Endpoint je výchozím nastavením `http://127.0.0.1:11434`. Pokud služba neběží, spusť Ollamu obvyklým způsobem, například `ollama serve`. Ollama zůstává výchozí variantou; připojení ChatGPT uživatel zapíná výslovně. Použitelnost konkrétního modelu pro JSON nástroje je nutné ověřit baseline během.

`doctor` ověřuje metadata modelu a sandbox. **Samotný úspěšný doctor ještě neznamená provedenou inferenci.** Skutečná modelová volání jsou zaznamenána v testu `provider-check`, baseline nebo kampani.

## Izolace

Nejsnazší varianta pro Fedora/Linux je již připravený Podman nebo Docker. Stáhni lokální obraz explicitně před prvním experimentem:

```bash
podman pull docker.io/library/python:3.12-slim
python -m rsi config --set sandbox=podman --set image=docker.io/library/python:3.12-slim
python -m rsi doctor
```

Docker alternativa:

```bash
docker pull python:3.12-slim
python -m rsi config --set sandbox=docker --set image=python:3.12-slim
python -m rsi doctor
```

Program samotný obrazy automaticky nestahuje. Pro běh připne ID konkrétního obrazu, vypne síť, nastaví read-only filesystem, neprivilegovaného uživatele, limit procesů, RAM, CPU, dočasného prostoru a času. SELinux bind mount se připravuje jen nad dočasnou pracovní kopií.

Bubblewrap alternativa vyžaduje `/usr/bin/python3`, povolené Linux namespaces a `libseccomp`. Filtr zakazuje vznik dalších procesů/vláken, sockety a čtení jiných procesů. Paměťový limit zde platí na proces; strategie i řešená úloha v tomto backendu musí být jednovláknové. Automatická volba zkusí Podman, Docker a Bubblewrap, ale použije jen variantu, která projde kontrolou izolace. Neexistuje přepínač pro tichý přechod na neizolovaný běh.

Tento runner je cílen na Linux. Nativní provoz RSI na Windows, macOS ani iOS nebyl implementován/ověřen; pro Windows je vhodné cílové Linux prostředí. Původní plánovač má vlastní postup v hlavním README.

## RSI-0: ověření úloh a baseline

```bash
python -m rsi reference-check
python -m rsi baseline --limit 10
python -m rsi status
```

`reference-check` nepotřebuje model, ale potřebuje funkční sandbox. Spustí všech 60 správných referenčních řešení a 60 výchozích chybných řešení. Musí potvrdit, že reference procházejí a chyby jsou odhaleny. Očekávané hodnoty zůstávají v řídicím procesu.

Dodaný benchmark obsahuje 20 číselných úloh pro vývoj, 20 textových pro validaci a 20 úloh nad kolekcemi pro závěrečné hodnocení. Každá má veřejný případ a dva další případy. Rodiny funkcí se mezi sadami neopakují. Jde o malý autorský syntetický benchmark pro ověření mechanismu, ne o reprezentativní real-world benchmark programátora.

Výchozí rozpočet je 150 modelových volání, 1 600 000 účtovaných/rezervovaných tokenů a 30 minut. Pro první baseline může být dostačující podle rychlosti modelu. Pro celou potvrzovací kampaň je malý; odhad uvidíš ve `status`.

## RSI-1 až RSI-4: jeden skutečný kandidát

Pro kompletní jednu generaci nad všemi 60 úlohami je konzervativní horní odhad **907 modelových volání** při maximálně třech krocích na úlohu a třech opakováních validace a závěrečného měření. Při výchozím kontextu/výstupu to odpovídá rezervaci nejvýše **9 287 680 tokenů**. Skutečnost bude nižší, pokud agent řeší úlohy v méně krocích nebo kandidát neprojde časnou branou. Nejde o naměřenou spotřebu.

Pokud chceš tento rozsah povolit, nastav limity explicitně:

```bash
python -m rsi config --set max_calls=1000 --set max_tokens=11000000 --set max_seconds=7200
python -m rsi campaign --generations 1
```

Dvě hodiny jsou strop, nikoliv slíbená doba dokončení. Pomalý lokální model může limit vyčerpat. Paměť modelové služby není součástí sandboxového limitu; celkovou spotřebu RAM na 8GB počítači je potřeba změřit. Peak RAM se zatím automaticky neměří a v záznamu je `null`, nikoliv vymyšlená hodnota.

Průběh kampaně:

1. Původní agent vyřeší vývojové úlohy a vznikne evidence chyb.
2. Tentýž agent přes svůj aktuální modul kontextu navrhne novou implementaci `build_context` a hypotézu.
3. Kandidát projde kontrolou syntaxe, rozsahu změny a obou režimů `solve`/`propose` v sandboxu.
4. Rodič a kandidát řeší shodné úlohy v párovaném pořadí a se stejnými semeny/modelovým rozpočtem na úlohu.
5. Po vývojové bráně následuje skrytá validace, potom jednorázové závěrečné měření.
6. Schopnostní přijetí vyžaduje nejméně dvě nové stabilní výhry, žádné regrese a žádné nestabilní výsledky v obou potvrzovacích sadách. Samostatná efektivnostní brána může přijmout stejnou úspěšnost při nejméně 15% úspoře skutečných tokenů. Stejný druh přínosu musí projít validací i závěrečným měřením; úspora se nevykazuje jako rozšíření schopností.

Prahy jsou pilotní provozní pravidla; přijetí kandidáta samo o sobě není statistickým důkazem obecného růstu inteligence. Návrh neobsahující změnu nebo skutečné měření bez přínosu se zamítne.

## RSI-5: použití přijaté verze a další generace

Výchozí politika ponechá přijatou verzi připravenou k aktivaci. Její ID najdeš v reportu nebo dashboardu:

```bash
python -m rsi activate agent-ID_Z_REPORTU
```

Před aktivací se znovu ověří shoda prostředí, modelu a důležitých parametrů. Kontrolní úloha běží před i po změně aktivní verze. Pokud kontrola po aktivaci selže, systém vrátí předchozí verzi a vadný kandidát dostane stav `canary_failed`.

Po jednorázovém závěrečném hodnocení je sada spotřebovaná, i když kandidát neuspěl nebo měření bylo přerušeno. Další potvrzování vyžaduje skutečně nové úlohy:

```bash
python -m rsi import-benchmark cesta/k/nove_sade.json
python -m rsi campaign --generations 1
```

Novou sadu sestav podle struktury `rsi_state/benchmark.json`, zachovej `dev`, `validation`, `final` a neprolínající se rodiny. Reference jsou volitelné pro modelové měření, ale potřebné pro `reference-check`. Import nekopíruje data do agenta; generátor kandidáta dostává pouze vývojovou evidenci. Skryté instrukce se zpřístupní až agentovi řešícímu danou úlohu při vyhodnocení; očekávané odpovědi se neposílají nikdy.

Přejmenování ID samo o sobě nespotřebovanou sadu nevytvoří. Hashování zachytí stejné závěrečné úlohy při změně názvů/pořadí; sémantickou podobnost nebo kontaminaci modelu nedokáže automaticky vyloučit. Čerstvost a vhodnost datasetu vyžaduje odbornou kontrolu.

## RSI-6: omezený samostatný běh

```bash
python -m rsi config --set auto_promote=true --set max_generations=2 --set stagnation_limit=3
python -m rsi campaign --generations 2
```

Jedna kampaň používá společný strop volání, tokenů a času napříč generacemi. Kontroler vybírá aktivního rodiče z registru. Po přijetí a kontrolním provozu používá další kolo novou verzi. Při spotřebované závěrečné sadě se však zastaví s `fresh_final_dataset_required`; automaticky nevyrábí zdánlivě nové závěrečné úlohy z téhož benchmarku. Pro více potvrzených generací připrav nové datasetové balíky. Nový příkaz `study` umí předem určené balíky postupně použít ve dvou srovnávacích větvích; postup je v `RSI_AB.md`.

Program neběží nepřetržitě na pozadí po uzavření. Samostatnost znamená omezenou kampaň spuštěnou uživatelem, včetně rozhodování, přijetí podle zadané politiky a návratu při selhání. Plánování dlouhodobé služby/cron není v této verzi součástí spuštění.

## Zastavení, návrat a zotavení po pádu

```bash
python -m rsi stop run-ID_Z_REPORTU
python -m rsi rollback
python -m rsi recover
```

`stop` ukončí sandboxovou úlohu nebo modelový transport; uzavření spojení přeruší lokální požadavek, ale závisí na Ollamě, kdy uvolní svůj výpočet. Nejasná spotřeba zůstane konzervativně rezervovaná. Běžící kampaň se ukončí stavem `stopped`.

`rollback` se vrací po rodičovské linii k předchozí přijaté verzi, nikdy nepřepíná tam a zpět na právě odmítnutý kandidát. `recover` lze spustit po tvrdém pádu: pod OS zámkem označí opuštěné běhy jako přerušené. Nerestartuje je a nevydává neúplný výsledek za úspěch.

## Data a oprávnění

Ve výchozím stavu se vše ukládá do `rsi_state/` vedle aplikace. Jiný adresář lze zadat globálně:

```bash
python -m rsi --state /cesta/k/laboratori status
```

Webové rozhraní používá stejnou cestu přes proměnnou `NEUROPILOT_RSI_STATE`. Uchovává se SQLite registr, zdroj každé strategie, rodiče, hashe, akce, skutečné požadavky/odpovědi, spotřeba, použití závěrečných sad a historie vydání. Záznamy mohou obsahovat texty úloh a modelové odpovědi; jsou určeny vlastníkovi lokální aplikace.

Nová verze eviduje jednotlivé spotřebované závěrečné úlohy, takže odmítne i přebalené podmnožiny použité sady. Historie z 3.2.0 nemá úplné záznamy jednotlivých úloh; u starších experimentů je nutné čerstvost sad zkontrolovat ručně.

Kandidát se načítá pouze v sandboxu. Nedostává databázi, produkční data, soubory hodnotitele ani klíče. Měnit smí jeden modul `build_context`, nejvýše 200 přidaných/odebraných řádků. Řešené úlohy jsou v tomto pilotu omezeny na `solution.py`; přístup k obecným repozitářům a závislostem je další rozšíření.

Model může použít nástroje `list_files`, `read_file`, `search`, `write_file`, `run_tests`, `finish`. Zápis kontroluje aktuální SHA-256 a syntaxi. Volání libovolného shellu není součástí protokolu. Kritéria přijetí a limity vlastní změna nemůže měnit.

Výsledky stáhneš pomocí:

```bash
python -m rsi report run-ID_Z_REPORTU --output report.json
```

## Testy a meze důkazů

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
npm install
npm run test:ui
npm run test:rsi-ui
```

`tests/rsi/test_integration.py` obsahuje jasně pojmenované `FixtureProvider` a `FixtureSandbox`. Ověřují stavový tok, úspěch/neúspěch bran, dva navazující kandidáty na nových sadách a rollback. Nejsou dostupné přes CLI jako model nebo sandbox a jejich výsledky se neprodávají jako naměřený výkon AI.

Přiložené `verification/rsi_doctor.json`, `verification/rsi_baseline.json` a `verification/rsi_study.json` zachycují skutečné zablokování této kontrolní relace. Neobsahují vymyšlené modelové skóre. Vizuální kontrola v Safari/Chromiu nebyla dokončena; testovány jsou DOM události.

Neprovedené: reálná inference, kompletní modelová kampaň v cílovém sandboxu, potvrzení dvou skutečných zlepšení, skutečný A/B běh, širší real-world benchmark a statistická studie. A/B kontroler je implementovaný a otestovaný pomocí výslovně označených fixtures; jeho skutečný výsledek zatím neznáme. Pole `actual_rsi_improvement_proven` proto zůstává `false`; případný přínos uvnitř pilotu má zvláštní označení.

## Technické zdroje

- Ollama chat API a skutečné počty tokenů: https://docs.ollama.com/api/chat
- Docker izolace a omezení kontejnerů: https://docs.docker.com/reference/cli/docker/container/run/
- Bubblewrap a seccomp: https://github.com/containers/bubblewrap/blob/main/bwrap.xml

Původní cíl, etapy a pravidla jsou v `RSI_PLAN.md`; tabulka implementace a ověření je v `RSI_STATUS.md`.
