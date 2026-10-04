# Implementace RSI — stav dodávky 0.3.0

NeuroPilot 3.4.0 obsahuje nové komponenty všech sedmi etap. Dokončení kódu a průchod testy neznamenají prokázané sebezdokonalení.

| Etapa | Dodaná implementace | Ověření v této relaci |
|---|---|---|
| RSI-0 | 60 specifikovaných úloh, veřejné/skryté případy, reference, oddělené rodiny, hash datasetu, baseline CLI | 60 referencí a 60 chyb ověřeno testy nad důvěryhodnými autorskými fixtures; skutečná modelová baseline `blocked` |
| RSI-1 | Ollama a ChatGPT OAuth adaptery, skutečný HTTP protokol, nástroje souborů a testů, sledování volání/tokenů | HTTP adapter ověřen lokálním testovacím serverem; skutečný model nepřipojen |
| RSI-2 | Pracovní kopie, Docker/Podman/Bubblewrap, probe izolace, kvóty, stop, registr a audit | Limity, konkurence, timeout a odmítnutí neizolovaného běhu otestovány; aktuální OS sandbox nedovolil |
| RSI-3 | Návrh hypotézy a vlastního modulu z vývojové evidence, omezený diff, kontrola obou režimů | Ověřeno testovacím providerem; žádná skutečná modelová vlastní změna zatím nezměřena |
| RSI-4 | Párovaná srovnání, opakování, schopnostní a tokenová efektivnostní brána, jednorázový holdout po jednotlivých úlohách | Testy bran prošly; žádný skutečný schopnostní zisk se netvrdí |
| RSI-5 | Archiv rodičů i autorů změn, aktivace, vícegenerační A/B kontroler s pevným i rekurzivním autorem | Test obou větví na předem určených fixture sadách prošel, včetně odděleného závěrečného auditu; skutečný A/B výsledek chybí |
| RSI-6 | Omezené kampaně, stagnace, automatická aktivace podle konfigurace, kontrolní úloha, rollback, zotavení po pádu | Automatické rozhodování, stop a rollback otestovány; neproběhl skutečný dlouhodobý modelový provoz |

## Rozsah první verze

- Mutuje se pouze Python modul pro sestavení kontextu, včetně části, která připravuje návrhy dalších změn. Váhy modelu se netrénují.
- Úlohy pracují s `solution.py` a standardní knihovnou. Obecné velké repozitáře a instalování závislostí nejsou zahrnuty.
- Běžná aplikace zůstává plánovačem. RSI má vlastní oddělený registr a UI na `/rsi`.
- Automatická efektivnostní brána ověřuje úsporu skutečných tokenů při stejných výsledcích. Doba běhu se vykazuje, ale automatické přijetí podle času se neprovádí.
- A/B kontroler zajišťuje shodné limity obou větví, předem určené sady, oddělené registry a společný čerstvý audit. Jedna pilotní studie není statistickým důkazem; nezávislé opakované studie ani metaanalýza se zatím automaticky neprovádějí.
- Peak RAM je neznámá hodnota; limit sandboxu se vynucuje, spotřeba modelového serveru se musí měřit zvlášť.
- Další potvrzené generace vyžadují skutečně nové závěrečné sady. Na jedné sadě nelze neomezeně opakovat přijímání kandidátů.

## Ověření verze 3.4.0

202 automatických testů prošlo. Nových 31 testů pokrývá OAuth, podepsané JWT, rotaci tokenů, lokální callback, SSE, chybné odpovědi, přečerpání tokenů a ukončení transportu. DOM test RSI zahrnuje přihlášení, zrušení pokusu a chybu při načítání modelů bez účtu. Skutečná inference se před přihlášením netvrdí.

## Historické ověření verze 3.3.1

171 automatických testů prošlo, včetně úspory tokenů, odmítnutí neznámé telemetrie, dvou A/B větví, celkových rozpočtů a zastavení. Dva DOM testy ověřují plánovač a nové ovládání RSI. Skutečná baseline i A/B studie zde zůstávají `blocked`.

## Nejbližší skutečný krok

Na cílovém Linuxu přihlásit ChatGPT (`OPENAI_README.md`) nebo připravit Ollamu; ověřit `provider-check` a připravit izolaci → `doctor` → `reference-check` → `baseline --limit 10` → prohlédnout skutečné výsledky → povolit odpovídající rozpočet → `campaign --generations 1`.

Výstupem první kampaně může být i zamítnutí všech změn. Platný negativní výsledek není chyba frameworku.

## Výzkumná revize

Výzkum verze 3.3.0 a opravy 3.3.1 dokumentuje `research/RESEARCH_REPORT.md`; přehled s grafy je v `research/report.html`. Naměřené limity rozhodovacích bran se nezaměňují za výkon skutečného modelu.
