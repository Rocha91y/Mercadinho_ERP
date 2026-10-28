"""
Fornecedor fictício do mercadinho.
Rode uma vez por dia:  python fornecedor.py
Para só ver o que ele faria, sem gravar nada:  python fornecedor.py simular
"""
import os
import sys
import random
from datetime import date, datetime, timedelta
from functools import lru_cache

try:
    from zoneinfo import ZoneInfo
    HOJE = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
except Exception:
    HOJE = date.today()
## HOJE = a data de hoje no horário de Brasília. Importante quando o programa rodar no GitHub, que conta o horário em UTC.
## Se o computador não tiver o fuso instalado, cai para a data do próprio computador.

SIMULAR = "simular" in sys.argv
## Se você rodar "python fornecedor.py simular", ele só mostra o que faria e NÃO grava nada no Supabase.

####--------------------------------------------------------------------------------------------------------------
## REGRAS (ajuste aqui)

ID_AUTO_MINIMO = 12514
## Só mexe em pedidos com id_auto igual ou maior que este. Protege o histórico (até 12513), que já está pronto.

TAB_MOVIMENTOS = "movimentacoes"
TAB_PRODUTOS = "produtos"
TAB_FORNECEDORES = "fornecedores"
TAB_ESTOQUE = "estoque"
## Nomes das tabelas no Supabase. Se mudar o nome de uma, é só trocar aqui.

DIAS_FATURAMENTO = [2, 3, 4, 5]
PESOS_FATURAMENTO = [50, 25, 15, 10]
## Faturamento: sorteia 2, 3, 4 ou 5 dias depois do pedido, com 50%, 25%, 15% e 10% de chance.

PRAZO_BASE = {"RJ": 4, "MG": 4, "ES": 4, "SP": 5, "DF": 6, "GO": 6, "PR": 6, "BA": 7}
## Previsão de entrega = faturamento + este número de dias corridos (depende da UF do fornecedor).

AJUSTE_ENTREGA = [-1, 0, 1]
PESOS_ENTREGA = [30, 50, 20]
## Entrega real: 30% chega 1 dia útil ANTES da previsão, 50% NA data e 20% 1 dia útil DEPOIS (atraso).

FRETE = {
    #  UF:  (mínimo, sem frete a partir de, % de frete sobre o valor)
    "MG": (150, 500, 0.05),
    "RJ": (200, 550, 0.06),
    "ES": (250, 600, 0.07),
    "SP": (310, 660, 0.08),
    "DF": (370, 720, 0.09),
    "PR": (430, 780, 0.10),
    "GO": (490, 840, 0.11),
    "BA": (560, 910, 0.12),
}
## PROPOSTA de frete por UF. Para cada fornecedor do pedido: se o valor chegou ao "sem frete", o frete é zero;
## senão, o frete é o % sobre o valor do que foi comprado dele. O mínimo daqui só vale para a trava do compras.py.

FERIADOS_MUNICIPAIS = {
    date(2027, 2, 15), date(2027, 6, 29), date(2027, 9, 6),
    date(2028, 2, 28), date(2028, 6, 29), date(2028, 9, 6),
}
## Feriados de Muriaé (os que você passou). Os nacionais são calculados sozinhos abaixo.

COLUNAS_UF = ["uf", "estado", "uf_origem", "sigla_uf"]
## Nomes possíveis da coluna de UF na tabela de fornecedores. O programa testa um por um até achar.
####--------------------------------------------------------------------------------------------------------------


####--------------------------------------------------------------------------------------------------------------
## CALENDÁRIO

def pascoa(ano):
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)
## Calcula a data da Páscoa de qualquer ano (fórmula pronta). Serve para achar a Sexta-feira Santa, que muda todo ano.

@lru_cache(maxsize=None)
def feriados_do_ano(ano):
    fixos = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12),
             (11, 2), (11, 15), (11, 20), (12, 25)]
    dias = {date(ano, m, d) for m, d in fixos}
    dias.add(pascoa(ano) - timedelta(days=2))
    dias |= {d for d in FERIADOS_MUNICIPAIS if d.year == ano}
    return dias
## Monta a lista de feriados do ano: nacionais fixos + Sexta-feira Santa + municipais de Muriaé.
## O @lru_cache guarda o resultado, para não recalcular o mesmo ano toda hora.

def eh_util(d):
    return d.weekday() < 5 and d not in feriados_do_ano(d.year)
## Dia útil = de segunda a sexta (weekday 0 a 4) e que não seja feriado.

def proximo_util(d):
    while not eh_util(d):
        d += timedelta(days=1)
    return d

def anterior_util(d):
    while not eh_util(d):
        d -= timedelta(days=1)
    return d
## Se a data cair em fim de semana ou feriado, anda para frente (proximo_util) ou para trás (anterior_util)
## até achar um dia útil.
####--------------------------------------------------------------------------------------------------------------


