
import os
from dotenv import load_dotenv

load_dotenv()

# RECALIBRADO PARA VAGA DE DESENVOLVEDOR (backend / frontend / fullstack).
# O radar nasceu apontado pra Dados/BI; a lógica de filtro, score, dedup e
# escopo geográfico não sabe de que área é a vaga — quem define o alvo são
# só as listas deste arquivo (ver RegrasFiltro em core/job.py, montado em
# core/perfis.py). Trocar as listas troca o alvo, sem tocar no motor.

# Cargo forte: título que só existe mesmo em vaga de desenvolvimento, sem
# possibilidade real de ser outra área. Casado com _contem_termo (borda de
# palavra), então "Java Developer" não bate em "JavaScript Developer" e
# "Programador" bate em "Programadora"/"Programador(a)" só até o "(" — por
# isso as variações de gênero/adjacência mais frágeis ficam a cargo da
# regra de cargo ambíguo abaixo, que casa por substring.
KEYWORDS_CARGO_FORTE = [
    "Desenvolvedor de Software",
    "Desenvolvedor Web",
    "Desenvolvedor Backend",
    "Desenvolvedor Frontend",
    "Desenvolvedor Fullstack",
    "Engenheiro de Software",
    "Software Engineer",
    "Software Developer",
    "Backend Developer",
    "Frontend Developer",
    "Fullstack Developer",
    "Full Stack Developer",
    "Web Developer",
    "Python Developer",
    "Java Developer",
    "React Developer",
    "Node Developer",
]

# Cargo ambíguo: título que também é usado em vaga sem nada a ver com
# desenvolvimento — "Desenvolvedor de Negócios" (vendas), "Business
# Developer" (comercial), "Engenheiro Civil/de Produção/de Vendas",
# "Desenvolvedor BI" (dados). Só conta como match se o título TAMBÉM tiver
# um QUALIFICADORES_TECNICOS junto.
#
# É esta regra, não a de cargo forte, que carrega a maior parte da
# cobertura real: o casamento aqui é por SUBSTRING crua (ver _avaliar em
# core/job.py), então "desenvolvedor" pega "Desenvolvedor(a)", "Pessoa
# Desenvolvedora" e "Desenvolvedores" — as três formas que a Gupy e o
# LinkedIn usam o tempo todo e que quebrariam qualquer termo composto com
# adjacência exata ("Desenvolvedor Backend" não bate em "Desenvolvedor(a)
# Back-end").
# "Programador" está aqui, não em cargo forte: na indústria existe
# "Programador de Produção"/"Programador de Manutenção" (PCP), que não é
# vaga de software nenhuma. Com qualificador junto ("Programador Java",
# "Programador Web") o ruído some.
KEYWORDS_CARGO_AMBIGUO = [
    "Desenvolvedor",
    "Developer",
    "Engenheiro",
    "Engineer",
    "Programador",
    "Analista de Sistemas",
]

# Termo que precisa aparecer junto no título quando o cargo é ambíguo, pra
# confirmar que é vaga de desenvolvimento e não de outra área qualquer.
# Casado com _contem_termo (borda de palavra + plural), então "java" não
# bate dentro de "javascript" e "api" não bate dentro de "capital".
QUALIFICADORES_TECNICOS = [
    "backend",
    "back-end",
    "frontend",
    "front-end",
    "fullstack",
    "full stack",
    "software",
    "web",
    "api",
    "python",
    "java",
    "javascript",
    "typescript",
    "node",
    "node.js",
    "react",
    "angular",
    "vue",
    "php",
    ".net",
    "c#",
    "ruby",
    "golang",
    "microsserviços",
]

# Framework/stack que aparece como núcleo do título ("Especialista React",
# "Consultor Laravel"). Só conta como match se o título TAMBÉM tiver uma
# palavra de cargo — é o espelho da regra de KEYWORDS_CARGO_AMBIGUO: lá o
# cargo é ambíguo e pede domínio, aqui a stack é ambígua e pede cargo. Sem
# isso, "React" sozinho aprovaria "Recrutador para squad React" e "Product
# Owner (React/Node)", que não são vaga de desenvolvimento.
#
# ATENÇÃO: esta lista é casada por SUBSTRING crua (ver _avaliar em
# core/job.py), não por borda de palavra — nada de termo curto aqui.
# "go" bateria dentro de "Google", "java" dentro de "JavaScript", "r"
# dentro de qualquer coisa. Linguagem de nome curto entra pelo caminho de
# cargo forte ("Java Developer") ou de qualificador técnico, os dois
# casados com borda de palavra.
FERRAMENTAS_TITULO = [
    "React",
    "Angular",
    "Vue.js",
    "Node.js",
    "Django",
    "Laravel",
    "Spring Boot",
    "Next.js",
]

