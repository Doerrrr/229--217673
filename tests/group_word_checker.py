"""Exact direct-product matrix word checker; contains no synthesis or fixtures."""

def checks(q,result):
    out=dict(product=False,target=False)
    try:
        if type(result) is not dict or set(result)!={'word','products'}:return out
        word=result['word'];products=result['products'];g=len(q['generators'])
        if type(word) is not list or len(word)>q['max_length'] or any(type(x)is not int or not 1<=abs(x)<=g for x in word):return out
        if type(products) is not list or len(products)!=len(q['moduli']):return out
        calculated=[]
        for lane,p in enumerate(q['moduli']):
            current=[[1,0],[0,1]]
            for letter in word:
                a,b,c,d=q['generators'][abs(letter)-1][lane]
                right=[[a,b],[c,d]] if letter>0 else [[d%p,(-b)%p],[(-c)%p,a%p]]
                current=[[sum(current[i][k]*right[k][j] for k in range(2))%p for j in range(2)] for i in range(2)]
            calculated.append([current[0][0],current[0][1],current[1][0],current[1][1]])
        if any(type(row)is not list or len(row)!=4 or any(type(x)is not int or not 0<=x<p for x in row) for row,p in zip(products,q['moduli'])):return out
        out['product']=products==calculated
        out['target']=out['product'] and products==q['targets']
    except (TypeError,KeyError,ValueError,IndexError):pass
    return out
