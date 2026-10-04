'use strict';
const $ = id => document.getElementById(id);
async function api(path, method = 'GET', data) {
  const response = await fetch(path, {method, headers: {'Content-Type': 'application/json'}, body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `Chyba ${response.status}`);
  return result;
}
function node(tag, text) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; return el; }
function action(text, handler) {
  const btn = node('button', text);
  btn.type = 'button';
  btn.onclick = async () => { btn.disabled = true; try { await handler(); $('status').textContent = ''; } catch (e) { $('status').textContent = e.message; } finally { btn.disabled = false; } };
  return btn;
}
function today() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; }
async function refresh() {
  const [notes, tasks, habits] = await Promise.all([api('/notes'), api('/tasks'), api('/habits')]);
  $('notes').replaceChildren(...notes.map(n => {
    const card = node('article'); card.append(node('strong', n.text), node('pre', n.ai || ''), action('Smazat', async () => { await api(`/notes/${encodeURIComponent(n.id)}`, 'DELETE'); await refresh(); })); return card;
  }));
  $('tasks').replaceChildren(...tasks.map(t => {
    const item = node('li'); const label = node('span', t.text); if (t.done) label.style.textDecoration = 'line-through';
    item.append(action(t.done ? '✓ Hotovo' : 'Dokončit', async () => { await api(`/tasks/${encodeURIComponent(t.id)}/toggle`, 'POST', {}); await refresh(); }), label, action('Smazat', async () => { await api(`/tasks/${encodeURIComponent(t.id)}`, 'DELETE'); await refresh(); })); return item;
  }));
  const cards = await Promise.all(habits.map(async h => {
    const card = node('article'); const stats = await api(`/habits/${encodeURIComponent(h.id)}/stats/7`);
    card.append(node('strong', h.title), node('p', `Posledních 7 dní: ${stats.filter(x => x.done).length}/7`), action(h.records.includes(today()) ? '✓ Dnes splněno' : 'Splnit dnes', async () => { await api(`/habits/${encodeURIComponent(h.id)}/toggle`, 'POST', {date: today()}); await refresh(); }), action('Smazat', async () => { await api(`/habits/${encodeURIComponent(h.id)}`, 'DELETE'); await refresh(); })); return card;
  }));
  $('habits').replaceChildren(...cards);
}
function bind(id, handler) {
  $(id).onclick = async () => { $(id).disabled = true; $('status').textContent = ''; try { await handler(); } catch (e) { $('status').textContent = e.message; } finally { $(id).disabled = false; } };
}
bind('ask', async () => { const result = await api('/think', 'POST', {text: $('note').value}); $('out').textContent = result.note.ai; await refresh(); });
bind('addTask', async () => { await api('/tasks', 'POST', {text: $('taskInput').value}); $('taskInput').value = ''; await refresh(); });
bind('addHabit', async () => { await api('/habits', 'POST', {title: $('habitTitle').value}); $('habitTitle').value = ''; await refresh(); });
bind('importData', async () => {
  const file = $('importFile').files[0]; if (!file) throw new Error('Vyber soubor JSON.');
  const data = JSON.parse(await file.text());
  if (!confirm('Import nahradí současné poznámky, úkoly a návyky. Pokračovat?')) return;
  await api('/import', 'POST', data); await refresh(); $('status').textContent = 'Data byla importována.';
});
refresh().catch(e => { $('status').textContent = e.message; });
