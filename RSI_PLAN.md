# NeuroPilot — plán řízeného rekurzivního sebezdokonalování

Datum: 3. října 2026. Výchozí projekt: NeuroPilot 3.1.0. Stav dokumentu: návrh implementace; popsané nové schopnosti nejsou dosud naprogramovány.

RSI zde znamená Recursive Self-Improvement: agent upraví vlastní postup nebo povolenou část implementace, prokáže užitek v nezávislém měření a jeho nová verze se stane výchozím agentem dalšího kola. Cílem je doložit opakované zlepšení konkrétní schopnosti. Zrychlující se růst schopností, obecná inteligence ani neomezené sebezdokonalování nejsou předpokladem ani slíbeným výsledkem.

## 1. První měřitelný cíl

NeuroPilot se bude nejprve zlepšovat v opravách malých Python projektů: ze zadání najde relevantní soubory, navrhne patch, ověří ho a odevzdá použitelnou opravu. Zlepšovat může vlastní výběr kontextu, plánování kroků, aplikaci patchů a práci s chybami testů.

První cílový experiment: jedna vlastní úprava postupu vyřeší dříve nezvládnuté úlohy za stejných výpočetních podmínek; tento výsledek se zopakuje na nových úlohách. Dalším cílem budou nejméně dvě navazující přijaté generace, u kterých lze doložit, že každou další změnu navrhl předchozí vylepšený agent. Jde o experimentální cíle, nikoli předpověď úspěchu.

Za zlepšení inteligence se nesmí vydávat pouhá změna názvu, osobnosti nebo skóre nastaveného samotným agentem. Nižší cena při zachované úspěšnosti je užitečné zlepšení efektivity, které se bude vykazovat samostatně.

## 2. Co máme a co chybí

V auditu verze 3.1.0 je doloženo funkční lokální API, pravidlový agent, 15 modulů, opravy paměti, ukládání, volitelná modelová větev, 46 automatických testů a integrační test DOM. Reálná inference modelu ani skutečný agent pro úpravy repozitářů ověřeny nejsou.

Chybí jednotný modelový provider, pracovní kopie repozitáře, nástroje agenta, izolovaný běh, úlohový benchmark, nezávislý hodnotitel, správa kandidátů a proces přijetí/vrácení verze. Současné příkazy `:self` a `:rewrite` mění preference nebo nastavení; ještě netvoří RSI.

Osobní plánovač může zůstat ovládacím rozhraním. Vývoj RSI bude mít vlastní backlog a verzování experimentálního runtime, aby se jeho postup nemíchal s dřívější produktovou roadmapou.

## 3. Cílová architektura

| Část | Odpovědnost | Hranice |
|---|---|---|
| NeuroPilot UI | Cíl, stav běhu, porovnání verzí, diff, důvody přijetí, zastavení a návrat | Zobrazuje ověřené výsledky ze služby hodnocení |
| Provider | Volání skutečného modelu, časové a tokenové limity, identita modelu | Klíče drží důvěryhodná služba; kandidát je nedostane |
| Výkonný agent | Čtení projektu, návrh a aplikace patchů, veřejné testy, další krok | Pracuje pouze v přiděleném sandboxu |
| Generátor kandidátů | Z logu selhání vytvoří hypotézu a vlastní změnu povoleného modulu | Nemění testy, skórování ani pravidla přijetí |
| Správce experimentu | Výběr rodiče, rozpočet, pořadí běhů, životní cyklus kandidáta | Spolehlivý proces mimo měnitelný kód |
| Hodnotitel | Nezávislé spuštění testů, výsledky po úlohách, porovnání s baseline | Skryté testy a očekávané odpovědi nejsou přístupné agentovi |
| Registr verzí | Artefakty, hashe, rodič, diff, výstupy a rozhodnutí | Kandidát nemůže přepisovat výsledky ani historii |
| Správce vydání | Aktivace ověřené verze, kontrolní provoz, rollback | Nemůže být změněn hodnoceným kandidátem |

