"""Build the standalone research graphic and HTML from recorded JSON results."""
from pathlib import Path
import base64,json,html
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent
read=lambda n:json.loads((root/'results'/f'{n}.json').read_text())['result']
b,g,s=read('benchmark'),read('gates'),read('stress')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(1,3,figsize=(16,5),layout='constrained')
fig.suptitle('NeuroPilot: měření kontroleru a simulace pravidel — bez skutečného modelu',fontsize=17,fontweight='bold')
ax[0].bar(['Veřejný příklad','Všechny 3 případy'],[60-b['broken_tasks_not_detected_by_public_check'],b['broken_tasks_detected']],color=['#f3ad42','#16797b'])
ax[0].set_ylim(0,67);ax[0].set_ylabel('Odhalené připravené chyby z 60');ax[0].set_title('1. Pokrytí benchmarku')
for i,value in enumerate([23,60]):ax[0].text(i,value+1,str(value),ha='center',fontweight='bold')
for key,label,color in [('deterministic_four_new_wins','Bez kolísání','#16797b'),('nearly_deterministic_four_new_wins','2% kolísání výsledku','#d36b39')]:
 rows=[r for r in g['capability'] if r['scenario']==key]
 x=[r['repeats'] for r in rows];y=[r['both_splits_percent'] for r in rows]
 ax[1].plot(x,y,'o-',label=label,color=color,lw=2)
 for xx,yy in zip(x,y):ax[1].annotate(f'{yy:g} %',(xx,yy),xytext=(0,6),textcoords='offset points',ha='center',fontsize=9)
ax[1].set_yscale('log');ax[1].set_ylim(.01,240);ax[1].set_xticks([1,3,5]);ax[1].set_xlabel('Opakování na úlohu');ax[1].set_ylabel('Přijetí ve dvou sadách (%) · log');ax[1].set_title('2. Simulace čtyř zlepšených úloh');ax[1].legend(loc='lower left',fontsize=9)
x=[r['events'] for r in s['audit_scaling']];y=[r['median_status_ms'] for r in s['audit_scaling']]
ax[2].plot(x,y,'o-',color='#4856aa',lw=2)
for xx,yy in zip(x,y):ax[2].annotate(f'{yy:.1f} ms',(xx,yy),xytext=(0,7),textcoords='offset points',ha='center',fontsize=9)
ax[2].set_ylim(0,max(y)*1.25);ax[2].set_xlabel('Počet záznamů auditu');ax[2].set_ylabel('Medián čtení stavu (ms)');ax[2].set_title('3. Skutečný SQLite registr');ax[2].set_xticks([0,1000,10000],['0','1 000','10 000'])
for a in ax:a.grid(axis='y',alpha=.17);a.set_axisbelow(True)
fig.savefig(root/'research.png',dpi=140);plt.close(fig)
md=(root/'RESEARCH_REPORT.md').read_text()
# Render a small documented subset of Markdown without running scripts or loading URLs.
import re
out=[];in_code=False;in_table=False
for line in md.splitlines():
 if line.startswith('```'):
  if in_table:out.append('</tbody></table></div>');in_table=False
  out.append('</code></pre>' if in_code else '<pre><code>');in_code=not in_code;continue
 if in_code:out.append(html.escape(line)+'\n');continue
 if line.startswith('|'):
  if re.fullmatch(r'[| :\-]+',line):continue
  cells=[c.strip() for c in line.strip('|').split('|')]
  if not in_table:out.append('<div class="table"><table><tbody>');in_table=True
  out.append('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in cells)+'</tr>');continue
 if in_table:out.append('</tbody></table></div>');in_table=False
 escaped=html.escape(line)
 escaped=re.sub(r'`([^`]+)`',r'<code>\1</code>',escaped)
 escaped=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',escaped)
 if line.startswith('# '):out.append('<h1>'+escaped[2:]+'</h1>')
 elif line.startswith('## '):out.append('<h2>'+escaped[3:]+'</h2>')
 elif line.startswith('### '):out.append('<h3>'+escaped[4:]+'</h3>')
 elif line.startswith('- '):out.append('<p class="item">• '+escaped[2:]+'</p>')
 elif line.startswith('!['):out.append('<img alt="Tři grafy benchmarku, simulace bran a škálování registru" src="data:image/png;base64,'+base64.b64encode((root/'research.png').read_bytes()).decode()+'">')
 elif line:out.append('<p>'+escaped+'</p>')
if in_table:out.append('</tbody></table></div>')
page='''<!doctype html><html lang="cs"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NeuroPilot · výzkumná zpráva</title><style>
body{margin:0;background:#f2f4f7;color:#172333;font:17px/1.7 system-ui,sans-serif}main{max-width:1120px;margin:auto;padding:44px 28px 80px;background:#fff}h1{font-size:38px;line-height:1.2;max-width:900px}h2{margin-top:44px;font-size:25px;border-top:1px solid #dbe2e9;padding-top:24px}h3{font-size:20px}p{max-width:980px}.tag{color:#16797b;text-transform:uppercase;font-weight:700;font-size:13px;letter-spacing:.12em}.table{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:15px}td{border-bottom:1px solid #dbe2e9;padding:12px;vertical-align:top}tr:first-child{background:#e7eef4;font-weight:700}code{font-size:.9em;background:#edf1f5;padding:2px 5px;border-radius:4px}pre{background:#172333;color:#edf1f5;padding:18px;overflow:auto;font-size:14px}pre code{background:none;padding:0}img{width:100%;height:auto;margin:20px 0}.item{margin:8px 0}@media(max-width:600px){main{padding:24px 15px}h1{font-size:29px}body{font-size:16px}}@media print{body,main{background:white}main{padding:0}h2{break-after:avoid}tr,img{break-inside:avoid}}
</style><main><div class="tag">Experimentální výzkum · 4. října 2026</div>'''+''.join(out)+'</main></html>'
(root/'report.html').write_text(page)
print(root/'report.html')