# Palavra de cargo que confirma que a vaga de stack é de desenvolvimento.
# "desenvolvedor"/"developer"/"engenheiro" ENTRAM aqui — no radar de dados
# eles ficavam de fora justamente pra manter vaga de dev longe; aqui é o
# oposto, são o sinal principal.
QUALIFICADORES_CARGO = [
    "desenvolvedor",
    "desenvolvedora",
    "developer",
    "engenheiro",
    "engineer",
    "programador",
    "dev",
    "analista",
    "analyst",
    "especialista",
    "specialist",
    "consultor",
    "consultant",
]

KEYWORDS = KEYWORDS_CARGO_FORTE + KEYWORDS_CARGO_AMBIGUO

# Termos de busca enviados a cada site. Ficam separados das KEYWORDS de
# propósito: TERMOS_BUSCA é a rede ampla (o que é pesquisado em cada site,
# incluindo termos de ferramenta/stack pra achar vaga com título atípico),
# enquanto KEYWORDS é o filtro final e só olha o título da vaga já
# encontrada. Um termo de ferramenta (ex: "dax") só resulta em notificação
# se o TÍTULO da vaga também bater com uma keyword de cargo — isso evita
# falso positivo de vaga que só cita a ferramenta como diferencial.
#
# TERMOS_CARGO é derivado direto de KEYWORDS (em vez de mantido à mão em
# lista separada) — antes as duas listas divergiam: metade das KEYWORDS
# (ex: "Desenvolvedor BI", "BI Analyst", "Analista de Negócios") nunca era
# buscada de verdade, só existia como filtro, então só pegava essas vagas
# por sorte via outro termo. Com a derivação automática isso não pode mais
# acontecer — toda keyword nova em KEYWORDS já vira busca também.
TERMOS_CARGO_EXTRA = [
    # termos mais amplos que a keyword exata, mantidos por dar rede mais
    # larga na busca (a keyword em si é mais restrita, de propósito, pra
    # não gerar falso positivo no filtro de título).
    "desenvolvedor backend",
    "desenvolvedor frontend",
    "desenvolvedor fullstack",
    "pessoa desenvolvedora",
]

# Keyword que é bom FILTRO e péssima BUSCA. "engenheiro"/"engineer" no
# título só passam com qualificador técnico junto (ver
# KEYWORDS_CARGO_AMBIGUO), então como filtro custam nada; como TERMO DE
# BUSCA trazem engenharia civil, de produção, de segurança do trabalho e
# de vendas — páginas inteiras de resultado que o filtro descarta depois,
# gastando um slot inteiro do bloco do ciclo (TERMOS_POR_CICLO) pra render
# zero. "desenvolvedor"/"developer"/"programador", ao contrário, são
# ótimos nos dois papéis e continuam sendo buscados.
#
# A exclusão é explícita (conjunto nomeado) justamente pra não voltar ao
# problema que a derivação automática resolveu: keyword que existe só como
# filtro e nunca é buscada, sem ninguém perceber. Aqui, quando isso
# acontece, é decisão registrada — não esquecimento.
TERMOS_CARGO_NAO_BUSCADOS = {
    "engenheiro",
    "engineer",
}

TERMOS_CARGO = sorted(
    (set(k.lower() for k in KEYWORDS) | set(TERMOS_CARGO_EXTRA)) - TERMOS_CARGO_NAO_BUSCADOS
)

# Stack como termo de busca: acha a vaga cujo título não usa nenhuma
# palavra de cargo reconhecível ("Python Pleno — Squad Pagamentos"). O
# filtro de título continua valendo depois, então stack aqui não afeta o
# que é aprovado, só o que é encontrado.
#
# Lista deliberadamente curta: o histórico do projeto registra que termo
# de stack de baixo rendimento ("dax", "power query", "microsoft fabric")
# custava sessão de navegador igual a um termo de cargo e concentrava
# metade dos timeouts, com zero vaga notificada em 12 rodízios. Começar
# enxuto e ampliar com dado do relatorio_precisao.py é o caminho já
# validado nesta base.
TERMOS_FERRAMENTA = [
    "python",
    "javascript",
    "typescript",
    "react",
    "node.js",
    "java",
    "angular",
    ".net",
    "php",
]

