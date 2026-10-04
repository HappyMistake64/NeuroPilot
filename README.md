# NeuroPilot 3.4.0 — RSI s přihlášením ChatGPT

**Nové připojení OpenAI:** na `/rsi` klikni na **Continue with ChatGPT**, dokonči přihlášení, načti a vyber model. Podrobný postup a limity jsou v `OPENAI_README.md`. API klíč ani Codex CLI nejsou potřeba.

**Výzkum a opravy 3.3.1:** otevři `research/report.html` nebo `research/RESEARCH_REPORT.md`. Obsahují měření, simulace a reprodukční příkazy.

**Nové:** laboratoř RSI je na `/rsi`. Postup nastavení, skutečný stav ověření a limity jsou v `RSI_README.md` a `RSI_STATUS.md`. Nové A/B experimenty a efektivnostní bránu popisuje `RSI_AB.md`. Původní audit verze 3.1.0 je zachován jako historický dokument.

NeuroPilot je osobní plánovač s poznámkami, úkoly, návyky a experimentálním modulárním agentem. Základ funguje offline po instalaci Flasku. Původní agent plánovače používá pravidla a šablony; není to jazykový model. RSI agent má samostatné modelové rozhraní přes lokální Ollamu nebo předplatné ChatGPT. Podrobný původní audit je v `AUDIT_A_PLAN.md`.

## Spuštění na Linuxu / macOS

Python 3.10 nebo novější. ZIP rozbal a otevři terminál ve složce `NeuroPilot_3.4.0_OPENAI`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

Otevři **http://127.0.0.1:5000**. Ukončení: Ctrl+C. Na Fedoře/Ubuntu jde o stejný postup. První instalace potřebuje internet; následně základní plánovač internet nepotřebuje.

## Windows

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe server.py
```

## Ovládání

- **Požádej Neura:** zadání → pravidlová odpověď → uložená poznámka.
- **Úkoly:** vytvoření, označení hotovo, opětovné otevření, smazání.
- **Návyky:** vytvoření, splnění/zrušení dneška, součet za posledních sedm dní, smazání.
- **Záloha:** stáhnout JSON; import zálohy nahradí současná data po potvrzení. Staré číselné identifikátory jsou podporovány. Starší záloha bez `habits` dostane prázdný seznam návyků.
- Data plánovače se ukládají do `data.json` vedle serveru. `NEUROPILOT_DATA` dovoluje nastavit jinou cestu. Spouštěj jediný serverový proces.

## Příkazy lokálního agenta

Lze je zadat ve webovém poli nebo v terminálu přes `python run_chat.py`:

| Příkaz | Skutečná funkce |
|---|---|
| `:time` | Aktuální UTC čas |
| `:save_all` | Uložit stav agenta do `state/agent_state_full.json` |
| `:load_all` | Načíst ručně uložený stav |
| `:sleep` | Krátké pravidlové shrnutí a úprava preferencí |
| `fb 1`, `fb 0`, `fb -1` | Změna číselných preferencí |
| `:self truth 0.8` | Nastavit číselnou preferenci; také `novelty`, `coherence` |
| `:rewrite working_memory.slots 3` | Změna dovoleného parametru; nemění zdrojový kód |
| `:read README.md` | Načte nejvýše 2 000 znaků souboru uvnitř projektu; odpověď hlásí počet znaků |
| `:image něco.png` | Informace, že analýza obrázků dosud není implementována |
| `hledej: téma` | Volitelné čtení výsledkové stránky arXiv, po zapnutí webu |
| `hledej: téma1, téma2` | Dávkové čtení několika témat, po zapnutí webu |

Pracovní paměť žije během běhu agenta. Stav se mezi restarty obnovuje příkazem `:load_all` po předchozím `:save_all`; nejde o automatický dlouhodobý konverzační retrieval.

Web agenta je ve výchozím nastavení vypnutý. Zapnutí: `agent.web_cfg.enabled = true` v `config.json`; ponech explicitní whitelist. Po změně konfigurace restartuj server. Nejde o plnohodnotný vyhledávač, ale o omezené čtení webových stránek.

## Volitelné modelové rozhraní Gradio

Je oddělené od základního plánovače a má vlastní `memory.json`. Chat, textové návrhy kroků, shrnutí webu a generátor ZIP vyžadují nastavený kompatibilní textový model. Bez modelu zobrazí srozumitelnou chybu. Při importu aplikace se model nestahuje.

```bash
python -m pip install -r requirements-ai.txt
export NEUROPILOT_MODEL="/absolutni/cesta/ke/kompatibilnimu/modelu"
python app.py
```

Na Windows nastav proměnnou například přes `$env:NEUROPILOT_MODEL = "C:\model"`. Lze použít i ID modelu na Hugging Face; první použití pak stáhne jeho soubory. Výběr modelu, RAM, kvalita češtiny a kontext vyžadují samostatné ověření na cílovém zařízení. Knihovny i váhy mohou být velké; pro základní plánovač je nepotřebuješ. Pro CPU prostředí lze nejdřív nainstalovat odpovídající CPU sestavení PyTorch, aby instalátor neinstaloval nepotřebné GPU závislosti.

**Plánování vytváří textové návrhy. Nespouští terminál, neopravuje repozitáře a netestuje vygenerovaný kód.** ZIP vzniká jen z platných bloků souborů, ukládá se do `generated/` a vyžaduje lidskou kontrolu. Web research načítá jen explicitně zadanou URL, nikoliv adresy náhodně vygenerované modelem.

## Testy

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
python agent_test.py
```

Volitelný test událostí webového rozhraní používá Node.js 22+ a jsdom. Sám spustí izolovaný server s dočasnými daty, která po dokončení odstraní:

```bash
npm install
npm run test:ui
npm run test:rsi-ui
```

Pod Windows nastav `PYTHON` na cestu k Pythonu ve virtuálním prostředí, pokud příkaz `python3` nemáš. Test DOM neověřuje vizuální vzhled ani Safari. Grafické ověření v reálném prohlížeči a inference se skutečným modelem jsou stále otevřené.

## iPhone / Pythonista

Základní agent lze spustit skriptem `run_chat.py`. Webový plánovač potřebuje dostupný Flask; kompatibilita této verze s konkrétní instalací Pythonisty nebyla ověřena. Modelová větev s PyTorch není ověřena na iOS. Pro iPhone je proto nutné nejdřív ověřit základní verzi v cílovém prostředí.

## Rozsah nasazení

Tato verze je určena pro osobní použití na localhostu. Neobsahuje uživatelské účty ani veřejné produkční nasazení. JSON zápisy jsou atomické a chráněné před souběhem vláken jednoho procesu. Více serverových procesů vyžaduje databázi a jiný způsob koordinace.
