# NeuroPilot 3.3.1 — kontrolní experiment a efektivita

Nové příkazy rozšiřují RSI-4 až RSI-6. Připravují měřitelný experiment se skutečným modelem přes Ollamu. Testovací providery nejsou dostupné z CLI ani UI.

## Co porovnáváme

| Větev | Kdo navrhuje další změnu | Který agent řeší úlohy |
|---|---|---|
| `fixed_author` | Stále přesná počáteční strategie | Nejlepší dosud přijatá verze této větve |
| `recursive` | Poslední přijatá strategie | Nejlepší dosud přijatá verze této větve |

Obě větve začínají ze stejného zdrojového kódu aktuálně aktivního agenta. Mají stejný model, izolaci, sady, limity kroků a celkové rozpočty. Pevný autor dostává aktuální měněný zdroj a stejný druh vývojové evidence; pevná zůstává strategie, která připravuje kontext pro návrh změny. Identita autora je v každé generaci zaznamenána odděleně od rodiče.

Přijaté verze se aktivují pouze uvnitř větve. Studie nemění aktivní verzi hlavní laboratoře. Studie nepřebírá otevřené úlohy uživatele a nemění běžný plánovač.

## Spuštění

Nejdřív nastav model a izolaci podle `RSI_README.md`. Pokračuj až po úspěšném `doctor` a malém skutečném baseline běhu.

```bash
python -m rsi init
python -m rsi study-create rsi_state/study_manifest.json
python -m rsi study-plan rsi_state/study_manifest.json
```

Výchozí manifest rozdělí autorský katalog: první kolo má 8 vývojových, 8 validačních a 8 závěrečných úloh; druhé má dalších 8/8/8. Společný audit používá 4 další závěrečné úlohy. Žádná rodina ani totožná úloha se mezi koly a auditem neopakuje. V rámci jednoho kola obě větve záměrně používají stejné úlohy. Je to malý pilot, ne důkaz obecné inteligence.

Odhad horní meze je **770 volání na jednu větev**, tedy 1 540 pro obě. Při výchozím kontextu/výstupu je konzervativní rezervace **7 884 800 tokenů na větev**. Odhad není naměřená spotřeba.

Například pro tento rozsah lze explicitně nastavit:

```bash
python -m rsi config --set max_calls=1000 --set max_tokens=11000000 --set max_seconds=7200 --set max_generations=2
python -m rsi study rsi_state/study_manifest.json
```

U `study` jsou tyto limity **na každou větev dohromady přes všechna kola i audit**. Celá studie tedy může spotřebovat až 2 000 volání, 22 milionů účtovaných tokenů a čtyři hodiny. Jde o stropy, nikoliv předpověď. Výchozích 150 volání na větev může ukončit vývoj před dosažením nového kandidáta.

Kontroler rezervuje nejhorší počet auditních volání/tokenů a čtvrtinu časového limitu pro audit. Vyčerpání vývojového rozpočtu zastaví vývoj dané větve; pokud zbývá rozpočet, audit změří její poslední aktivní verzi. Celkový limit nadřazeného běhu platí také během čekání a přípravy. V auditu se střídá pořadí větví a obě dostávají stejné úlohy a semena. Čekání na druhou větev se nepřičítá jako výpočetní čas první.

V UI na `/rsi` jsou tlačítka **Připravit A/B plán** a **Spustit A/B experiment**. Zobrazují také limity a konzervativní odhad. Příprava existující manifest nepřepisuje. Vlastní manifest předáš přes CLI.

## Zastavení a výsledky

```bash
python -m rsi status
python -m rsi stop run-ID_STUDIE
python -m rsi report run-ID_STUDIE --output moje_studie.json
```

ID nadřazeného běhu uvidíš v seznamu běhů. Zastavení se kontroluje i uvnitř nástrojů a modelového transportu podřízených běhů. Registrované výstupy zůstanou zachované. Tvrdě přerušený proces lze označit příkazem `recover`; studie se automaticky neobnovuje a spotřebované sady se neuvolňují.

Každá studie má pod `rsi_state/studies/study-ID/` vlastní kopii manifestu, dva registry a report. V reportu najdeš:

- `arms`: generace, rodiče, autory, spotřebu, zastavení a auditní výsledky po větvích.
- `comparison`: nové výhry rekurzivní větve proti pevné, regrese a nestabilitu.
- `efficiency_comparison`: skutečné tokeny obou finálních agentů při auditu.
- `audit_complete`: zda byl audit obou větví dokončen.
- `actual_rsi_improvement_proven: false`: jedno pilotní srovnání neprokazuje obecnou výhodu rekurze.

Spotřeba reportu zahrnuje i generování kandidátů, odmítnuté pokusy a kontrolní úlohy. Neúplná telemetrie zůstává označena; rezervované tokeny se účtují konzervativně. Auditní úspora finálního agenta se nesmí zaměňovat za úsporu celého procesu vývoje.

Pokud obě větve vyřeší stejné úlohy, výsledek je shoda. Pokud rekurzivní větev nepřinese výhodu, je to platný negativní výsledek. Pro silnější závěr jsou potřeba nezávislé opakované studie na širších, nových sadách; tento program zatím automatickou statistickou studii nevytváří.

## Čerstvost sad

Manifest obsahuje `schema: 1`, pole `rounds` se seznamy úloh a `audit` se závěrečnými úlohami. Formát jednotlivé úlohy odpovídá `rsi_state/benchmark.json`. Vyžadují se nejméně dvě kola a nejvýše `max_generations`; všechny sady se validují před prvním voláním modelu.

Po ověření prostředí kontroler rezervuje všechny závěrečné úlohy manifestu. Ani přerušená studie je automaticky neuvolní. Nelze zkoušet stále stejný audit a vybírat jen úspěšné běhy. Podmnožiny a změny ID neobejdou záznam použití. Rozpoznání sémanticky podobných úloh a kontaminace tréninkových dat vyžaduje odbornou kontrolu.

Dodaný manifest nelze použít jako nezávislý audit, pokud jsi jeho závěrečné úlohy už spotřeboval v běžné kampani. Připrav skutečně nové sady. U databází z 3.2.0 se kontroluje známý aktuální benchmark, ale stará historie neobsahuje kompletní evidenci jednotlivých úloh.

## Efektivnostní brána

Výchozí nastavení:

```bash
python -m rsi config --set allow_efficiency=true --set min_token_saving_percent=15
```

Přijetí kvůli efektivitě vyžaduje shodný výsledek každé párované úlohy, stabilitu opakování, alespoň jednu skutečně vyřešenou úlohu a úplné skutečné počty tokenů. Sčítají se všechny měřené pokusy včetně neúspěšných. Úspora nejméně 15 % musí projít zvlášť validací a závěrečnou sadou. Úspornější agent s nulovou úspěšností se nepřijme.

Report takovou změnu označí `gain_kind: efficiency` a `pilot_efficiency_gain_confirmed`. Nepřidá jí označení schopnostního zisku. Vypnutí této cesty ponechá pouze schopnostní bránu. Medián času je informativní; časová brána ani automatické měření maxima RAM zatím součástí nejsou.

## Stav dodaného balíku

171 automatických testů a dva testy DOM prošly. Test A/B používá viditelně označené náhrady modelu a sandboxu. Skutečný pokus v prostředí této relace skončil `blocked`: nebyl nakonfigurován lokální model a dostupný Bubblewrap neprošel izolací. Žádná skutečná výhra, úspora ani přínos rekurze se z těchto testů nevyvozuje.
