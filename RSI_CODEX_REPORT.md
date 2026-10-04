# NeuroPilot: Codex pro skutečné RSI experimenty

Ověřeno 4. 10. 2026, z `main` po sloučení PR #2
(`2db179dcc5237707ea9eaafb5935ff1ffabb5ca0`), větev `feat/complete-rsi-integration`.

NeuroPilot připojuje ChatGPT přes oficiální Codex app-server také k běžnému
RSI provideru. Model `gpt-6.1-sol` v cloudovém prostředí skutečně vyřešil
10 z 10 vývojových úloh; řešení nezávisle ověřil Bubblewrap sandbox.

## Změny

- Provider `codex`, výběr dostupného modelu na `/rsi`, CLI konfigurace
  `provider=codex` a `codex_model=ID_Z_KATALOGU`.
- Lokální rozpočtová brána počítá každé předání HTTP modelového požadavku před
  odesláním. Opakování klienta není bezplatné a neobejde `max_calls`.
- Oficiální Codex spravuje přihlášení a obnovu tokenů. NeuroPilot nečte jeho
  credential soubor; hlavičky předá pouze v paměti na publikovaný výchozí
  Codex backend. Přímý SIWC OAuth provider má vlastní nezávislou registraci.
- Modelové nástroje jsou vypnuté; vykonání akcí z JSON provádí dosavadní broker
  a sandbox. Limity, evaluátor, rozdělení dat, brány přijetí a automatická
  aktivace zůstávají zachované.