TERMOS_BUSCA = TERMOS_CARGO + TERMOS_FERRAMENTA

# Medido: os TERMOS_BUSCA inteiros (hoje 42) rodando em TODO ciclo é o que
# gera as centenas de sessões de navegador por execução — o custo cresce
# linear com o tamanho da lista, e a lista só cresce (mais ainda com a
# expansão internacional puxando mais termos no radar). TERMOS_POR_CICLO é
# o tamanho do BLOCO usado por ciclo, não o total de termos — main.py roda
# um bloco por vez em rodízio (ver _proximo_bloco_termos) e avança pro
# próximo bloco no ciclo seguinte, salvando a posição no jobs.db. Isso
# desacopla custo por ciclo de tamanho da lista: dobrar TERMOS_BUSCA dobra
# quantos ciclos até cobrir tudo de novo, não o custo de cada ciclo.
TERMOS_POR_CICLO = 10

# Onde vaga HIBRIDA ou PRESENCIAL e aceita (mais "Remoto", que nao e
# cidade e sim a porta de entrada da regra de modalidade remota — ver
# _FLAGS_REMOTO em job.py). Vaga hibrida/presencial fora desta lista e
# rejeitada; e uma whitelist, nao uma preferencia de ordenacao.
#
# SÓ REMOTO: nenhuma cidade na lista significa que vaga presencial ou
# híbrida é rejeitada em qualquer lugar do mundo — é o requisito atual,
# não um efeito colateral. A lista de cidades da configuração original
# (Campina Grande, João Pessoa, Recife...) saiu inteira junto com o
# requisito que a motivava.
#
# Efeito colateral bom: LOCATIONS_LINKEDIN_CIDADES_PRESENCIAL é derivada
# daqui, então some junto — cada cidade era uma busca a mais por termo no
# LinkedIn, e nenhuma delas podia mais resultar em vaga aprovada.
CIDADES = [
    "Remoto",
]

# MEDIDO: "Data Analyst @ Lisboa" e "Analista de Datos @ Madrid" reprovavam
# na localização, não no cargo — CIDADES acima é whitelist só de cidade
# brasileira, e a expansão de LOCATIONS_LINKEDIN pra Argentina/Chile (ver
# abaixo) passou a trazer vaga presencial/híbrida em Portugal/Espanha de
# vez em quando junto. Lista SEPARADA (não misturada em CIDADES, que
# continua só-Brasil de propósito — ver decisão registrada na criação do
# config_intl.py) com toggle próprio, pra dar pra ligar/desligar esse eixo
# sem mexer no resto do filtro. Canônica aqui porque config_intl.py já
# importa de config.py (não o contrário) — o pipeline internacional reusa
# essa mesma lista em vez de manter uma cópia (risco de divergir, mesmo
# motivo da unificação de _contem_termo/_tem_termo).
CIDADES_EUROPA_IBERICA = [
    "Portugal",
    "Lisboa",
    "Porto",
    "Braga",
    "Espanha",
    "España",
    "Spain",
    "Madrid",
    "Barcelona",
    "Valencia",
]

# Toggle independente do ATIVAR_EIXO_IBERICO de config_intl.py — são dois
# eixos diferentes (esse aqui é do pipeline BR/main.py, aquele é do
# pipeline internacional/main_intl.py), cada um com seu próprio liga/
# desliga, mesmo compartilhando a mesma lista de cidades acima.
#
# DESLIGADO: do mercado internacional, só interessa vaga remota — vaga
# presencial/híbrida em Lisboa/Madrid (o que esse eixo notifica, marcada
# "exploratória") não é o que o usuário quer. CIDADES_EUROPA_IBERICA
# continua definida (não precisa apagar) pra caso o eixo volte a ser
# ligado depois — só o toggle muda.
ATIVAR_EIXO_IBERICO_BR = False