####--------------------------------------------------------------------------------------------------------------
## SORTEIOS E CÁLCULOS (não mexem no banco: só recebem dados e devolvem datas e valores)

def calc_faturamento(semente, data_pedido):
    rng = random.Random(f"{semente}-fat")
    dias = rng.choices(DIAS_FATURAMENTO, PESOS_FATURAMENTO)[0]
    return proximo_util(data_pedido + timedelta(days=dias))
## Sorteia quantos dias demora para faturar e empurra para o próximo dia útil.
## A "semente" (id do pedido + fornecedor) faz o sorteio dar SEMPRE o mesmo resultado para o mesmo pedido,
## mesmo que o programa rode várias vezes. É como lançar um dado que já veio marcado de fábrica para aquele pedido.

def calc_previsao(data_fat, uf):
    return proximo_util(data_fat + timedelta(days=PRAZO_BASE[uf]))
## Previsão = faturamento + prazo da UF (dias corridos); se cair em dia sem entrega, vai para o próximo dia útil.

def calc_recebimento(semente, previsao):
    rng = random.Random(f"{semente}-ent")
    ajuste = rng.choices(AJUSTE_ENTREGA, PESOS_ENTREGA)[0]
    if ajuste == 0:
        return previsao
    if ajuste > 0:
        return proximo_util(previsao + timedelta(days=1))
    return anterior_util(previsao - timedelta(days=1))
## Sorteia se a entrega vem antes, na data ou depois da previsão. O atraso de verdade (20%) você analisa no BI
## comparando recebido_em com previsao_entrega.

def calc_frete(uf, valor):
    minimo, sem_frete, pct = FRETE[uf]
    if valor >= sem_frete:
        return 0.0
    return round(valor * pct, 2)
## Frete do fornecedor naquele pedido: zero se o valor bateu o "sem frete", senão % sobre o valor.

def agrupar(linhas, forn_do_produto):
    grupos = {}
    for m in linhas:
        chave = (m["id_movimento"], forn_do_produto[m["id_produto"]])
        grupos.setdefault(chave, []).append(m)
    for g in grupos.values():
        g.sort(key=lambda x: x["id_auto"])
    return grupos
## Junta as linhas do mesmo pedido (id_movimento) e do mesmo fornecedor. Cada grupo é "uma entrega":
## tem um faturamento, um frete e uma data de chegada. Duas linhas do mesmo fornecedor no mesmo pedido = 1 grupo = 1 frete.

def planejar_faturamento(id_mov, id_forn, linhas, uf, hoje):
    fat = calc_faturamento(f"{id_mov}-{id_forn}", date.fromisoformat(linhas[0]["data_pedido"]))
    if fat > hoje:
        return None
    previsao = calc_previsao(fat, uf)
    frete = calc_frete(uf, sum(float(m["custo"]) for m in linhas))
    return [(m["id_auto"], {
        "data_faturamento": str(fat),
        "uf_origem": uf,
        "previsao_entrega": str(previsao),
        "valor_frete": frete if i == 0 else 0,
    }) for i, m in enumerate(linhas)]
## Para um grupo: sorteia o faturamento. Se a data ainda não chegou, devolve None (espera). Se chegou, devolve o que
## gravar em cada linha. O frete inteiro vai na PRIMEIRA linha e as outras ficam com 0, como você pediu.

def planejar_recebimento(id_mov, id_forn, linhas, hoje):
    previsao = date.fromisoformat(linhas[0]["previsao_entrega"])
    rec = calc_recebimento(f"{id_mov}-{id_forn}", previsao)
    if rec > hoje:
        return None
    return [(m, rec) for m in linhas]
## Para um grupo já faturado: sorteia a chegada. Se ainda não chegou, devolve None. Se chegou, todas as linhas
## do grupo chegam juntas, no mesmo dia.
####--------------------------------------------------------------------------------------------------------------


####--------------------------------------------------------------------------------------------------------------
## SUPABASE (aqui o programa conversa com o banco)

def conectar():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not (url and key):
        from config import URL, KEY
        url, key = URL, KEY
    return create_client(url, key)
## Pega a URL e a chave das variáveis do ambiente (é assim que o GitHub vai fornecer, sem a chave aparecer no código).
## Se não existirem, lê do arquivo config.py do seu computador. Use a chave SECRET neste programa.

def mapa_fornecedores(sb):
    linhas = sb.table(TAB_FORNECEDORES).select("*").execute().data
    col_uf = next((c for c in COLUNAS_UF if linhas and c in linhas[0]), None)
    if col_uf is None:
        raise SystemExit(f"Não achei a coluna de UF em '{TAB_FORNECEDORES}'. Colunas existentes: {list(linhas[0])}")
    return {f["id_fornecedor"]: f[col_uf] for f in linhas}
