import numpy as np, pandas as pd, random
import sys
# Usage : python scripts/generer_dataset.py [graine] [nb_entreprises] [fichier_sortie]
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 42
N_COMP = int(sys.argv[2]) if len(sys.argv) > 2 else 30
OUT = sys.argv[3] if len(sys.argv) > 3 else "data/dataset_extraction_annexes_financieres.csv"
rng=np.random.default_rng(SEED); random.seed(SEED)

companies=[("Valmorel Industries","Industrie","France"),("Ostrava Logistique","Transport & Logistique","France"),
("Brennac Santé","Santé","France"),("Kervalis Énergie","Énergie","France"),("Lumeris Retail","Distribution","France"),
("Saveron Foods","Agroalimentaire","France"),("Corvane Telecom","Télécoms","Belgique"),("Altheon Software","Technologie","France"),
("Delmare Matériaux","Matériaux","Espagne"),("Fenwick & Rowe plc","Industrie","Royaume-Uni"),("Nordhaven Shipping","Transport & Logistique","Pays-Bas"),
("Quintel Pharma AG","Santé","Suisse"),("Ravensby Utilities","Énergie","Royaume-Uni"),("Solvane Chimie","Matériaux","France"),
("Tessaro Moda","Distribution","Italie"),("Ulmera Hôtels","Loisirs & Hôtellerie","France"),("Verancia Immobilier","Immobilier","France"),
("Wexford Systems Inc.","Technologie","États-Unis"),("Ystral Aéro","Industrie","France"),("Zephyra Cosmétiques","Biens de consommation","France"),
("Arcturo Bebidas","Agroalimentaire","Espagne"),("Belvedan Médias","Médias","France"),("Calderon Steel","Matériaux","Allemagne"),
("Dravik Automotive","Automobile","Allemagne"),("Elmsworth Leisure","Loisirs & Hôtellerie","Royaume-Uni"),("Fiorano Ceramiche","Matériaux","Italie"),
("Grenvale Pharma Inc.","Santé","États-Unis"),("Hallbrook Retail Corp.","Distribution","États-Unis"),("Isarta Ingénierie","Industrie","France"),
("Juvence Bio","Santé","France")]
cur_of={"France":"EUR","Belgique":"EUR","Espagne":"EUR","Italie":"EUR","Pays-Bas":"EUR","Allemagne":"EUR",
"Royaume-Uni":"GBP","Suisse":"CHF","États-Unis":"USD"}
std_of=lambda c:"US GAAP" if c=="États-Unis" else "IFRS"
lang_of=lambda c:"FR" if c in("France","Belgique") else "EN"
analysts={f"AN-0{i}":(sp,er) for i,(sp,er) in enumerate([(1.0,1.0),(0.85,1.3),(1.2,0.7),(0.95,1.0),(1.1,0.8),(0.8,1.6)],1)}

