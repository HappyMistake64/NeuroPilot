# 3.4.0 — OpenAI přes předplatné ChatGPT, RSI 0.3.0

- Přímé oficiální OAuth přihlášení: PKCE, state, nonce, ověření podpisu JWT a více oddělených účtů.
- Chráněné uložení mimo projekt, serializovaná obnova rotujících tokenů, odhlášení a revokace.
- Responses SSE adapter pro předplatné, výběr modelu z katalogu účtu; žádný API-key fallback ani nástroje hostitele.
- UI připojení na `/rsi`, CLI `openai-*`, skutečný jednorázový test `provider-check`.
- Vykazování skutečných tokenů a neznámé spotřeby, zastavení při přečerpání. Tokenový limit je u tohoto preview účetní, nikoliv pevný serverový strop. Seed a připnutí vah nejsou podporovány.
- 202 Python testů; dva DOM testy. Testy OAuth používají fixtures, skutečné přihlášení a inference vyžadují dokončení uživatelem.

# 3.3.1 — výzkumná revize a opravy RSI 0.2.1

- Výzkum: 60 úloh, 3 534 rozšířených referenčních případů, 800 000 simulovaných scénářů rozhodovacích bran, 5 000 souběžných rezervací, 500 opakování stavu, 18 řízených výpadků a škálování auditu.
- Opraveno: nepřesné celé číselné výsledky, overflow při porovnání velkých integerů a přijetí chybějící hodnoty jako null.
- Opraveno: nesprávný typ cesty nástroje, záporné/nevhodné rezervace tokenů, totožné úlohy s přejmenovanými rodinami a přesun spotřebovaného holdoutu do vývojové sady.
- Přidáno 20 regresních případů: celkem 171 Python testů.
- Původní pravidla přijetí zachována. Výzkum ukázal jejich nízkou citlivost při kolísání výsledků; nenahrazujeme měření umělým uvolněním prahů.
- Kompletní report, JSON výsledky, skript a výchozí archiv v research/. Skutečný modelový RSI běh stále není v tomto prostředí ověřen.

# 3.3.0 — RSI 0.2.0

- Skutečná spotřeba tokenů a počet volání po úlohách; neznámé hodnoty zůstávají neznámé.
- Samostatná efektivnostní brána: stejná úspěšnost, žádná nestabilita a nejméně 15% úspora tokenů, potvrzená ve validaci i finální sadě.
- Předem určená A/B studie: pevný autor změn proti rekurzivnímu autorovi, nové sady v dalších kolech, společný čerstvý audit.
- Stejné kumulativní limity pro každou větev a rezervace části rozpočtu pro audit; stop se přenáší do podřízených běhů.
- Registry uchovávají rodiče i autora; neplatný kandidát dostane stav invalid. Aktivní agent hlavní laboratoře se studií nemění.
- Ochrana proti opakovanému použití závěrečných úloh i v přebalené podmnožině.
- UI: příprava/spuštění A/B studie, limity a diff strategie.
- 151 Python testů a dva DOM průchody; skutečný modelový běh stále vyžaduje cílový Linux, Ollamu a funkční izolaci.

# 3.2.0 — RSI 0.1.0

- Přidána laboratoř RSI na `/rsi` a CLI `python -m rsi`.
- 60 pilotních úloh, reference, baseline, modelový provider pro lokální Ollamu.
- Izolované strategie a testování, kontrola dostupnosti sandboxu bez neizolované náhrady.
- Hypotézy, vlastní změny kontextového modulu, porovnání verzí a jednorázové závěrečné měření.
- Registr rodičů, aktivace, kontrolní provoz, rollback, rozpočty a přerušení.
- 141 automatických testů a dva DOM integrační průchody.
- Skutečný modelový RSI experiment zatím blokuje chybějící model/izolace v kontrolním prostředí; výkonnostní zlepšení se netvrdí.

# 3.1.0

- Funkční JavaScript pro Flask plánovač; Python/Gradio přesunut do `app.py` a `ai_tools.py`.
- Opraveny statistiky návyků, export, validace API, import záloh a cesty nezávislé na cwd.
- Atomické JSON zápisy se zámkem, UUID záznamů, dokončování a mazání úkolů.
- Zachování pracovního stavu a konfigurace agenta, úplnější save/load, registrace 15 modulů.
- Funkční priorita příkazů, normalizace Unicode, regexy, omezené čtení souborů.
- Řízený worker s omezenou frontou a bez mapy opuštěných výsledků.
- Kontrola síťových adres a přesměrování, bezpečné cesty generovaných ZIP souborů.
- Volitelný model bez downloadu při importu, max_new_tokens a rezervace kontextu.
- Textové plánování odděleno od skutečného provádění; dokumentace odpovídá kódu.
- 46 automatických testů a integrační test událostí frontend/backend.