# LinkedInScraper é a única fonte do pipeline BR que também alcança vaga
# fora do Brasil (as outras são portais brasileiros) — mas até aqui rodava
# só com location=Brasil fixo no código (scrapers/linkedin.py:88), então
# essa "porta pra fora" nunca era usada.
#
# Mercado "casa": era o único a rodar a passada COMPLETA (presencial/
# híbrida + remoto), porque vaga local interessava. Com CIDADES só-remoto,
# a passada presencial não pode mais resultar em vaga aprovada — varreria
# o Brasil inteiro pra ter tudo descartado no filtro de modalidade. Lista
# vazia = nenhuma passada completa; "Brasil" foi pra
# LOCATIONS_LINKEDIN_REMOTO_APENAS abaixo, onde paga só a passada f_WT=2.
# Isso corta pela metade as requisições do mercado brasileiro por termo.
LOCATIONS_LINKEDIN = []

# Mercados adicionais: só busca REMOTA (f_WT=2) — vaga presencial/híbrida
# num país onde o usuário não mora não serve, então nem faz sentido gastar
# a passada nacional ali (era puro desperdício: Argentina/Chile já rodavam
# as duas passadas antes, mas a nacional nunca batia em CIDADES mesmo,
# que é só cidade brasileira). Espanhol ou português — mesmo critério do
# pipeline internacional. Lista reaproveita exatamente os países já usados
# e testados ao vivo no endpoint do LinkedIn em config_intl.py
# (LOCATIONS_INTL) — evita arriscar nome de país nunca testado (grafia
# errada ou região que o LinkedIn não resolve como location de verdade,
# como já visto com "LATAM"/"Latin America").
LOCATIONS_LINKEDIN_REMOTO_APENAS = ["Brasil", "Argentina", "Chile", "México", "Colômbia", "Espanha", "Portugal"]

# MEDIDO: a passada nacional acima (location="Brasil") varre o país inteiro
# e só sobra o que bate em CIDADES depois do filtro — pra termo concorrido
# em SP/RJ/MG (a maioria), as 3 páginas (30 resultados) nunca chegam numa
# vaga de cidade menor do Nordeste, porque o volume dos polos maiores
# ocupa tudo antes. Testado ao vivo: página 1 de "analista de dados" em
# Brasil inteiro veio 100% São Paulo/Curitiba/Brasília, nenhuma do
# Nordeste. Busca ESPECÍFICA por cidade não depende de volume nacional —
# o próprio location= do LinkedIn já restringe o resultado à cidade, então
# funciona mesmo quando SP/RJ dominam o termo. "Remoto" (item de CIDADES)
# não é local de busca de verdade — sai da lista, já coberto pela passada
# remoto=True de LOCATIONS_LINKEDIN acima.
LOCATIONS_LINKEDIN_CIDADES_PRESENCIAL = [c for c in CIDADES if c != "Remoto"]

# Mercado que a vaga remota precisa aceitar pra contar, quando o texto de
# local DECLARA um escopo geográfico ("Remote — US only", "Remote — India").
# Ver Job.escopo_remoto/RegrasFiltro.mercados_remoto_aceitos em job.py — sem
# isso, uma vaga remota só pra outro país passava igual a uma remota de
# verdade pro Brasil. Vaga remota SEM escopo declarado no texto (a grande
# maioria) continua batendo normalmente, isso só filtra quando a fonte
# EXPLICITA um mercado incompatível.
#
# None = NÃO checa escopo nenhum, qualquer vaga remota serve — é o
# requisito atual ("só remoto, o país não importa"), e é exatamente o
# comportamento que RegrasFiltro.mercados_remoto_aceitos documenta pra
# None (ver job.py). Cuidado ao mexer: lista VAZIA não é a mesma coisa,
# significaria "só aceita remoto SEM escopo declarado", rejeitando toda
# vaga que diga pra quem é.
#
# A lista anterior era ["Brasil", "LATAM", "Argentina", "Chile", "México",
# "Colômbia", "Portugal", "Espanha"] — restrição de mercado que fazia
# sentido pra quem só podia ser contratado nesses países. Fica registrada
# aqui pra facilitar a volta caso o requisito mude; hoje ela barraria
# "Remote — US only", "Remote — Europe" e "Remote — India", que agora
# passam de propósito.
MERCADOS_REMOTO_ACEITOS = None