labels={ # field_code: (section, FR label, EN label, kind)
"CA_SEG_1":("Information sectorielle","Chiffre d'affaires – Segment 1","Revenue – Segment 1","flow"),
"CA_SEG_2":("Information sectorielle","Chiffre d'affaires – Segment 2","Revenue – Segment 2","flow"),
"CA_SEG_3":("Information sectorielle","Chiffre d'affaires – Segment 3","Revenue – Segment 3","flow"),
"CA_TOTAL":("Information sectorielle","Chiffre d'affaires consolidé","Total revenue","flow"),
"CA_ZONE_EUROPE":("Information sectorielle","CA – Europe","Revenue – Europe","flow"),
"CA_ZONE_AMERIQUES":("Information sectorielle","CA – Amériques","Revenue – Americas","flow"),
"CA_ZONE_RDM":("Information sectorielle","CA – Asie & reste du monde","Revenue – Asia & RoW","flow"),
"DETTE_OBLIGATAIRE":("Dettes financières","Emprunts obligataires","Bonds","stock"),
"DETTE_BANCAIRE":("Dettes financières","Emprunts bancaires","Bank borrowings","stock"),
"DETTE_LOCATIVE":("Dettes financières","Dettes de location","Lease liabilities","stock"),
"DETTE_BRUTE":("Dettes financières","Endettement financier brut","Gross financial debt","stock"),
"TRESORERIE":("Dettes financières","Trésorerie et équivalents","Cash and cash equivalents","stock"),
"DETTE_NETTE":("Dettes financières","Endettement financier net","Net debt","stock"),
"ECHEANCE_MOINS_1AN":("Dettes financières","Échéance < 1 an","Due within 1 year","stock"),
"ECHEANCE_1_5ANS":("Dettes financières","Échéance 1 à 5 ans","Due in 1-5 years","stock"),
"ECHEANCE_PLUS_5ANS":("Dettes financières","Échéance > 5 ans","Due after 5 years","stock"),
"TAUX_MOYEN_DETTE":("Dettes financières","Taux d'intérêt moyen","Average interest rate","rate"),
"LOC_COURANT":("Contrats de location","Dettes de location – part courante","Lease liabilities – current","stock"),
"LOC_NON_COURANT":("Contrats de location","Dettes de location – part non courante","Lease liabilities – non-current","stock"),
"LOC_INTERETS":("Contrats de location","Charge d'intérêts sur dettes de location","Interest expense on leases","flow"),
}
sec_label={"FR":{"Information sectorielle":"Information sectorielle","Dettes financières":"Dettes financières","Contrats de location":"Contrats de location"},
"EN":{"Information sectorielle":"Segment information","Dettes financières":"Borrowings","Contrats de location":"Leases"}}
seg_names={"FR":"Segment","EN":"Segment"}

def fmt(v,lang,scale):
    # v in display units (millions or thousands)
    neg=v<0; a=abs(v)
    s=f"{a:,.1f}" if scale=="millions" else f"{a:,.0f}"
    if lang=="FR": s=s.replace(",","§").replace(".",",").replace("§"," ")
    return f"({s})" if neg else s

def transpose(v,nd=1):
    s=f"{abs(v):.{nd}f}"; d=[i for i,ch in enumerate(s) if ch.isdigit()]
    for _ in range(10):
        i=rng.integers(0,len(d)-1)
        a,b=d[i],d[i+1]
        if s[a]!=s[b]:
            l=list(s); l[a],l[b]=l[b],l[a]; return float("".join(l))*(1 if v>=0 else -1)
    return round(v+1,1)