Návrh struktury: `providers/`, `agent_runtime/`, `experiments/`, `evaluation/`, `registry/`, `release/`. Pouhé oddělení do adresářů neznamená izolaci. Hodnotitel, registry a pravidla poběží pod jiným oprávněním nebo v oddělené službě; nebudou zapisovatelně připojeny do sandboxu kandidáta.

## 4. Jeden cyklus zlepšování

1. Správce připne rodičovskou verzi, model, závislosti, datovou sadu a rozpočet.
2. Spustí výchozí měření nebo načte platnou baseline se shodným prostředím.
3. Agent dostane pouze vývojové úlohy a jejich povolené diagnostické záznamy.
4. Navrhne jednu konkrétní hypotézu: problém, očekávaný mechanismus zlepšení a cenu změny.
5. V nové pracovní kopii změní jen povolený kód. Správce uloží diff a hash.
6. Nezávislá kontrola ověří rozsah změn, rozhraní, regresní testy a limity.
7. Kandidát se porovná s rodičem na vývojových úlohách za shodných podmínek.
8. Vybraný kandidát se ověří na neveřejné validační sadě. Agent neuvidí její obsah ani podrobné chyby.
9. Před vydáním proběhne oddělené závěrečné měření. Zamítnutý kandidát zůstane v archivu; aktivní verze se nezmění.
10. Přijatý kandidát projde kontrolním provozem. Jeho přesný artefakt se stane rodičem dalšího kola.

Výsledek může být přijetí, zamítnutí nebo nedostatek důkazů. Žádná nová verze se nevydává pouze proto, že vznikla nová generace. Po vyčerpání rozpočtu se běh označí jako nedokončený a pozastaví.

## 5. Etapy implementace a dokončovací podmínky

| Etapa | Co vytvořit | Kdy je hotovo |
|---|---|---|
| RSI-0: zadání a měření | Vymezené úlohy, dataset manifest, veřejné/skryté testy, protokol výsledků | Každá úloha má ověřitelný výsledek; vadná řešení skutečně selžou |
| RSI-1: skutečný agent | Jeden provider, čtení souborů, patch, veřejné testy, limit kroků | Agent sám vyřeší několik předem neviděných malých oprav; všechny akce mají skutečné záznamy |
| RSI-2: prostředí experimentů | Pracovní kopie, izolace, limity, archiv, přerušení a opakovatelné běhy | Neúspěšný nebo zaseknutý kandidát nepoškodí produkční data; lze rekonstruovat běh |
| RSI-3: první vlastní změna | Diagnóza selhání, generování jednoho kandidáta, vnější hodnocení | Nový kandidát vznikne bez ručního napsání jeho změny a je korektně přijat či odmítnut |
| RSI-4: doložené zlepšení | Nezávislé úlohy, opakování, porovnání při stejném rozpočtu | Rozdíl je potvrzen a není jen cenou většího počtu pokusů; zamítnutí zůstává platným výsledkem |
| RSI-5: rekurzivní cyklus | Přijatá verze jako další autor kandidátů, rodokmen, obnovitelnost | Existují alespoň dvě navazující ověřené generace a přesný původ každé změny |
| RSI-6: omezený samostatný provoz | Dlouhodobý rozpočet, kontrolní provoz, automatický návrat a zastavení stagnace | Série běhů má úplné záznamy, stabilní aplikaci a opakovaně otestovaný rollback |

Závislosti: RSI-0 a návrh RSI-1 lze připravovat souběžně. Spouštění vlastních změn vyžaduje hotové RSI-2. RSI-5 nezačne, dokud se nedoloží přínos na RSI-4. Konkrétní termín se stanoví po změření prvního skutečného modelového běhu; rychlost současných jednotkových testů není odhadem délky modelových experimentů.

## 6. Benchmark a důkazy

### Rozdělení úloh