## Baixa os fornecedores (são poucos) e monta um dicionário id_fornecedor -> UF.

def mapa_produto_fornecedor(sb, linhas):
    ids = sorted({m["id_produto"] for m in linhas})
    mapa = {}
    for i in range(0, len(ids), 100):
        bloco = ids[i:i + 100]
        dados = sb.table(TAB_PRODUTOS).select("id_produto,id_fornecedor").in_("id_produto", bloco).execute().data
        mapa.update({p["id_produto"]: p["id_fornecedor"] for p in dados})
    return mapa
## Para os produtos que aparecem nos pedidos, descobre quem é o fornecedor de cada um. Pede em blocos de 100 para a
## consulta não ficar grande demais.

def gravar(sb, id_auto, valores, so_se_vazio=None):
    if SIMULAR:
        print("   [simular]", id_auto, valores)
        return True
    q = sb.table(TAB_MOVIMENTOS).update(valores).eq("id_auto", id_auto)
    if so_se_vazio:
        q = q.is_(so_se_vazio, "null")
    return bool(q.execute().data)
## Atualiza UMA linha pelo id_auto (a chave única da tabela). O "so_se_vazio" é um cadeado: só grava se a coluna ainda
## estiver vazia. Assim, se o programa rodar duas vezes ao mesmo tempo, o estoque não é somado duas vezes.

def somar_estoque(sb, id_produto, qtd):
    if SIMULAR:
        print("   [simular] estoque", id_produto, "+", qtd)
        return
    atual = sb.table(TAB_ESTOQUE).select("quantidade").eq("id_produto", id_produto).execute().data
    if atual:
        sb.table(TAB_ESTOQUE).update({"quantidade": atual[0]["quantidade"] + qtd}).eq("id_produto", id_produto).execute()
    else:
        sb.table(TAB_ESTOQUE).insert({"id_produto": id_produto, "quantidade": qtd}).execute()
## Entrada no estoque: lê a quantidade atual do produto e soma a que chegou. Se o produto ainda não existe no estoque,
## cria a linha.

def main():
    sb = conectar()
    uf_do_forn = mapa_fornecedores(sb)
    faturados = recebidos = 0
    print(f"{HOJE}  {'(SIMULAÇÃO)' if SIMULAR else ''}")

    # 1) FATURAR: pedidos que ainda não têm data de faturamento
    pendentes = (sb.table(TAB_MOVIMENTOS).select("*")
                 .gte("id_auto", ID_AUTO_MINIMO)
                 .is_("data_faturamento", "null").execute().data)
    if pendentes:
        forn_prod = mapa_produto_fornecedor(sb, pendentes)
        for (id_mov, id_forn), linhas in agrupar(pendentes, forn_prod).items():
            plano = planejar_faturamento(id_mov, id_forn, linhas, uf_do_forn[id_forn], HOJE)
            if plano is None:
                continue
            print(f" faturar {id_mov} fornecedor {id_forn}: {len(linhas)} linha(s)")
            for id_auto, valores in plano:
                gravar(sb, id_auto, valores)
            faturados += 1

    # 2) RECEBER: pedidos faturados que ainda não chegaram
    a_receber = (sb.table(TAB_MOVIMENTOS).select("*")
                 .gte("id_auto", ID_AUTO_MINIMO)
                 .not_.is_("previsao_entrega", "null")
                 .is_("recebido_em", "null").execute().data)
    if a_receber:
        forn_prod = mapa_produto_fornecedor(sb, a_receber)
        for (id_mov, id_forn), linhas in agrupar(a_receber, forn_prod).items():
            plano = planejar_recebimento(id_mov, id_forn, linhas, HOJE)
            if plano is None:
                continue
            print(f" receber {id_mov} fornecedor {id_forn}: {len(linhas)} linha(s)")
            for m, rec in plano:
                ok = gravar(sb, m["id_auto"], {"recebido_em": str(rec), "total_recebido": m["quantidade"]},
                            so_se_vazio="recebido_em")
                if ok:
                    somar_estoque(sb, m["id_produto"], m["quantidade"])
            recebidos += 1

    print(f"Resumo: {faturados} grupo(s) faturado(s), {recebidos} grupo(s) recebido(s).")
## Roda os dois passos em ordem.
## 1) FATURAR: pega pedidos sem data_faturamento, agrupa por pedido + fornecedor e grava as datas e o frete.
## 2) RECEBER: pega pedidos já faturados e sem recebido_em, e quando a chegada sorteada é hoje (ou já passou),
##    grava recebido_em, total_recebido (= quantidade que chegou) e soma a quantidade no estoque.
## Se a data sorteada ainda não chegou, o grupo simplesmente espera até o próximo dia.
####--------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    main()