Podklady pro integraci: [app-server](https://developers.openai.com/codex/app-server),
[přihlášení](https://developers.openai.com/codex/auth),
[konfigurace providerů](https://developers.openai.com/codex/config-reference) a
[publikovaná definice výchozího backendu](https://github.com/openai/codex/blob/main/codex-rs/model-provider-info/src/lib.rs).
Ověřený klient: `codex 0.159.0-alpha.3`. OAuth na telefonu uživatel dokončil v
předchozím kroku; při těchto měřeních nebyl vyžádán další přihlašovací kód.

## Živé výsledky

| Běh | Výsledek | Skutečné HTTP požadavky | Skutečné tokeny |
|---|---|---:|---:|
| Test rozpočtového provideru `run-7a3dc9b41841` | Odpověď `{"connection":"ok"}`, inference ověřena | 1 | 1 548 |
| Baseline `run-0c09f8c7b934` | 10/10 úloh vyřešeno, všechny v jednom kroku | 10 | 19 866 |
| Pilot `run-02edf3b63d3c` | Generace dokončena, kandidát zamítnut | 61 | 126 767 |

Důkazy: [test spojení](verification/codex_budgeted_connection.json),
[baseline včetně výsledků úloh](verification/codex_rsi_baseline.json).
V exportech je vynechán otisk účtu; nejsou v nich tokeny, přihlašovací kódy
ani surový transport. Předchozí samostatný `codex-check` s náhodnou výzvou
zůstává doložený v `CODEX_CONNECTION_REPORT.md`.

Baseline měla limity 30 volání, 300 000 tokenů a 600 sekund. Ověřila prvních
10 vývojových úloh existujícího autorského syntetického benchmarku. Nejde o
SWE-bench ani důkaz obecné schopnosti opravovat libovolné repozitáře.

## Výsledek jedné generace

Kampaň měla původní výchozí limity: **150 volání, 1 600 000 tokenů, 1 800 sekund**,
`auto_promote=false`. Nejprve změřila všech 20 vývojových úloh. Model sám navrhl
změnu modulu `build_context`: kompaktnější JSON a podrobnější instrukce k opravám.
Následovalo nové párované měření původní a kandidátní strategie.

Obě strategie vyřešily **20/20** úloh bez nestability či regrese. Původní strategie
spotřebovala 39 702 tokenů, kandidát 40 694, tedy **o 2,50 % více**. Nebyly nové
vyřešené úlohy ani požadovaná úspora alespoň 15 %. Kandidát
`agent-047e036cce07` proto skončil `rejected_development`. Celá kampaň má stav
`complete`: dokončeným výsledkem je zamítnutí, nikoli přijetí změny.

Aktivní zůstal `agent-d1fe1545e5b6`. Validace ani závěrečný holdout se nespustily;
žádný holdout nebyl spotřebován. Všech 61 HTTP požadavků má skutečné účtování,
neznámá spotřeba je nula a auditní řetězec je platný. Izolace, tokenová brána,
minimální úspora a počty opakování nebyly kvůli výsledku změněny.

Důkazy: [report kampaně](verification/codex_rsi_campaign.json),
[modelový kandidát](verification/codex_rsi_candidate.json),
[výsledky jednotlivých úloh a audit](verification/codex_rsi_campaign_audit.json).
**Tento pilot neprokázal zlepšení RSI.** Prokazuje funkční cyklus od inference,
přes vlastní návrh a izolované hodnocení až po vnější rozhodnutí o zamítnutí.

## Reprodukce

Závislosti: `python -m pip install -r requirements-dev.txt` a
`npm install --ignore-scripts --no-audit --no-fund --package-lock=false`.
Repozitář nemá npm lockfile, proto se nepoužívá `npm ci`.

```bash
python -m rsi codex-login  # jen pokud platné přihlášení chybí
python -m rsi codex-status
python -m rsi --state /chranena/cesta/rsi config \
  --set provider=codex --set codex_model=ID_Z_KATALOGU --set sandbox=bwrap
python -m rsi --state /chranena/cesta/rsi provider-check
python -m rsi --state /chranena/cesta/rsi init
python -m rsi --state /chranena/cesta/rsi doctor
python -m rsi --state /chranena/cesta/rsi baseline --limit 10
python -m rsi --state /chranena/cesta/rsi campaign --generations 1
```

Při chybě sandboxu se experiment zastaví. Pro izolaci lze místo Bubblewrapu
použít připravený Docker/Podman. Přihlášení přes telefon popisuje `OPENAI_README.md`.

## Hranice dodávky

Tokenový rozpočet je účetní kontrola, nikoli tvrdý limit serveru. Jeden požadavek
jej může překročit, další se už neodešle. Stop a timeout ukončí místní transport;
nejsou zárukou, že vzdálený server okamžitě přestane účtovat již odeslaný dotaz.
Při neznámé spotřebě zůstává započítaná rezervace, nikdy nula.

Podporováno je výchozí směrování ChatGPT bez regionálního omezení workspace;
jiné směrování se odmítá. Experimentální pole app-serveru mohou vyžadovat úpravu
po aktualizaci klienta. Seed a váhy hostovaného modelu nejsou připnuté.
Původní plánovač nadále používá pravidlového agenta, tato integrace patří do
samostatné laboratoře RSI. Aplikace je pro localhost; veřejné nasazení, grafické
ověření Safari a dlouhodobý A/B výzkum nejsou výsledkem tohoto PR.

## Testy

- `NEUROPILOT_TEST_SANDBOXES=bwrap,docker python -m pytest tests -q`:
  **264 passed**, včetně skutečných probe obou sandboxů a 25 nových testů.
- `python agent_test.py`: prošel.
- `npm run test:ui`: prošel.
- `npm run test:rsi-ui`: prošel; ovládání Codexu testováno pomocí označené
  protokolové fixture, ostatní ovládání proti skutečnému lokálnímu Flask serveru.
- `git diff --check`: prošel. Přehled: `verification/codex_rsi_checks.json`.
- Nové regrese zahrnují účtování retry, odmítnutí nadlimitního požadavku před
  transportem, skutečné přečerpání, neznámou spotřebu, zrušení, ukončení upstream
  procesu při timeoutu/stop, zákaz nástrojů, neúplný SSE stream, kontrolu
  identity/routingu, explicitní UI konfiguraci a ochranu proti cizímu originu.

Místní výchozí `rsi_state` byl inicializován s `provider=codex`,
`codex_model=gpt-6.1-sol`, `sandbox=bwrap`; `doctor` vrací `ready=true`.
Tento stav a přihlášení nejsou součástí Gitu. Nová instalace potřebuje vlastní
přihlášení a výběr modelu. Živé experimenty běžely v samostatném state mimo
repozitář a produkční data plánovače.