# Empresas rejeitadas pelo NOME, independentemente de cargo, nota ou
# localização. É o único critério do filtro que lê `empresa` — todo o resto
# de Job._avaliar() olha só título/local/modalidade (a empresa até então
# servia apenas pra dedup, via Job.chave_secundaria, e pra exibir na
# notificação).
#
# Compartilhada pelos dois perfis (BR e internacional, ver core/perfis.py):
# empresa que não interessa não passa a interessar por mudar de mercado.
#
# MEDIDO: BairesDev sozinha respondia por 37 das 1.302 vagas do jobs.db
# (2,8%), gravadas em DUAS grafias diferentes — "BAIRESDEV" (19) e
# "BairesDev" (18), dependendo da fonte que trouxe. Daí a comparação ser
# normalizada (minúsculo, sem acento) e não literal: bloquear a string exata
# pegaria só metade.
#
# Essas 37 são todas do perfil ANTIGO (títulos de Dados/BI) — reprocessadas
# sob a regra de desenvolvedor de hoje, nenhuma passaria no filtro de cargo
# de qualquer jeito. A blocklist existe pro que vier daqui pra frente: a
# BairesDev anuncia vaga de dev em volume alto e em todas as fontes, e é
# justamente o tipo de anúncio que bate o filtro de cargo com folga.
#
# O match usa borda de palavra (_contem_termo), não substring crua:
# "BairesDev LLC" e "BairesDev - Brasil" batem igual, mas um nome curto que
# entre nesta lista no futuro não derruba empresa alheia que apenas contenha
# essas letras no meio — é exatamente o bug que "bi" causou nas keywords de
# cargo (ver _contem_termo em core/job.py).
EMPRESAS_BLOQUEADAS = [
    "bairesdev",
]

INTERVALO_MINUTOS = int(os.getenv("INTERVALO_MINUTOS", 180))

# Piso de relevância: vaga com score ABAIXO deste valor é descartada — não
# notifica na hora nem entra no digest. É o primeiro uso do score como
# CORTE; até aqui ele só ordenava (ver LIMIAR_DIGEST_IMEDIATO abaixo), e
# tudo que passava em combina_com() acabava notificado uma hora ou outra.
#
# ATENÇÃO — 6 é um corte AGRESSIVO no perfil de desenvolvedor atual, por um
# motivo estrutural que não é óbvio olhando a escala "1 a 10".
#
# MEDIDO (reprocessando as 1.302 vagas do jobs.db sob o perfil ATUAL, não
# lendo a coluna `relevancia`, que está obsoleta — foi gravada sob o perfil
# de Dados/BI, antes da recalibração do commit 6521f17): só 5 vagas da base
# inteira ainda passam em combina_com(), e o piso 6 corta 4 dessas 5.
#
# A causa é o peso de ferramenta quase nunca disparar. FERRAMENTAS_TITULO
# tem só 8 nomes de framework (React, Angular, Vue.js, Node.js, Django,
# Laravel, Spring Boot, Next.js); Python, Java, PHP e .NET moram em
# QUALIFICADORES_TECNICOS, que serve pra OUTRA coisa (confirmar domínio de
# cargo ambíguo). Então "Desenvolvedor Backend Python" não ganha os +2 de
# _PESO_FERRAMENTA. Somado a isso, CIDADES é só-remoto e
# MERCADOS_REMOTO_ACEITOS é None, então quase toda vaga fica em "remota sem
# mercado declarado" = +1, nunca os +2 de mercado confirmado.
#
# Sobra este teto prático, conferido rodando o código:
#   "Desenvolvedor Backend Python"          -> 5   (cortada)
#   "Desenvolvedor Full Stack"              -> 4   (cortada)
#   "Programador PHP" / "Desenvolvedor Java"-> 4   (cortada)
#   "Desenvolvedor Backend Python Júnior"   -> 6   (passa)
#   "Desenvolvedor Backend Python Sênior"   -> 2   (cortada)
#
# Ou seja: com piso 6, na prática só passa vaga que diga "Júnior"/"Pleno"
# no título (é o +2 de senioridade que fecha a conta) ou que cite um dos 8
# frameworks. Vaga boa e remota sem palavra de nível no título — a maioria
# dos anúncios reais — é descartada.
#
# Escolhido assim por pedido explícito ("rejeitar vagas com pontuação
# abaixo de 6"). Se o volume vier baixo demais, o ajuste barato é 5 (deixa
# passar o "Desenvolvedor Backend Python" sem nível declarado); o ajuste
# CERTO é rebalancear os pesos em job.py — mover as linguagens pra
# FERRAMENTAS_TITULO faria a escala voltar a usar a faixa de cima.
LIMIAR_RELEVANCIA_MINIMA = 6

