"""Only curated application messages may cross the HTTP/UI error boundary."""
PUBLIC_MESSAGES = {message: message for message in (
    'Datum musí mít formát YYYY-MM-DD.',
    'Import musí být objekt JSON.',
    'Požadavek musí být objekt JSON.',
    'Počet dní musí být 1–366.',
    'Stav úkolu musí být boolean.',
    'Odpověď musí být text.',
    'Neplatné záznamy návyku.',
    'Nejdřív se přihlas přes Continue with ChatGPT.',
    'Přihlas tento účet znovu.',
    'Přihlášení již čeká na dokončení.',
    'Povol využití předplatného v přihlášení ChatGPT.',
    'Vyber model z aktuálního seznamu.',
    'Vyber model z aktuálního katalogu Codexu.',
    'Vyber model Codexu v nastavení RSI.',
    'Codex CLI není nainstalován.',
    'Přihlas ChatGPT příkazem python -m rsi codex-login.',
    'Codex workspace routing is not supported by this gateway',
    'Unknown run', 'Unknown artifact', 'Unknown ChatGPT account',
    'Invalid account', 'Run init first', 'Another experiment is running',
    'No previous release', 'Only accepted artifacts can be promoted',
    'Artifact integrity failure',
)}
for collection in ('notes', 'tasks', 'habits'):
    for template in ('Neplatná kolekce {}.', 'Neplatný záznam v {}.', 'Neplatné nebo duplicitní ID v {}.'):
        message = template.format(collection)
        PUBLIC_MESSAGES[message] = message
for field in ('text', 'title'):
    message = f'Pole {field} musí obsahovat text (nejvýše 20 000 znaků).'
    PUBLIC_MESSAGES[message] = message


def public_error(error):
    # Do not stringify arbitrary exceptions: OS/SDK errors can contain paths,
    # response bodies or credentials. Return a trusted literal, never the input.
    message = error.args[0] if error.args and type(error.args[0]) is str else None
    return PUBLIC_MESSAGES.get(message, 'Operace se nezdařila. Ověř zadané údaje, konfiguraci a přihlášení.')
