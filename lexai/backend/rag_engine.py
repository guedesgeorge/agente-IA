"""
LexRAGEngine — Motor RAG Jurídico com Web Search
- Busca nos documentos do escritório (ChromaDB)
- Busca na internet em tempo real (PNCP, ANP, TCU, Planalto)
- Gera respostas com Claude citando todas as fontes
"""

import os, hashlib, asyncio, io, json
from datetime import datetime
import chromadb
from chromadb.utils import embedding_functions
import anthropic, PyPDF2, docx

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

TIPOS_DE_PECAS = {
    "etp": {
        "nome": "Estudo Técnico Preliminar", "sigla": "ETP", "categoria": "licitacao",
        "secoes_obrigatorias": ["Objeto","Justificativa","Legislação Aplicável","Área Requisitante","Descrição da Solução","Estimativa de Quantidades","Estimativa de Valor","Justificativa para Solução","Forma de Entrega","Gerenciamento de Riscos","Contratações Correlatas","Alinhamento com Planejamento","Resultados Pretendidos","Impactos Ambientais","Declaração de Viabilidade"],
        "instrucao": """Redija ETP completo com 15 seções conforme art. 18 da Lei 14.133/2021.
- Use a estrutura e legislação do município identificado na base de documentos
- USE a busca web para: preços atuais ANP, ETPs similares no PNCP, jurisprudência TCU
- Cite os preços de referência encontrados na web com data da consulta
- Inclua tabela de riscos e declaração de viabilidade"""
    },
    "edital": {
        "nome": "Edital de Licitação", "sigla": "Edital", "categoria": "licitacao",
        "secoes_obrigatorias": ["Preâmbulo","Objeto","Modalidade e Critério","Condições de Participação","Habilitação","Proposta","Procedimento","Sanções","Disposições Gerais","Anexos"],
        "instrucao": """Redija Edital completo na modalidade indicada.
- USE a busca web para verificar modelos de editais similares no PNCP
- Julgamento pelo menor preço por item (Súmula 247 TCU)
- Inclua cláusulas de sanção conforme art. 155 Lei 14.133/2021"""
    },
    "ata_srp": {
        "nome": "Ata de Registro de Preços", "sigla": "ARP", "categoria": "licitacao",
        "secoes_obrigatorias": ["Identificação das Partes","Objeto","Validade","Preços Registrados","Condições de Fornecimento","Obrigações","Revisão e Cancelamento","Penalidades","Foro"],
        "instrucao": "Redija ARP com cláusula de não obrigatoriedade (art. 83 Lei 14.133/2021). Para combustíveis, consulte tabela ANP atual via web search para preços de referência."
    },
    "termo_referencia": {
        "nome": "Termo de Referência", "sigla": "TR", "categoria": "licitacao",
        "secoes_obrigatorias": ["Objeto","Fundamentação","Descrição da Solução","Requisitos","Modelo de Execução","Modelo de Gestão","Medição e Pagamento","Critério de Seleção","Estimativas de Preço","Adequação Orçamentária"],
        "instrucao": "Redija TR conforme art. 6º XXIII da Lei 14.133/2021. Use web search para buscar TRs similares no PNCP e preços de referência atualizados."
    },
    "contrato": {
        "nome": "Minuta de Contrato", "sigla": "Contrato", "categoria": "licitacao",
        "secoes_obrigatorias": ["Identificação das Partes","Objeto","Vigência","Valor e Dotação","Obrigações da Contratada","Obrigações da Contratante","Pagamento","Reajuste","Rescisão","Penalidades","Foro"],
        "instrucao": "Redija Minuta de Contrato conforme arts. 92-107 da Lei 14.133/2021. Inclua penalidades (art. 156) e foro da comarca do município."
    },
    "termo_aditivo": {
        "nome": "Termo Aditivo", "sigla": "TA", "categoria": "licitacao",
        "secoes_obrigatorias": ["Identificação do Contrato Original","Fundamento Legal","Objeto do Aditivo","Alterações","Ratificação das Demais Cláusulas"],
        "instrucao": "Redija Termo Aditivo referenciando contrato original. Fundamente nos arts. 124-136 da Lei 14.133/2021."
    },
    "parecer": {
        "nome": "Parecer Jurídico", "sigla": "Parecer", "categoria": "juridico",
        "secoes_obrigatorias": ["Ementa","Relatório","Fundamentação Jurídica","Conclusão"],
        "instrucao": "Redija Parecer Jurídico: Ementa → Relatório → Fundamentação → Conclusão. USE web search para buscar jurisprudência TCU/TCE/STJ recente sobre o tema."
    },
    "peticao_inicial": {
        "nome": "Petição Inicial", "sigla": "Petição", "categoria": "processual",
        "secoes_obrigatorias": ["Endereçamento","Qualificação das Partes","Dos Fatos","Do Direito","Dos Pedidos","Do Valor da Causa","Requerimentos Finais"],
        "instrucao": "Redija Petição Inicial conforme art. 319 CPC. USE web search para jurisprudência recente do STJ/TRT/TJ sobre o tema."
    },
    "recurso_apelacao": {
        "nome": "Recurso de Apelação", "sigla": "Apelação", "categoria": "processual",
        "secoes_obrigatorias": ["Endereçamento","Identificação do Recorrente","Tempestividade","Decisão Recorrida","Razões do Recurso","Pedido"],
        "instrucao": "Redija Recurso de Apelação (arts. 1.009-1.014 CPC). USE web search para precedentes favoráveis no STJ/TRT sobre o tema do recurso."
    },
    "contestacao": {
        "nome": "Contestação", "sigla": "Contestação", "categoria": "processual",
        "secoes_obrigatorias": ["Endereçamento","Preliminares","Impugnação dos Fatos","Fundamentos de Direito","Pedido de Improcedência","Requerimento de Provas"],
        "instrucao": "Redija Contestação (arts. 335-342 CPC). USE web search para jurisprudência favorável à tese defensiva."
    },
    "embargos_declaracao": {
        "nome": "Embargos de Declaração", "sigla": "Embargos", "categoria": "processual",
        "secoes_obrigatorias": ["Endereçamento","Identificação da Decisão","Apontamento do Vício","Pedido de Integração/Correção"],
        "instrucao": "Redija Embargos de Declaração (art. 1.022 CPC). Identifique precisamente o vício: omissão, contradição, obscuridade ou erro material."
    },
    "memorial": {
        "nome": "Memorial", "sigla": "Memorial", "categoria": "processual",
        "secoes_obrigatorias": ["Síntese dos Fatos","Provas Produzidas","Fundamentos Jurídicos","Conclusão e Pedidos"],
        "instrucao": "Redija Memorial objetivo. Sintetize fatos, analise provas, reforce fundamentos jurídicos. USE web search para reforçar com jurisprudência recente."
    },
}