# Digest ranqueado (item 08): vaga com Job.pontuar_relevancia() >= este
# limiar notifica na hora (como sempre foi); abaixo disso, fica na fila do
# digest diário — ver _enviar_digest_diario em main.py.
#
# MEDIDO: rodei o score contra as ~305 vagas do jobs.db real que ainda
# batem as regras atuais. Distribuição: score 4 (2%), 5 (24%), 6 (67%),
# 7 (5%), 8 (2%) — nada em 9-10 na amostra (exige acertar praticamente
# todo sinal ao mesmo tempo: cargo forte + ferramenta + senioridade alvo +
# mercado confirmado). Limiar 7 deixa ~7% imediata e ~93% no digest — bate
# com o pedido ("vaga de score alto na hora, resto agrupado"); 6 deixava
# 74% imediata (pouca redução de ruído); 8 deixava só 2% (digest com
# praticamente tudo, quase nenhuma vaga "excelente" se destacando na hora).
LIMIAR_DIGEST_IMEDIATO = 7

# Hora UTC a partir da qual o digest diário pode sair (uma vez por perfil,
# por dia — ver _enviar_digest_diario em main.py). A regra é "ainda não
# enviei hoje E já passou desta hora", então o digest sai no PRIMEIRO ciclo
# do dia UTC que TERMINAR depois dela — não numa janela exata de 1 hora,
# que era o que impedia o disparo de acontecer (o ciclo dura ~80 min e
# nunca terminava dentro da janela).
#
# 9 UTC: o ciclo que começa às 09:00 UTC termina por volta das 10:20 UTC =
# 07:20 em Brasília (UTC-3). Escolhido pela usuária: chega de manhã, com a
# lista do dia anterior pronta pra revisar, em vez de de madrugada.
#
# Era 0 (= ~22h20 de Brasília), mas esse valor nunca foi uma escolha de
# verdade — ficou assim desde que o recurso foi escrito e nunca chegou a
# funcionar, então nunca houve como perceber que horário dava na prática.
#
# Se o ciclo das 09:00 falhar num dia, o das 12:00 (13:20 UTC) manda — a
# regra é "já passou de 9", não "é exatamente 9", então qualquer ciclo
# seguinte do mesmo dia UTC serve de recuperação.
DIGEST_HORA_UTC = 9

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Canal alternativo ao Telegram: URL de webhook do Discord ou do Slack (a
# plataforma é detectada pela própria URL, ver notifier/webhook.py).
# Preenchida, ela GANHA do Telegram — quem decide é notifier/canal.py, que é
# o que main.py importa. Vazia, o robô segue no Telegram como sempre.
NOTIFICADOR_WEBHOOK_URL = os.getenv("NOTIFICADOR_WEBHOOK_URL", "").strip()

# Caminho ancorado na RAIZ do projeto, não na pasta deste arquivo.
#
# MEDIDO: o commit b8227b0 ("Reorganiza raiz: ... -> core/") moveu este
# config.py da raiz pra core/. Como DB_PATH era relativo a __file__, o
# banco se mudou junto, em silêncio: data/jobs.db virou core/data/jobs.db.
# Efeito real, confirmado em disco e no jobradar.log:
#   - data/jobs.db (1.080 vagas, versionado) ficou órfão;
#   - core/data/jobs.db nasceu vazio, então iniciar_db() passou a abortar
#     por BancoVazioSuspeito em toda execução local;
#   - no GitHub Actions a pasta core/data/ não existe no repositório, então
#     o banco era recriado do zero a cada run — toda vaga virava "nova"
#     (renotificação a cada 3h), o rodízio de termos travava no offset 0
#     (só os 10 primeiros de 44 termos eram buscados), a fila do digest era
#     descartada e o heartbeat saía a cada ciclo em vez de 1x/dia;
#   - o passo "git add data/jobs.db" do workflow não via mudança nenhuma
#     ("Nada novo pra commitar"), então o estado nunca mais persistiu.
#
# _RAIZ_PROJETO sobe um nível a partir de core/, então o caminho deixa de
# depender de onde este arquivo mora — mover config.py de novo não move
# mais o banco junto. Coberto por tests/test_db_path.py, pra uma
# reorganização futura quebrar o teste em vez da produção.
#
# JOBRADAR_DB_PATH existe pra apontar um banco descartável em teste/
# experimento sem risco de escrever no banco real.
_RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("JOBRADAR_DB_PATH") or os.path.join(_RAIZ_PROJETO, "data", "jobs.db")