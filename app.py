import streamlit as st
import pandas as pd
import pdfplumber
import re
from io import BytesIO

def extrair_dados_pdf(arquivo_pdf):
    """
    Processa um único arquivo PDF para extrair TODAS as ocorrências 
    de data e saldo do dia.
    
    Retorna uma lista de tuplas [(data, saldo), ...] ou uma string de erro.
    """
    texto_completo = ""
    resultados_encontrados = []

    try:
        # 1. Extrair todo o texto do PDF
        with pdfplumber.open(arquivo_pdf) as pdf:
            for pagina in pdf.pages:
                texto_pagina = pagina.extract_text()
                if texto_pagina:
                    texto_completo += texto_pagina + "\n"
        
        # 2. Expressão Regular (Regex) Corrigida
        # A nova regex é mais específica para a estrutura da linha:
        # DATA [Nr. Doc.] SALDO DIA [VALOR DA TRANSACAO] [SALDO FINAL]
        # O objetivo é capturar o Grupo 1 (Data) e o Grupo 2 (Saldo Final).
        #
        # Componentes da Regex:
        # (\d{2}/\d{2}/\d{2,4})         -> Grupo 1: Captura a data (ex: 01/09/2025)
        # \s+\d+\s+SALDO DIA            -> Corresponde ao Nr. Doc. e à palavra "SALDO DIA"
        # \s+[\d\.],\d{2}\s[CD]?      -> Corresponde ao valor da transação (ex: 0,00 C) e o ignora
        # \s+([\d\.],\d{2})\s[CD]?    -> Grupo 2: Captura o Saldo Final (ex: 15.043,90 C)
        regex_saldo_dia = re.compile(
            r"(\d{2}/\d{2}/\d{2,4})\s+\d+\s+SALDO DIA\s+[\d\.],\d{2}\s[CD]?\s+([\d\.],\d{2})\s[CD]?",
            re.IGNORECASE
        )

        # 3. Encontrar TODAS as ocorrências
        matches = regex_saldo_dia.finditer(texto_completo)

        for match in matches:
            data = match.group(1)
            saldo_bruto = match.group(2).strip()
            
            # Remove pontos de milhar para consistência no formato do Excel.
            # Mantém a vírgula como separador decimal.
            saldo_limpo = saldo_bruto.replace(".", "")
            
            # Adiciona o resultado à lista
            resultados_encontrados.append((data, saldo_limpo))
        
        # Retorna a lista de tuplas (data, saldo)
        return resultados_encontrados

    except Exception as e:
        # Mostra o erro no Streamlit e retorna uma string para o main tratar
        st.error(f"Erro ao processar o arquivo: {e}")
        return "Erro na leitura"

def main():
    st.set_page_config(layout="wide", page_title="Extrator de Saldos")
    st.title("📌 Extrator de Saldo Diário de Extratos (PDF)")
    st.markdown("Faça upload de um ou mais arquivos PDF (extratos razão) para extrair a data e o 'Saldo do dia'.")

    # 1. Upload de Arquivos
    uploaded_files = st.file_uploader(
        "Selecione os arquivos PDF",
        type="pdf",
        accept_multiple_files=True
    )

    # Inicialização do estado de sessão para armazenar os resultados
    if 'df_resultados' not in st.session_state:
        st.session_state.df_resultados = pd.DataFrame(columns=["Arquivo", "Data", "Saldo do Dia"])

    if st.button("Processar Arquivos"):
        if uploaded_files:
            lista_resultados = []
            
            # Barra de progresso
            progress_bar = st.progress(0)
            total_files = len(uploaded_files)
            
            for i, file in enumerate(uploaded_files):
                st.info(f"Processando: {file.name}...")
                
                # 3. Processamento
                # O arquivo é passado em formato de bytes para pdfplumber
                resultados_extracao = extrair_dados_pdf(file)
                
                # Verifica se o retorno é uma LISTA (sucesso)
                if isinstance(resultados_extracao, list):
                    
                    if not resultados_extracao:
                        # Se a lista estiver vazia, o padrão não foi encontrado
                        lista_resultados.append({
                            "Arquivo": file.name,
                            "Data": "N/A",
                            "Saldo do Dia": "Saldo não encontrado"
                        })
                    else:
                        # Adiciona o nome do arquivo a cada linha de resultado (requisito do usuário)
                        for data_ext, saldo_ext in resultados_extracao:
                            lista_resultados.append({
                                "Arquivo": file.name,
                                "Data": data_ext,
                                "Saldo do Dia": saldo_ext
                            })
                
                # Se não for lista, é uma string de erro
                elif resultados_extracao == "Erro na leitura":
                    lista_resultados.append({
                        "Arquivo": file.name,
                        "Data": "N/A",
                        "Saldo do Dia": "Erro ao ler PDF"
                    })
                
                # Atualiza a barra de progresso
                progress_bar.progress((i + 1) / total_files)

            st.session_state.df_resultados = pd.DataFrame(lista_resultados)
            st.success("Processamento concluído! Confira os resultados abaixo.")

        else:
            st.warning("Por favor, faça upload de pelo menos um arquivo PDF.")

    # 4. Mostrar Resultados e Botão de Download
    if not st.session_state.df_resultados.empty:
        df = st.session_state.df_resultados
        
        st.subheader("Resultados do Processamento")

        # 4a. Arquivos com sucesso
        sucesso_df = df[~df["Saldo do Dia"].isin(["Saldo não encontrado", "Erro ao ler PDF"])]
        if not sucesso_df.empty:
            st.markdown("✅ *Saldos diários encontrados:*")
            # Adiciona a coluna 'Arquivo' para mostrar o nome do PDF de origem
            st.dataframe(sucesso_df[["Arquivo", "Data", "Saldo do Dia"]], use_container_width=True)
        
        # 4b. Arquivos com falha
        falha_df = df[df["Saldo do Dia"].isin(["Saldo não encontrado", "Erro ao ler PDF"])]
        if not falha_df.empty:
            st.markdown("⚠ *Arquivos onde o saldo não foi encontrado ou houve erro:*")
            st.dataframe(falha_df[["Arquivo", "Saldo do Dia"]], use_container_width=True)
            
        # 5. Botão de Download do Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Saldos Extraídos')
        
        output.seek(0) 

        st.download_button(
            label="Download da Planilha Excel",
            data=output,
            file_name="relatorio_saldos_extraidos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if _name_ == "_main_":
    main()