reports=[]; ci=list(range(N_COMP)); two=set(rng.choice(N_COMP,N_COMP//3,replace=False))
rid=1
for c in ci:
    for fy in ([2024,2025] if c in two else [int(rng.choice([2024,2025],p=[.3,.7]))]):
        reports.append((f"RPT-{rid:03d}",c,fy)); rid+=1

rows=[]; base_rev={}; comp_style={}
LAYOUTS=list(rng.permutation(["simple"]*9+["multi-colonnes N/N-1"]*12+["imbriqué"]*6+["scanné/image"]*3))
for rep,c,fy in reports:
    name,sector,country=companies[c]; lang=lang_of(country); cur=cur_of[country]
    if c not in base_rev: base_rev[c]=float(np.exp(rng.normal(np.log(2500),1.1)))
    rev=base_rev[c]*(1 if fy==2024 else 1+rng.normal(.05,.06))
    if c not in comp_style:
        comp_style[c]=("milliers" if (rev<1500 and rng.random()<.6) or rng.random()<.15 else "millions",
                       LAYOUTS[c])
    scale,layout=comp_style[c]
    div=1 if scale=="millions" else 1000
    pages=int(np.clip(rng.normal(150+rev/120,35),110,320))
    q=lambda x: round(x,1) if scale=="millions" else round(x*1000)/1000  # rounding in display unit, value in M
    # revenue
    sh=rng.dirichlet([4,3,2]); segs=[q(rev*s) for s in sh]; tot=round(sum(segs),3)
    zs=rng.dirichlet([5,2.5,2]); z=[q(rev*s) for s in zs[:2]]; z.append(round(tot-sum(z),3))
    # debt
    lev=rng.uniform(.15,1.1); gross=rev*lev; lshare=rng.uniform(.08,.35)
    bshare=rng.uniform(.3,.75)*(1-lshare) if rev>800 else rng.uniform(0,.3)*(1-lshare)
    lease=q(gross*lshare); bond=q(gross*bshare); bank=q(gross-lease-bond); gross_v=round(bond+bank+lease,3)
    cash=q(rev*rng.uniform(.04,.28)); net=round(gross_v-cash,3)
    m=rng.dirichlet([2,4,2.5]); m1=q(gross_v*m[0]); m2=q(gross_v*m[1]); m3=round(gross_v-m1-m2,3)
    rate=round(rng.uniform(1.4,6.3)+(1.0 if cur in("USD","GBP") else 0),2)
    lc=q(lease*rng.uniform(.15,.3)); lnc=round(lease-lc,3); lint=q(lease*rng.uniform(.025,.06))
    vals={"CA_SEG_1":segs[0],"CA_SEG_2":segs[1],"CA_SEG_3":segs[2],"CA_TOTAL":tot,
      "CA_ZONE_EUROPE":z[0],"CA_ZONE_AMERIQUES":z[1],"CA_ZONE_RDM":z[2],
      "DETTE_OBLIGATAIRE":bond,"DETTE_BANCAIRE":bank,"DETTE_LOCATIVE":lease,"DETTE_BRUTE":gross_v,
      "TRESORERIE":cash,"DETTE_NETTE":net,"ECHEANCE_MOINS_1AN":m1,"ECHEANCE_1_5ANS":m2,"ECHEANCE_PLUS_5ANS":m3,
      "TAUX_MOYEN_DETTE":rate,"LOC_COURANT":lc,"LOC_NON_COURANT":lnc,"LOC_INTERETS":lint}
    # rounding gap published in ~8% of reports on a total
    if rng.random()<.08:
        k=rng.choice(["CA_TOTAL","DETTE_BRUTE"]); vals[k]=round(vals[k]+(0.1 if scale=="millions" else 0.001)*rng.choice([-1,1]),3)
    an=list(analysts)[rng.integers(0,6)]; sp,er=analysts[an]
    notes={"Information sectorielle":int(rng.integers(3,7)),"Dettes financières":int(rng.integers(18,27)),"Contrats de location":int(rng.integers(10,18))}
    pg={s:int(pages*f+rng.integers(-6,6)) for s,f in [("Information sectorielle",.52),("Dettes financières",.68),("Contrats de location",.62)]}
    d0=pd.Timestamp(f"{fy+1}-03-01")+pd.Timedelta(days=int(rng.integers(0,200))) if fy==2025 else pd.Timestamp("2026-01-12")+pd.Timedelta(days=int(rng.integers(0,60)))
    seen=set()
    for fc,(sec,lfr,len_,kind) in labels.items():
        true=vals[fc]
        raw=f"{true:.2f} %".replace(".",",") if kind=="rate" and lang=="FR" else (f"{true:.2f}%" if kind=="rate" else fmt(true*div if scale=="milliers" else true,lang,scale))
        lab=lfr if lang=="FR" else len_
        # time
        first=sec not in seen; seen.add(sec)
        t=rng.lognormal(np.log(35),.35)
        if first: t+=rng.lognormal(np.log(90+pages*0.9),.35)
        if fc in("DETTE_NETTE",) : t+=10
        t*= {"simple":1,"multi-colonnes N/N-1":1.15,"imbriqué":1.4,"scanné/image":1.9}[layout]*sp*(1.15 if scale=="milliers" else 1)
        # error
        p=.04*er*{"simple":.7,"multi-colonnes N/N-1":1.2,"imbriqué":1.7,"scanné/image":2.6}[layout]*(1.3 if scale=="milliers" else 1)*(1.2 if pages>220 else 1)
        etype="aucune"; man=true
        if rng.random()<p:
            opts={"transposition":3,"mauvaise_colonne_N-1":4 if layout!="simple" else .5,"omission":1.2,"arrondi":1.5,
                  "mauvaise_echelle":3 if scale=="milliers" and kind!="rate" else 0,"signe":3 if true<0 else .4}
            ks=list(opts); w=np.array([opts[k] for k in ks]); etype=rng.choice(ks,p=w/w.sum())
            if etype=="transposition": man=transpose(true,2 if kind=="rate" else (3 if scale=="milliers" else 1))
            elif etype=="mauvaise_colonne_N-1": man=round(true*(1+rng.choice([-1,1])*rng.uniform(.03,.15)),2 if kind=="rate" else (3 if scale=="milliers" else 1))
            elif etype=="omission": man=np.nan
            elif etype=="arrondi": man=float(round(true)) if abs(true-round(true))>.05 else round(true+rng.choice([-1,1]),0)
            elif etype=="mauvaise_echelle": man=round(true*1000,1)
            elif etype=="signe": man=-true
            t*=rng.uniform(.6,.9) if etype=="omission" else 1
        manual_err=int(etype!="aucune")
        date=d0+pd.Timedelta(days=int(rng.integers(0,2)))
        rows.append(dict(id_report=rep,id_entreprise=f"ENT-{c+1:03d}",nom_entreprise=name,secteur=sector,pays=country,
          referentiel_comptable=std_of(country),exercice=fy,devise=cur,langue_rapport=lang,nb_pages_rapport=pages,
          section_annexe=sec_label[lang][sec],numero_note=notes[sec],page_note=pg[sec],mise_en_page_tableau=layout,
          code_champ=fc,libelle_dans_rapport=lab,echelle_publiee=scale if kind!="rate" else "pourcentage",
          texte_brut_publie=raw,valeur_reference=round(true,3),unite_reference="%" if kind=="rate" else f"M {cur}",
          valeur_saisie_manuelle=None if pd.isna(man) else round(man,3),erreur_saisie=manual_err,type_erreur=etype,
          temps_saisie_sec=int(round(t)),id_analyste=an,date_saisie=date.strftime("%Y-%m-%d")))

df=pd.DataFrame(rows)
n=len(df)
# --- imperfections ---
# interruptions (time outliers)
for i in rng.choice(n,5,replace=False): df.loc[i,"temps_saisie_sec"]=int(rng.integers(1400,2600))
# timer not recorded
df["temps_saisie_sec"]=df["temps_saisie_sec"].astype("Int64")
for i in rng.choice(n,9,replace=False): df.loc[i,"temps_saisie_sec"]=pd.NA
# missing page
for i in rng.choice(n,6,replace=False): df.loc[i,"page_note"]=np.nan
df["page_note"]=df["page_note"].astype("Int64")
# inconsistent sector labels
alt={"Industrie":["industrie","Industrials"],"Santé":["Sante","Healthcare"],"Distribution":["Retail"],"Technologie":["Tech"]}
idx=[i for i in rng.choice(n,14,replace=False) if df.loc[i,"secteur"] in alt]
for i in idx: df.loc[i,"secteur"]=random.choice(alt[df.loc[i,"secteur"]])
# currency symbol
for i in rng.choice(df.index[df.devise=="EUR"],5,replace=False): df.loc[i,"devise"]="€"
# date format
for i in rng.choice(n,12,replace=False): df.loc[i,"date_saisie"]=pd.Timestamp(df.loc[i,"date_saisie"]).strftime("%d/%m/%Y")
# duplicates (double entries)
df["_o"]=np.arange(n,dtype=float)
dups=df.loc[rng.choice(n,6,replace=False)].copy(); dups["_o"]+=0.5
df=pd.concat([df,dups]).sort_values("_o").drop(columns="_o").reset_index(drop=True)
df.insert(0,"id_ligne",[f"L{i+1:04d}" for i in range(len(df))])
df.to_csv(OUT,index=False,encoding="utf-8-sig")