Pro první plný experiment navrhuji 60 nezávislých malých úloh: 20 vývojových, 20 validačních a 20 závěrečných. Je to pilotní velikost, ne dostatečný důkaz univerzálního zlepšení. Rozdělení bude podle rodin chyb a projektů, aby se blízké varianty jedné chyby nerozdělily mezi trénování postupu a závěrečné hodnocení.

Typy úloh: validace API, práce se stavem, parsování strukturovaného výstupu, chyby při aplikaci patchů, výběr souborů, oprava selhávajících testů a zvládnutí limitů. Skrytá sada musí obsahovat nové problémy, ne jen přejmenované kopie vývojových úloh. Původních 46 testů NeuroPilotu bude regresní brána, nikoli měřítko agentní schopnosti.

Skryté testy spouští hodnotitel po dokončení úlohy a po ukončení agentního procesu. Jeho adresář a správné odpovědi se nepřipojí k prostředí agenta. Veřejné testy může agent používat při řešení.

### Metriky

| Metrika | Význam |
|---|---|
| Resolved | Podíl úloh, jejichž finální oprava projde nezávislými funkčními i regresními testy |
| New wins / regressions | Přesný počet nově vyřešených a nově pokažených úloh oproti rodiči |
| Invalid patches | Neaplikovatelné, nepovolené nebo prázdné změny |
| Calls / tokens / cost | Skutečná spotřeba modelu; chybějící telemetrie se neodhaduje jako nula |
| Runtime / peak RAM | Doba a maximum paměti měřené důvěryhodným runnerem |
| Stability | Kolikrát stejný kandidát při opakování úlohu skutečně vyřeší |
| Improvement yield | Přijatá zlepšení na počet kandidátů, modelové volání a celkový rozpočet |
| Rollback | Důvod, úspěšnost a čas návratu na funkční verzi |

Při generování se zapisuje model, jeho dostupná identita/verze, nastavení samplování, prompt, počet pokusů a tool budget. Porovnání proběhne na stejném hardwaru a ve srovnatelném zatížení. Pořadí rodič/kandidát se bude střídat nebo náhodně míchat. Změna modelu či rozpočtu zakládá nový experiment; není sama důkazem RSI.

### Přijetí kandidáta

Vždy musí projít integrita chráněných komponent, regresní testy a limity. Kandidát nesmí upravit hodnotitel, ukrást správné odpovědi ani vydávat textový log za provedený test. Zelený výstup z modelu nemá autoritu výsledku runneru.

Pro pilot navrhuji schopnostní bránu: nejméně dvě nové stabilně vyřešené úlohy ve validační sadě a žádná nová stabilní regrese. Nejasné/stochastické případy se opakují u rodiče i kandidáta minimálně třikrát. Tato brána je provozní filtr, nikoli statistický důkaz. Před širším tvrzením o zlepšení se porovnání potvrdí na čerstvé závěrečné sadě a uvede nejistota výsledku; opakované běhy téhož problému se nesmějí vydávat za nezávislé nové úlohy.

Efektivnostní brána je samostatná: zachovaná úspěšnost a například nejméně 15% úspora tokenů nebo mediánu času. Jde o navržený práh k doladění podle variance baseline. Výsledek se označí jako úspora, ne jako rozšíření schopností.

Validační zpětná vazba je omezená a počet pokusů předem daný. Opakovaným používáním přestává být sada nezávislá. Závěrečná sada se použije jednou pro předem vybraného finalistu; po zpřístupnění výsledků se pro další potvrzení nahradí čerstvou sadou. Rodiny úloh, historie použití a možné úniky se evidují.

## 7. Rozsah vlastních změn

| Povolit postupně | Zachovat mimo oprávnění kandidáta |
|---|---|
| Instrukce k řešení a strukturu pracovního plánu | Správné odpovědi, skryté testy a bodování |
| Výběr relevantních souborů a skládání kontextu | Limity peněz, tokenů, času, paměti a sítě |
| Validaci patchů a zacházení s chybami nástrojů | Klíče providerů, přihlašovací údaje a osobní data |
| Omezené opakování, volbu dalšího kroku | Aktivaci produkce a nouzové zastavení |
| Formát vlastní zkušenostní paměti | Podepisování/ověřování výsledků a registry |
| Později strategii návrhu dalších kandidátů | Samotné hranice oprávnění a instalační prostředí |

