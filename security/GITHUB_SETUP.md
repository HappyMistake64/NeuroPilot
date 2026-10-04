# Dokončení ochrany repozitáře na GitHubu

Kontrola 4. 10. 2026: repozitář je veřejný, `main` není chráněná, seznam rulesetů
je prázdný a soukromé hlášení zranitelností je zapnuté. Připojený GitHub App
neumožňuje správu repozitáře: čtení nastavení Actions i CodeQL vrací HTTP 403.
Údaj `permissions.admin=true` popisuje uživatele, nezaručuje práva této integrace.
Následující nastavení proto **nebyla automaticky zapnuta**. Neposílej žádný token.

## Ochrana main (lze z telefonu)

Po úspěšném CI a sloučení bezpečnostního PR otevři
[Settings → Rules → Rulesets](https://github.com/HappyMistake64/NeuroPilot/settings/rules).
Přes **New ruleset → Import a ruleset** importuj
[main-ruleset.json](main-ruleset.json) a ověř stav **Active** a větev `main`.
Soubor jde stáhnout tlačítkem Raw/Download na GitHubu. Import neposkytuje žádné
přihlašovací údaje ani přístup jiné osobě.

Pravidla vyžadují PR, vyřešené diskuse, aktuální větev a úspěšné kontroly:
`tests`, `Dependency audit`, `Secret scan`, `CodeQL (python)` a
`CodeQL (javascript-typescript)`. Kontroly jsou svázané s GitHub Actions App
(ID 15368). Zakazují force-push a smazání `main`, nemají bypass výjimky.
Před uložením ověř skutečné názvy dokončených kontrol v bezpečnostním PR.

Pro jediného vlastníka je počet povinných schválení **0**: GitHub nedovoluje
schválit vlastní PR. Změna stále vyžaduje PR a kontrolní běhy. Až budeš mít
nezávislého spolupracovníka, nastav alespoň jedno schválení a review vlastníka
kódu. Soubor CODEOWNERS sám tuto povinnost nevynucuje.

## Ochrana přihlašovacích údajů

V [Settings → Code security](https://github.com/HappyMistake64/NeuroPilot/settings/security_analysis)
ověř/zapni Secret scanning, Push protection, Dependabot alerts a Dependabot
security updates. Zachovej zapnuté Private vulnerability reporting. Dostupné
názvy voleb se mohou podle GitHub UI lišit. V tomto PR dodané CodeQL používá
advanced setup; pokud je zapnuté default setup, nepoužívej současně obě konfigurace.

## Oprávnění GitHub Actions a účtu

V [Settings → Actions → General](https://github.com/HappyMistake64/NeuroPilot/settings/actions)
nastav výchozí Workflow permissions na **Read repository contents**, vypni
**Allow GitHub Actions to create and approve pull requests** a požaduj schválení
workflow od externích přispěvatelů. CodeQL má explicitně pouze potřebné
`security-events: write` v konkrétním jobu.

Na osobním GitHub účtu používej passkey nebo 2FA a uchovej obnovovací kódy mimo
repozitář. Zkontroluj spolupracovníky, instalované GitHub Apps a deploy keys;
jejich seznam ani změny nejsou součástí oprávnění tohoto připojení.

Nakonec znovu otevři `main` a ověř, že GitHub zobrazuje ochranu větve. Úspěšný PR
ani přítomnost tohoto dokumentu samy nezapínají administrativní nastavení.