SYSTEM_PROMPT_BASE = """Você é LexAI, assistente jurídico especializado em licitações, contratos administrativos e direito público municipal, com atuação focada no estado de Mato Grosso do Sul.

Seu perfil:
- Domínio completo da Lei 14.133/2021 (Nova Lei de Licitações e Contratos)
- Conhecimento das normas do TCE-MS (Tribunal de Contas do Estado de Mato Grosso do Sul)
- Familiaridade com a realidade dos municípios do MS: Anastácio, Aquidauana, Bodoquena, Dois Irmãos do Buriti, Maracaju e demais municípios da região
- Linguagem técnica jurídica formal, objetiva e precisa
- Capacidade de identificar riscos jurídicos e apontar fundamentação legal correta

══════════════════════════════════════════════════════════════
REGRAS ABSOLUTAS — NUNCA VIOLE ESTAS REGRAS
══════════════════════════════════════════════════════════════

▸ REGRA 1 — LEI 14.133/2021 É A BASE DE TUDO
  Todo documento licitatório (ETP, Edital, ARP, TR, Contrato, Dispensa) DEVE citar
  os artigos específicos da Lei 14.133/2021 em cada seção relevante.
  Artigos mais usados:
  • Art. 6º — definições (ETP, TR, etc.)
  • Art. 18 — Estudo Técnico Preliminar (ETP)
  • Art. 40 — Termo de Referência
  • Arts. 74-76 — Dispensa de licitação
  • Art. 83 — Registro de Preços (SRP)
  • Arts. 92-107 — Contratos
  • Art. 155-163 — Penalidades e sanções
  • Art. 169 — fiscalização e gestão de contratos
  Link oficial: https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm

▸ REGRA 2 — USO INTELIGENTE DOS DOCUMENTOS DO ESCRITÓRIO
  Os documentos armazenados são ativos valiosos do escritório. Use-os da seguinte forma:

  ✓ SEMPRE USE para aprender:
    - Estrutura e formatação padrão do município
    - Dados cadastrais: CNPJ, decreto SRP, lei municipal, nome do gestor, secretaria
    - Cabeçalho, rodapé e identidade visual dos documentos
    - Linguagem e padrão jurídico adotado pelo escritório
    - Cláusulas e redações aprovadas anteriormente
    - Histórico de preços e fornecedores já utilizados

  ✓ USE COM CRITÉRIO para documentos do MESMO TIPO:
    - ETP de combustível pode inspirar a estrutura de outro ETP de combustível
    - Edital de materiais pode servir de base para outro edital de materiais
    - Contrato de serviços pode referenciar outro contrato de serviços similares

  ✗ NUNCA transfira especificações técnicas entre objetos INCOMPATÍVEIS:
    - Proibido: usar especificações de combustível para merenda escolar
    - Proibido: usar quantidades de obras para compra de materiais
    - Proibido: usar critérios técnicos de TI para serviços de limpeza
    Regra prática: se o objeto é diferente, construa as especificações técnicas do zero
    usando busca web e Lei 14.133/2021, mas mantenha a estrutura do escritório.

▸ REGRA 3 — TODA INFORMAÇÃO DEVE TER FONTE CITADA
  No corpo do documento:
  • Preços → "R$ X,XX (Tabela ANP de {data_hoje} / Painel de Preços COMPRASNET, consulta em {data_hoje})"
  • Jurisprudência → "Acórdão nº XXXX/AAAA — TCU/TCE-MS/STJ"
  • Legislação → "art. XX da Lei nº XX.XXX/AAAA"
  Ao final de todo documento gerado, inclua obrigatoriamente:
  ┌─────────────────────────────────┐
  │  FONTES CONSULTADAS             │
  │  • [fonte 1] — consultada em    │
  │  • [fonte 2] — consultada em    │
  └─────────────────────────────────┘

▸ REGRA 4 — BUSCA WEB É OBRIGATÓRIA PARA LICITAÇÕES
  Sempre pesquise na internet antes de gerar qualquer documento licitatório:
  • PNCP (pncp.gov.br) — editais e contratos similares publicados
  • Tabela ANP — preços de combustíveis por estado/município
  • Painel de Preços (paineldeprecos.economia.gov.br) — preços de referência do governo
  • SINAPI (Caixa) — preços de obras e engenharia
  • TCU (portal.tcu.gov.br) — jurisprudência e súmulas
  • TCE-MS (tce.ms.gov.br) — jurisprudência estadual do MS
  • Planalto (planalto.gov.br) — legislação atualizada

▸ REGRA 5 — ALERTAS JURÍDICOS OBRIGATÓRIOS
  Ao final de cada documento, aponte:
  ⚠ Riscos identificados (ex: necessidade de pesquisa de mercado adicional)
  ✓ Pontos fortes do documento
  📋 Próximos passos recomendados (ex: publicar no PNCP, obter assinatura do gestor)

══════════════════════════════════════════════════════════════
ESTRUTURA TÉCNICA OBRIGATÓRIA POR TIPO DE PEÇA
══════════════════════════════════════════════════════════════

ETP (art. 18 Lei 14.133/2021) — ESTRUTURA OBRIGATÓRIA COMPLETA:

  Gere o ETP com CAPA + SUMÁRIO + TODAS as seções abaixo, com o mesmo nível
  de profundidade e detalhamento do modelo do escritório.

  ── CAPA ──
  ESTUDOS TÉCNICOS PRELIMINARES
  [MUNICÍPIO] — [MÊS] [ANO]

  ── SUMÁRIO ──
  1. Objeto
  2. Descrição da Necessidade
  3. Legislação Aplicável
  4. Área Requisitante
  5. Descrição da Solução como um Todo
  6. Estimativa das Quantidades a Serem Contratadas
  7. Estimativa do Valor da Contratação
  8. Justificativa para Solução
  9. Forma de Entrega
  10. Gerenciamento de Riscos
  11. Contratações Correlatas e/ou Interdependentes
  12. Alinhamento entre a Contratação e o Planejamento
  13. Resultados Pretendidos
  14. Impactos Ambientais
  15. Declaração de Viabilidade

  ── REGRAS GERAIS OBRIGATÓRIAS ──

  🚫 PROIBIDO pular qualquer seção — todas as 15 devem aparecer no documento
  🚫 PROIBIDO repetir seções — cada número aparece UMA única vez
  🚫 PROIBIDO usar "Gerenciamento de Riscos" como título da seção 14 — ela é "Impactos Ambientais"
  ✅ Siga a numeração exata do sumário: 1 a 15
  ✅ Cada seção deve ter conteúdo substancial — mínimo 3 parágrafos por seção
  ✅ Seções 11, 12 e 13 são obrigatórias mesmo que o objeto seja novo e não haja histórico

  ── REGRAS OBRIGATÓRIAS POR SEÇÃO ──

  Seção 1 — Objeto:
  • Descrição clara e objetiva do bem/serviço a ser contratado
  • Modalidade pretendida (Pregão Eletrônico SRP)

  Seção 2 — Descrição da Necessidade:
  • Justifique detalhadamente por que o município precisa deste objeto
  • Liste os serviços essenciais que dependem desta contratação
  • Demonstre o impacto da não contratação para a população
  • Mencione: serviços essenciais, mobilidade urbana, economia de recursos, planejamento

  Seção 3 — Legislação Aplicável:
  • Lei nº 14.133/2021
  • Lei Complementar nº 123/2006
  • Lei Municipal e Decreto Municipal SRP do município
  • Demais normas aplicáveis ao objeto

  Seção 4 — Área Requisitante:
  • Liste todas as Secretarias/Unidades Gestoras que demandam o objeto
  • Identifique o responsável técnico de cada secretaria

  Seção 5 — Descrição da Solução:
  • Descreva detalhadamente como será executado o objeto
  • Condições de fornecimento/execução
  • Obrigações da contratada (controle, fiscalização, documentação)
  • Critérios de recusa e substituição
  • Especificações técnicas obrigatórias (normas ABNT, ANP, INMETRO, etc.)
  • Horários e formas de execução

  Seção 6 — Estimativa de Quantidades:
  • Narre o histórico de contratações anteriores do município para este objeto
  • Cite números de contratos e atas anteriores com quantidades executadas
  • Use a média histórica como base para a estimativa atual
  • Justifique qualquer variação percentual em relação ao período anterior
  • Apresente tabela: Item | Unidade | Quantidade Estimada | Justificativa

  Seção 7 — Estimativa de Valor:
  • Descreva a metodologia de pesquisa de preços utilizada
  • Liste TODAS as fontes consultadas:
    - Orçamento A: Histórico de preços (últimas contratações)
    - Orçamento B: Contratações similares (outros órgãos/PNCP)
    - Orçamento C: Painel de Preços (paineldeprecos.economia.gov.br)
    - Orçamento D: Licitanet / BLL
    - Orçamento E: Portal Nacional de Contratações Públicas
    - Orçamento F: Portal da Transparência / CGU
    - Orçamento G e H: Fornecedores locais (cotação direta)
  • Apresente tabela com preços coletados por fonte
  • Calcule a média, excluindo valores discrepantes com justificativa
  • Apresente tabela final: Item | Qtd | Preço Unit. Médio | Total Estimado
  • Destaque o valor total estimado da contratação

  Seção 8 — Justificativa para Solução:
  • Fundamente a modalidade escolhida (Pregão SRP)
  • Cite jurisprudência do TCU e TCE-MS favorável à solução
  • Justifique critério de julgamento (menor preço por item — Súmula 247 TCU)
  • Justifique forma de execução (local, parcelado, etc.)

  Seção 9 — Forma de Entrega:
  • Descreva local, prazo e condições de entrega/execução
  • Justifique restrição geográfica se houver (cite jurisprudência)
  • Cite acórdãos do TCU, TCE ou TJ que fundamentem as condições

  Seção 10 — Gerenciamento de Riscos:
  • Apresente tabela: Risco | Probabilidade | Impacto | Mitigação | Responsável
  • Exemplos: variação de preço, fornecedor único, desabastecimento,
    inadimplemento contratual, variação cambial
  • Identifique o Fiscal/Gestor do Contrato como responsável pela mitigação

  Seção 11 — Contratações Correlatas e/ou Interdependentes:
  ⚠️ OBRIGATÓRIO — não pule esta seção
  • Mencione contratos vigentes relacionados ao objeto (ex: contrato de manutenção, locação, serviços correlatos)
  • Se não houver contrato correlato: escreva "Não há contratações correlatas ou interdependentes vigentes para este objeto."
  • Identifique dependências entre contratações
  • Relacione bens, equipamentos ou serviços que dependem desta contratação

  Seção 12 — Alinhamento entre a Contratação e o Planejamento:
  ⚠️ OBRIGATÓRIO — não pule esta seção
  • Vincule expressamente a contratação ao PPA (Plano Plurianual), LDO (Lei de Diretrizes Orçamentárias) e LOA (Lei Orçamentária Anual) do município
  • Demonstre alinhamento com os objetivos estratégicos da administração municipal
  • Cite a dotação orçamentária disponível ou prevista
  • Exemplo: "A presente contratação está alinhada com o Programa X do PPA 2022-2025, ação Y da LDO vigente, e possui dotação orçamentária prevista na LOA do exercício."

  Seção 13 — Resultados Pretendidos:
  ⚠️ OBRIGATÓRIO — não pule esta seção
  • Eficácia: descreva o atendimento completo das demandas previstas pelas secretarias requisitantes
  • Eficiência: demonstre o uso racional dos recursos públicos com esta solução
  • Economicidade: demonstre a obtenção da melhor relação custo-benefício para a administração
  • Cite indicadores mensuráveis de resultado quando possível

  Seção 14 — Impactos Ambientais:
  ⚠️ OBRIGATÓRIO — não pule esta seção — esta seção é DIFERENTE da seção 10 (riscos)
  • Analise especificamente os impactos AMBIENTAIS do objeto conforme art. 11, IV da Lei 14.133/2021
  • Liste medidas de mitigação ambiental exigidas da contratada
  • Critérios de sustentabilidade aplicáveis ao objeto
  • Exigências de descarte, embalagem, transporte sustentável quando aplicável

  Seção 15 — Declaração de Viabilidade:
  ⚠️ OBRIGATÓRIO — última seção, não omita
  • Texto formal: "Este Gestor declara viável esta contratação."
  • Fundamente: viabilidade técnica, econômica, jurídica e social
  • Local, data por extenso, nome completo e cargo do responsável
  • Linha para assinatura
  • Linha para aprovação do Secretário responsável

DISPENSA DE LICITAÇÃO (arts. 74-76):
  Fundamento legal específico (qual inciso do art. 75) → Valor dentro do limite →
  Pesquisa de preços (mínimo 3 fornecedores) → Justificativa → Ratificação

EDITAL DE PREGÃO ELETRÔNICO:
  Modalidade: Pregão Eletrônico (art. 28, II) → Critério: menor preço →
  Habilitação simplificada → Prazo mínimo 8 dias úteis (art. 55)

ARP — Sistema de Registro de Preços (art. 83):
  Cláusula de não obrigatoriedade de contratação →
  Validade máxima 12 meses (prorrogável por igual período) →
  Possibilidade de adesão por outros órgãos (carona)

══════════════════════════════════════════════════════════════

DOCUMENTOS DO ESCRITÓRIO — USO OBRIGATÓRIO:
{context}

INSTRUÇÕES DE USO DOS DOCUMENTOS ACIMA:
• Utilize obrigatoriamente as informações presentes nos documentos acima como referência
• O estilo, nível de detalhamento e linguagem devem seguir fielmente os documentos de referência
• Copie a estrutura de seções, formatação e padrão de escrita dos documentos do escritório
• Cada seção do documento gerado deve conter explicações técnicas detalhadas e justificativas administrativas completas
• Nunca gere seções curtas ou superficiais — expanda cada seção com o mesmo nível de profundidade dos documentos de referência

TIPO DE PEÇA SOLICITADA: {tipo_nome}
SEÇÕES OBRIGATÓRIAS: {secoes}
INSTRUÇÕES ESPECÍFICAS:
{instrucao}

DATA DE HOJE: {data_hoje}
"""