Agent dostane kopii svého povoleného kódu. V první verzi maximálně jednu cílenou změnu, tři soubory a 200 změněných řádků na kandidáta; překročení se označí jako mimo rozsah. Tato čísla jsou výchozí nastavení experimentu, která může správce později explicitně změnit.

Linux runner: samostatné neprivilegované prostředí s omezeným CPU/RAM/časem, bez hostitelských klíčů a bez přístupu k produkčním datům. Pouhý podproces nebo Git worktree není bezpečnostní sandbox. Síťové nástroje budou ve výchozím experimentu vypnuté; přístup k modelu zprostředkuje omezený broker mimo měnitelný kód. Kandidát nemůže instalovat balíčky mimo předem připravený obraz.

Změny aplikačního kódu se přijímají podle předem stanovené politiky; rozšíření oprávnění a zásahy do hodnoticího jádra jsou samostatná změna spravovaná člověkem. Není nutné ručně potvrzovat každou vratnou operaci uvnitř přiděleného experimentu.

## 8. Provoz na 8 GB RAM

Pro první pokusy navrhuji jednu kandidátní větev a jeden běžící worker. Modelový provider může být externí nebo lokální; lokální varianta se přijme teprve po změření RAM a rychlosti s konkrétním modelem. Model není nutné trénovat: první RSI se týká orchestrace a vlastních nástrojů při neměnných vahách modelu.

Předběžný rozpočet jednoho sandboxu: 1–2 GB RAM a nejvýše dvě CPU vlákna pro malé testovací projekty. Zbytek paměti musí stačit systému, UI a případnému modelu; součet se změří. Pokud se nevejde, sníží se kontext či rozsah testů nebo se model přesune na oddělený provider.

Každý běh musí mít pevný strop počtu volání a tokenů; placený provider navíc peněžní strop. Bez nastaveného rozpočtu se placený experiment nespustí. Hodnoty a aktuální ceník se určují až pro zvoleného providera; tento plán žádný účet ani placený běh neaktivuje.

Pro první technický pilot: 10 veřejných úloh, rodič a jeden kandidát, dvě opakování a nejvýše tři modelová volání na řešení. To je nejvýše 120 volání pro řešení úloh; s rezervou na diagnózu/návrh nastavíme limit 150 volání. Jde o test celého procesu, nikoliv o nezávislé potvrzení pokroku. Plné validační měření má samostatný rozpočet spočtený před spuštěním.

Po třech kandidátech bez prokazatelného přínosu se kampaň zastaví a vznikne zpráva o stagnaci. Jde o úsporný výchozí limit pro pilot, ne tvrzení, že další zlepšení není možné. Timeout, OOM a chybějící výsledek se evidují jako neúspěšný/neúplný běh, nikdy jako splněná úloha.

## 9. Paměť experimentů a verzování

Každý kandidát dostane ID, ID rodiče, hash kódu, diff, stručnou hypotézu, seznam dostupných dat, prostředí, model, spotřebu, výsledky po úlohách a rozhodnutí. Uchovávají se přijaté i zamítnuté varianty. Zkušenostní paměť agentovi zpřístupní jen vývojová selhání a ověřené obecné poznatky; podrobnosti skrytých testů se do ní nepřenášejí.

Použijeme SQLite pro metadata a soubory/Git pro neměnné artefakty. Přijetí znamená změnu ukazatele na konkrétní ověřený artefakt, ne přepis právě běžícího procesu. Aktivaci provede správce, nový proces projde kontrolou zdraví a jednoduchým funkčním průchodem; teprve potom dostane provoz. Při chybě se ukazatel vrátí a spustí se poslední funkční verze.

