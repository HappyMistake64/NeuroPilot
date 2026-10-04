"""60 authored pilot tasks. References are evaluator fixtures, never agent input."""
# key, signature, specification, broken expression, reference expression, [(args, expected)]
DEV = [
('absolute','x','Return the absolute value of integer x.','x','abs(x)',[([-3],3),([0],0),([-19],19)]),
('clamp','x, lo, hi','Clamp x to inclusive [lo, hi]; assume lo <= hi.','min(x, hi)','max(lo, min(x, hi))',[([20,0,10],10),([-4,0,10],0),([4,0,10],4)]),
('inclusive_sum','n','Sum all integers from 0 to nonnegative n, inclusive.','sum(range(n))','sum(range(n+1))',[([3],6),([0],0),([10],55)]),
('median','xs','Median of a nonempty numeric list; average the middle two for even length.','sorted(xs)[len(xs)//2]','(sorted(xs)[(len(xs)-1)//2]+sorted(xs)[len(xs)//2])/2',[([[3,1,2]],2),([[1,9]],5),([[10,2,4,8]],6)]),
('factorial','n','Factorial of integer n >= 0.','sum(range(1,n+1))','math.prod(range(1,n+1))',[([3],6),([0],1),([5],120)]),
('evens','xs','Return even integers from xs in original order.','[x for x in xs if x%2]','[x for x in xs if x%2==0]',[([[1,2,4]], [2,4]),([[-2,-1,0]],[-2,0]),([[]],[])]),
('gcd','a, b','Return the nonnegative greatest common divisor, including zero arguments.','max(a,b)','math.gcd(a,b)',[([6,9],3),([0,12],12),([-8,12],4)]),
('power','x, n','Return x raised to integer n >= 0.','x*n','x**n',[([2,3],8),([7,0],1),([-2,3],-8)]),
('positive_count','xs','Count numbers strictly greater than zero.','sum(x>=0 for x in xs)','sum(x>0 for x in xs)',[([[-1,1]],1),([[0,0,2]],1),([[]],0)]),
('dot','xs, ys','Dot product of equal-length numeric lists.','sum(xs)+sum(ys)','sum(x*y for x,y in zip(xs,ys))',[([[1,2],[3,4]],11),([[],[]],0),([[-1,2],[2,-3]],-8)]),
('ceil_div','a, b','Ceiling of a/b for integer a and positive integer b.','a//b','-(-a//b)',[([6,3],2),([7,3],3),([-7,3],-2)]),
('percent','part, total','Return percentage part/total * 100, or None for total zero.','part/total','None if total==0 else part/total*100',[([1,4],25),([0,0],None),([5,10],50)]),
('angle','x','Normalize integer angle to [0,359].','x','x%360',[([90],90),([-10],350),([720],0)]),
('distance','a, b','Euclidean distance between 2D points a and b.','abs(a[0]-b[0])+abs(a[1]-b[1])','math.hypot(a[0]-b[0],a[1]-b[1])',[([[0,0],[0,4]],4),([[0,0],[3,4]],5),([[1,1],[1,1]],0)]),
('prefix_sum','xs','Return inclusive cumulative sums, one result per input.','[sum(xs[:i]) for i in range(len(xs))]','[sum(xs[:i+1]) for i in range(len(xs))]',[([[1,2,3]],[1,3,6]),([[]],[]),([[-1,1,2]],[-1,0,2])]),
('extrema','xs','Return [minimum,maximum], or [] for empty input.','[max(xs),min(xs)]','[min(xs),max(xs)] if xs else []',[([[3,1,7]],[1,7]),([[]],[]),([[4]],[4,4])]),
('sign','x','Return -1, 0, or 1 according to sign of x.','1 if x>=0 else -1','(x>0)-(x<0)',[([3],1),([0],0),([-3],-1)]),
('triangular','n','Return nth triangular number for n >= 0.','n*n','n*(n+1)//2',[([1],1),([5],15),([0],0)]),
('multiple_floor','x, m','Largest multiple of positive m <= integer x.','round(x/m)*m','(x//m)*m',[([7,3],6),([8,3],6),([-1,3],-3)]),
('safe_division','a, b','Return a/b or None when b is zero.','a/b','None if b==0 else a/b',[([6,3],2),([2,0],None),([-3,2],-1.5)]),
]
VALIDATION = [
('reverse_words','text','Reverse whitespace-separated words; output one ASCII space between words.','text[::-1]','" ".join(text.split()[::-1])',[(['a b'],'b a'),([' one   two\nthree '],'three two one'),([''],'')]),
('vowels','text','Count ASCII vowels aeiou, case-insensitive.','sum(c in "aeiou" for c in text)','sum(c.lower() in "aeiou" for c in text)',[(['abc'],1),(['AEIOU'],5),(['rhythm'],0)]),
('palindrome','text','Compare alphanumeric Unicode characters case-insensitively, ignoring others.','text==text[::-1]','(lambda s:s==s[::-1])("".join(c.casefold() for c in text if c.isalnum()))',[(['aba'],True),(['A man, a plan, a canal: Panama!'],True),(['abc'],False)]),
('slug','text','Lowercase ASCII words, replace each run of non [a-z0-9] with a dash, trim outer dashes.','text.lower().replace(" ","-")','re.sub("[^a-z0-9]+","-",text.lower()).strip("-")',[(['Hello World'],'hello-world'),(['  A!!B  '],'a-b'),(['!!!'],'')]),
('initials','text','Uppercase initial of each whitespace-separated word, concatenated.','text[0].upper()','"".join(w[0].upper() for w in text.split())',[(['alice'],'A'),([' alice bob '],'AB'),([''],'')]),
('suffix','text, suffix','Remove exactly one matching nonempty suffix; otherwise return text unchanged.','text.replace(suffix, "")','text[:-len(suffix)] if suffix and text.endswith(suffix) else text',[(['abc.txt','.txt'],'abc'),(['txt.txt.txt','.txt'],'txt.txt'),(['abc',''],'abc')]),
('truncate','text, n','Return at most n characters, n >= 0.','text[:n-1]','text[:n]',[(['abcd',2],'ab'),(['abc',0],''),(['ab',9],'ab')]),
('collapse_spaces','text','Split on any whitespace and join with one ASCII space.','text.strip()','" ".join(text.split())',[([' hi '],'hi'),(['a\t b\n c'],'a b c'),([''],'')]),
('anagram','a, b','Case-insensitive anagrams ignoring whitespace, preserving all other characters.','a==b','sorted("".join(a.casefold().split()))==sorted("".join(b.casefold().split()))',[(['ab','ba'],True),(['Dormitory','dirty room'],True),(['aa','a'],False)]),
('count_substring','text, sub','Count non-overlapping substring occurrences; empty substring counts as zero.','text.count(sub)','text.count(sub) if sub else 0',[(['aaaa','aa'],2),(['abc',''],0),(['ababab','ab'],3)]),
('is_ascii_digits','text','True only for nonempty strings of ASCII digits 0-9.','text.isdigit()','bool(text) and all("0"<=c<="9" for c in text)',[(['012'],True),([''],False),(['²'],False)]),
('title_words','text','Capitalize first letter and lowercase remainder of each whitespace-separated word.','text.upper()','" ".join(w[:1].upper()+w[1:].lower() for w in text.split())',[(['hELLO'],'Hello'),([' hELLO   wORLD '],'Hello World'),([''],'')]),
('common_prefix','a, b','Return the longest shared character prefix.','a if a in b else ""','a[:next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y),min(len(a),len(b)))]',[(['abc','abd'],'ab'),(['ab','abcd'],'ab'),(['','x'],'')]),
('mask','text, n','Replace all except final n characters with *, n >= 0.','"*"*n+text[-n:]','"*"*max(0,len(text)-n)+(text[-n:] if n else "")',[(['abcd',2],'**cd'),(['abc',0],'***'),(['ab',5],'ab')]),
('csv_trim','text','Split on commas, trim each field, preserve empty fields; no CSV quoting.','text.split()','[x.strip() for x in text.split(",")]',[(['a,b'],['a','b']),([' a, ,b '],['a','','b']),([''],[''])]),
('first_unique','text','Return first character occurring exactly once, or None.','text[0] if text else None','next((c for c in text if text.count(c)==1),None)',[(['abc'],'a'),(['aabbc'],'c'),(['aabb'],None)]),
('snake_to_camel','text','Drop empty underscore-separated segments; preserve first segment; capitalize start of subsequent segments.','text.replace("_","")','(lambda w:w[0]+"".join(x[:1].upper()+x[1:] for x in w[1:]) if w else "")([x for x in text.split("_") if x])',[(['hello_world'],'helloWorld'),(['_one__two_'],'oneTwo'),(['___'],'')]),
('strip_prefix','text, prefix','Remove exactly one matching prefix; leave nonmatching text unchanged.','text.replace(prefix, "")','text[len(prefix):] if text.startswith(prefix) else text',[(['pretext','pre'],'text'),(['prepre','pre'],'pre'),(['xpre','pre'],'xpre')]),
('line_count','text','Count lines using str.splitlines; empty string has zero lines.','len(text.split("\\n"))','len(text.splitlines())',[(['a\nb'],2),([''],0),(['a\n'],1)]),
('ascii_shift','text, k','Caesar-shift ASCII lowercase letters by k modulo 26; leave other characters unchanged.','text','"".join(chr((ord(c)-97+k)%26+97) if "a"<=c<="z" else c for c in text)',[(['abc',1],'bcd'),(['z A!',2],'b A!'),(['a',-1],'z')]),
]
FINAL = [
('stable_unique','xs','Remove duplicates of hashable values, preserving first occurrence.','sorted(set(xs))','list(dict.fromkeys(xs))',[([[1,2,1]],[1,2]),([[3,1,3,2]],[3,1,2]),([[]],[])]),
('flatten_one','xs','Flatten exactly one level of nested lists.','xs','[v for row in xs for v in row]',[([[[1,2],[3]]],[1,2,3]),([[[1],[],[2]]],[1,2]),([[]],[])]),
('chunks','xs, n','Split list into chunks of positive size n, keep short final chunk.','[xs[:n]]','[xs[i:i+n] for i in range(0,len(xs),n)]',[([[1,2],2],[[1,2]]),([[1,2,3,4,5],2],[[1,2],[3,4],[5]]),([[],3],[])]),
('rotate','xs, n','Rotate list right by integer n; empty input returns [].','xs[n:]+xs[:n]','xs[-(n%len(xs)):]+xs[:-(n%len(xs))] if xs and n%len(xs) else xs[:]',[([[1,2,3],1],[3,1,2]),([[1,2,3],-1],[2,3,1]),([[],9],[])]),
('frequencies','xs','Return counts for string list elements.','{x:1 for x in xs}','{x:xs.count(x) for x in xs}',[([['a','b']],{'a':1,'b':1}),([['a','a','b']],{'a':2,'b':1}),([[]],{})]),
('intersection','a, b','Unique common integers sorted ascending.','a+b','sorted(set(a)&set(b))',[([[1,2],[2,3]],[2]),([[2,2,1],[2,1]],[1,2]),([[],[1]],[])]),
('difference','a, b','Items from a absent in b; preserve order and duplicates from a.','[x for x in a if x in b]','[x for x in a if x not in b]',[([[1,2],[2]],[1]),([[3,1,3],[1]],[3,3]),([[],[]],[])]),
('merge_maps','a, b','Merge dictionaries with b taking precedence.','dict(b,**a)','dict(a,**b)',[([{'a':1},{'b':2}],{'a':1,'b':2}),([{'a':1},{'a':3}],{'a':3}),([{},{}],{})]),
('invert_groups','mapping','Map each string value to sorted list of corresponding original keys.','{v:k for k,v in mapping.items()}','{v:sorted(k for k,x in mapping.items() if x==v) for v in mapping.values()}',[([{'a':'x'}],{'x':['a']}),([{'b':'x','a':'x','c':'y'}],{'x':['a','b'],'y':['c']}),([{}],{})]),
('without_null','mapping','Remove dictionary entries whose value is None, keep other falsey values.','{k:v for k,v in mapping.items() if v}','{k:v for k,v in mapping.items() if v is not None}',[([{'a':1,'b':None}],{'a':1}),([{'a':0,'b':False,'c':''}],{'a':0,'b':False,'c':''}),([{}],{})]),
('transpose','rows','Transpose rectangular nested list; empty list returns [].','rows[::-1]','[list(x) for x in zip(*rows)]',[([[[1,2],[3,4]]],[[1,3],[2,4]]),([[[1,2,3]]],[[1],[2],[3]]),([[]],[])]),
('zip_map','keys, values','Map keys to corresponding values, stop at shortest list; last duplicate wins.','{k:values[0] for k in keys}','dict(zip(keys,values))',[([['a'],[1]],{'a':1}),([['a','b','a'],[1,2,3]],{'a':3,'b':2}),([['x'],[]],{})]),
('pairwise','xs','Return adjacent pairs as lists; fewer than two elements returns [].','[[xs[0],x] for x in xs[1:]]','[[xs[i],xs[i+1]] for i in range(len(xs)-1)]',[([[1,2]],[[1,2]]),([[1,2,3]],[[1,2],[2,3]]),([[]],[])]),
('partition','xs, threshold','Return [items below threshold, items >= threshold], preserving order.','[xs,[]]','[[x for x in xs if x<threshold],[x for x in xs if x>=threshold]]',[([[1,3],2],[[1],[3]]),([[2,0,2],2],[[0],[2,2]]),([[],0],[[],[]])]),
('indices','xs, value','Return all indices where xs equals value.','[xs.index(value)] if value in xs else []','[i for i,x in enumerate(xs) if x==value]',[([[1,2],2],[1]),([[2,1,2],2],[0,2]),([[],2],[])]),
('sorted_records','rows, key','Stable ascending sort of dictionaries by existing numeric key.','rows','sorted(rows,key=lambda x:x[key])',[([[{'n':1},{'n':2}],'n'],[{'n':1},{'n':2}]),([[{'n':2,'s':'a'},{'n':1,'s':'b'},{'n':2,'s':'c'}],'n'],[{'n':1,'s':'b'},{'n':2,'s':'a'},{'n':2,'s':'c'}]),([[],'n'],[])]),
('take_last','xs, n','Return final n items, n >= 0; n=0 returns [].','xs[-n:]','xs[-n:] if n else []',[([[1,2,3],2],[2,3]),([[1,2],0],[]),([[1],4],[1])]),
('dict_select','mapping, keys','Keep only existing requested keys.','{k:mapping[k] for k in keys}','{k:mapping[k] for k in keys if k in mapping}',[([{'a':1,'b':2},['a']],{'a':1}),([{'a':1},['z','a']],{'a':1}),([{},[]],{})]),
('compact','xs','Remove only None elements, preserve zero, false and empty strings.','[x for x in xs if x]','[x for x in xs if x is not None]',[([[1,None,2]],[1,2]),([[0,False,'',None]],[0,False,'']),([[]],[])]),
('alternating','a, b','Interleave a and b starting with a; append leftovers preserving order.','a+b','[row[i] for j in range(max(len(a),len(b))) for i,row in [(j,a),(j,b)] if i<len(row)]',[([[1],[2]],[1,2]),([[1,3,5],[2]],[1,2,3,5]),([[],[2,4]],[2,4])]),
]

def catalog():
    tasks=[]
    for split,rows in (('dev',DEV),('validation',VALIDATION),('final',FINAL)):
        for index,(key,params,description,broken,reference,cases) in enumerate(rows,1):
            prefix='import math\nimport re\n\ndef solve('+params+'):\n    return '
            tasks.append({'id':split+'-'+str(index).zfill(3),'family':key,'split':split,'instruction':description+' Implement solve in solution.py. Inputs are JSON-compatible. Do not change the public test.',
                'files':{'solution.py':prefix+broken+'\n'},'entrypoint':'solve',
                'public':[{'args':cases[0][0],'expected':cases[0][1]}],
                'hidden':[{'args':args,'expected':expected} for args,expected in cases[1:]],
                'reference':prefix+reference+'\n'})
    return tasks