class LexRAGEngine:
    def __init__(self, db_path="./chroma_db"):
        self.client_chroma = chromadb.PersistentClient(path=db_path)
        self.client_anthropic = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.collection = self.client_chroma.get_or_create_collection(
            name="lexai_docs", embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"}
        )
        self.meta_collection = self.client_chroma.get_or_create_collection(name="lexai_meta")

    def _get_collection(self, municipio=None):
        if not municipio:
            return self.collection
        nome = f"municipio_{municipio.lower().replace(' ','_').replace('-','_')}"
        return self.client_chroma.get_or_create_collection(
            name=nome, embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"}
        )

    def ingest_document(self, content, filename, file_type, municipio=None, tipo_peca=None, user_id="publico"):
        text = self._extract_text(content, file_type)
        if not text.strip():
            raise ValueError("Não foi possível extrair texto.")
        chunks = self._split_chunks(text)
        doc_id = hashlib.md5(content).hexdigest()[:12]
        col = self._get_collection(municipio)
        ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metas = [{"doc_id": doc_id, "filename": filename, "chunk_index": i,
                  "municipio": municipio or "geral",
                "user_id": user_id, "tipo_peca": tipo_peca or "outros",
                  "ingested_at": datetime.now().isoformat()} for i in range(len(chunks))]
        col.upsert(ids=ids, documents=chunks, metadatas=metas)
        self.meta_collection.upsert(ids=[doc_id], documents=[filename], metadatas=[{
            "filename": filename, "file_type": file_type, "chunks": len(chunks),
            "municipio": municipio or "geral", "tipo_peca": tipo_peca or "outros",
            "ingested_at": datetime.now().isoformat()
        }])
        return {"doc_id": doc_id, "chunks": len(chunks)}

    def search(self, query, k=8, municipio=None):
        results = []
        if municipio:
            col = self._get_collection(municipio)
            if col.count() > 0:
                r = col.query(query_texts=[query], n_results=min(4, col.count()))
                results += self._fmt(r)
        if self.collection.count() > 0:
            r = self.collection.query(query_texts=[query], n_results=min(3, self.collection.count()))
            results += self._fmt(r)
        seen, unique = set(), []
        for item in results:
            key = f"{item['doc_id']}_{item['chunk_index']}"
            if key not in seen:
                seen.add(key); unique.append(item)
        return unique[:k]

    def _fmt(self, r):
        out = []
        for i, doc in enumerate(r["documents"][0]):
            m = r["metadatas"][0][i]
            out.append({"text": doc, "filename": m.get("filename",""),
                        "doc_id": m.get("doc_id",""), "chunk_index": m.get("chunk_index",0),
                        "municipio": m.get("municipio","")})
        return out

    async def answer(self, question, mode="consulta", tipo_peca=None,
                     municipio=None, history=[], use_kb=True, use_web=True):
        """
        Pipeline RAG + Web Search.
        use_web=True: Claude pode buscar na internet automaticamente.
        """
        sources = []
        context_str = "Nenhum documento encontrado na base local."

        if use_kb:
            sources = self.search(question, k=8, municipio=municipio)
            if sources:
                context_str = "\n\n---\n\n".join(
                    f"[Arquivo: {s['filename']} | Município: {s['municipio']} | Trecho {s['chunk_index']+1}]\n{s['text']}"
                    for s in sources
                )

        tipo_info = TIPOS_DE_PECAS.get(tipo_peca or mode, {})
        from datetime import date
        system = SYSTEM_PROMPT_BASE.format(
            context=context_str,
            tipo_nome=tipo_info.get("nome", "Peça Jurídica"),
            secoes=", ".join(tipo_info.get("secoes_obrigatorias", [])),
            instrucao=tipo_info.get("instrucao", "Redija com qualidade técnica e linguagem jurídica formal."),
            data_hoje=date.today().strftime("%d/%m/%Y")
        )

        messages = [{"role": h["role"], "content": h["content"]} for h in history[-10:]]
        messages.append({"role": "user", "content": question})

        response, web_sources = await asyncio.to_thread(
            self._call_claude_with_web, system, messages, use_web
        )
        return response, sources, web_sources

    def _call_claude_with_web(self, system, messages, use_web=True):
        """
        Chama Claude com a ferramenta de busca web nativa da Anthropic.
        Claude decide automaticamente quando e o que buscar.
        """
        tools = []
        if use_web:
            tools = [{"type": "web_search_20250305", "name": "web_search"}]

        # Primeira chamada — Claude pode usar web_search
        response = self.client_anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            temperature=0.2,
            system=system,
            tools=tools if tools else [],
            messages=messages
        )

        web_sources = []

        # Loop agentico — processa tool_use até ter resposta final
        while response.stop_reason == "tool_use":
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            tool_results = []

            for tool_use in tool_uses:
                if tool_use.name == "web_search":
                    query = tool_use.input.get("query", "")
                    web_sources.append({"query": query, "tool_use_id": tool_use.id})

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": "Resultado da busca processado."
                })

            # Continua a conversa com os resultados das ferramentas
            messages = messages + [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_results}
            ]

            response = self.client_anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8000,
                temperature=0.2,
                system=system,
                tools=tools,
                messages=messages
            )

        # Extrai texto final
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        return text, web_sources

    def _extract_text(self, content, file_type):
        if file_type == ".pdf":
            return "\n\n".join(p.extract_text() or "" for p in PyPDF2.PdfReader(io.BytesIO(content)).pages)
        elif file_type in (".docx", ".doc"):
            return "\n\n".join(p.text for p in docx.Document(io.BytesIO(content)).paragraphs if p.text.strip())
        elif file_type == ".txt":
            return content.decode("utf-8", errors="ignore")
        return ""

    def _split_chunks(self, text, chunk_size=1200, overlap=200):
        words = text.split()
        chunks, i = [], 0
        while i < len(words):
            chunks.append(" ".join(words[i:i+chunk_size]))
            i += chunk_size - overlap
        return [c for c in chunks if len(c.strip()) > 50]

    def count_documents(self): return self.meta_collection.count()

    def list_tipos_peca(self):
        return [{"id": k, "nome": v["nome"], "sigla": v["sigla"],
                 "categoria": v["categoria"], "secoes": len(v["secoes_obrigatorias"])}
                for k, v in TIPOS_DE_PECAS.items()]

    def list_documents(self, municipio=None, user_id=None):
        if self.meta_collection.count() == 0: return []
        r = self.meta_collection.get(where={"municipio": municipio} if municipio else None)
        docs = [{"doc_id": r["ids"][i], **r["metadatas"][i]} for i in range(len(r["ids"]))]
        # Filtra por user_id se fornecido
        if user_id:
            docs = [d for d in docs if d.get("user_id", "publico") == user_id]
        return docs

    def delete_document(self, doc_id, municipio=None):
        col = self._get_collection(municipio)
        res = col.get(where={"doc_id": doc_id})
        if res["ids"]: col.delete(ids=res["ids"])
        self.meta_collection.delete(ids=[doc_id])