V počátečním RSI není dovolena automatická změna databázového schématu. Díky tomu může rollback kódu pracovat se stejnými daty. Pozdější migrace budou mít vlastní zálohu a dopřednou/zpětnou kompatibilitu.

## 10. Jak prokázat rekurzivní přínos

Samotný rodokmen dvou generací dokládá rekurzivní provoz, nikoli rychlejší sebezdokonalování. Proto povedeme kontrolu:

- Větev A: původní agent opakovaně navrhuje zlepšení se stejným celkovým rozpočtem.
- Větev B: přijatá verze se v dalším kole stane novým autorem zlepšení.
- Obě dostanou srovnatelná zadání, stejný provider, nástroje, oprávnění a celkový rozpočet.
- Sledujeme schopnosti finálního agenta i počet přijatých zlepšení na rozpočet.
- Pořadí a několik nezávislých kampaní omezí vliv náhody. Rozšíření tvrzení závisí na výsledcích a nejistotě.

Pokud větev B není lepší, oznámíme „rekurzivní mechanismus funguje, jeho výhoda zatím neprokázána“. Pokud nepřibydou vyřešené úlohy, oznámíme „bez doloženého zlepšení schopností“. Zvyšovat verzi bez výsledku není úspěch experimentu.

## 11. První konkrétní backlog

1. Připnout současnou verzi 3.1.0 a zaznamenat čistou baseline testů.
2. Vytvořit rozhraní modelového providera a potvrdit skutečnou odpověď modelu.
3. Připravit 10 malých vývojových repozitářů s ověřenými chybami a neveřejnými hodnoticími testy.
4. Přidat nástroje čtení souboru, hledání v projektu, aplikace patche a běhu veřejného testu.
5. Implementovat izolovaný runner, limity, záznamy akcí a ukončení celé skupiny procesů.
6. Změřit původního agenta a vybrat konkrétní opakující se selhání.
7. Nechat agenta navrhnout jednu změnu svého kontextového nebo opravného postupu.
8. Spustit rodiče a kandidáta na shodných úlohách a zapsat rozdíly po úlohách.
9. Otestovat odmítnutí vadné změny, nepovoleného zápisu a padlé verze; nacvičit rollback.
10. Teprve potom sestavit plný dataset 20/20/20 a potvrzovací experiment.

První hypotéza k prověření: „Když agent po neúspěšném testu dostane přesně relevantní soubor a stručný strukturovaný výpis chyby, opraví více úloh v limitu tří volání.“ Kandidát upraví vlastní skládání kontextu. Úspěšnost se měří na opravovaných projektech; změna samotného testu NeuroPilotu by tento cíl nesplnila.

## 12. Dokončená první verze RSI

Za dokončené experimentální minimum považujeme: skutečný modelový agent, izolovaná pracovní kopie, kandidát vytvořený agentem, vnější měření, reprodukovatelný záznam, rozhodnutí a ověřený návrat. Za prokázané sebezdokonalení teprve nezávisle potvrzený přínos. Za prokázaný přínos rekurze navíc lepší výsledek oproti nerekurzivní kontrolní větvi při stejném rozpočtu.

## 13. Výzkumné podklady a jejich hranice

- Sakana AI, Darwin Gödel Machine, 30. 5. 2025: popisuje vlastní změny agentního kódu a empirické hodnocení kandidátů. Autoři také uvádějí případy falešných logů a manipulace s měřením. Pro tento návrh jde o motivaci pro nezávislý hodnotitel a archiv, nikoliv důkaz výsledků NeuroPilotu. https://sakana.ai/dgm/
- OpenAI, Why SWE-bench Verified no longer measures frontier coding capabilities, 23. 2. 2026: rozebírá kontaminaci benchmarku a problémy testů. Pro tento návrh jde o důvod ověřit vlastní úlohy a chránit čerstvé závěrečné měření. https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/

Konkrétní etapy, limity, počty úloh a rozhodovací pravidla výše jsou náš návrh pro NeuroPilot, nikoli převzaté nebo již prokázané výsledky těchto výzkumů.
