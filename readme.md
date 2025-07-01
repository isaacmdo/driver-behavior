# Análise de Violações de Motoristas

Este projeto é uma aplicação web interativa para analisar e quantificar a gravidade das violações de motoristas a partir de dados de telemetria. A aplicação permite a configuração de parâmetros de sensibilidade para diferentes tipos de violações, processa um arquivo CSV com os dados das infrações e apresenta um ranking de motoristas com base em um índice de gravidade calculado, além de uma análise detalhada e georreferenciada das ocorrências.

## 📊 Visão Geral

Sistema avançado de análise de telemetria para gestão de frotas, com foco em segurança e eficiência operacional. O dashboard utiliza técnicas state-of-the-art de engenharia de prompt para gerar relatórios personalizados de melhoria de direção.

## 🚀 Funcionalidades Principais

### 📈 Análise de Dados
- **Processamento de CSV**: Upload e análise automática de arquivos de telemetria
- **Cálculo de Pontuação**: Sistema de gravidade baseado em múltiplos fatores
- **Ranking de Motoristas**: Classificação por risco e desempenho
- **Análise Temporal**: Evolução do risco ao longo do tempo

### 🎯 Relatórios Inteligentes
- **Instrutor Virtual**: Relatórios personalizados usando IA avançada
- **Técnicas de Prompt Engineering**: Constitutional AI, Chain-of-Thought, Self-Correction
- **Contexto Geográfico**: Links para mapas das violações
- **Recomendações Práticas**: Dicas acionáveis para melhoria

### 📱 Interface Moderna
- **Design Responsivo**: Funciona em desktop e mobile
- **Tema Escuro**: Interface moderna e profissional
- **Gráficos Interativos**: Visualizações dinâmicas com Plotly
- **Exportação**: Relatórios em HTML para impressão

## Arquitetura e Fluxo da Aplicação

A aplicação segue um fluxo simples e interativo, projetado para ser intuitivo para o usuário final.

1.  **Configuração de Parâmetros**: Na tela inicial, o usuário pode ajustar os pesos e limites para cada tipo de violação. Valores padrão já vêm pré-configurados.
2.  **Upload de Dados**: O usuário realiza o upload de um arquivo `.csv` contendo os registros de violações.
3.  **Processamento e Análise**: O script `main.py` processa o arquivo, aplicando as regras de negócio e os parâmetros definidos para calcular um índice de gravidade para cada evento.
4.  **Visualização dos Resultados**: A aplicação exibe os resultados em três seções principais:
    * **Ranking de Motoristas**: Uma tabela com os motoristas ordenados pelo somatório do índice de gravidade de suas violações.
    * **Detalhes das Violações**: Uma tabela detalhada com todas as violações processadas, incluindo o índice de gravidade individual calculado para cada uma.

## Estrutura do Arquivo de Entrada (CSV)

Para a correta inicialização e processamento, a aplicação requer um arquivo CSV com a seguinte estrutura e colunas. O delimitador utilizado deve ser o ponto e vírgula (**;**).

| Coluna | Descrição | Exemplo |
| :--- | :--- | :--- |
| `Nome da conta` | Nome da transportadora ou cliente. | Transportadora XYZ |
| `Nome do veículo` | Identificação (nome, placa) do veículo. | SCANIA-P320 |
| `Número do veículo` | Código/número interno do veículo. | 10520 |
| `Motorista` | Nome do motorista responsável. | João da Silva |
| `CPF` | CPF do motorista (usado como identificador único). | 123.456.789-00 |
| `Violação` | O tipo de infração cometida. | Velocidade Excessiva |
| `Data inicial da violação`| Data e hora do início do evento. | 01/06/2024 08:00 |
| `Data final da violação` | Data e hora do fim do evento. | 01/06/2024 08:02 |
| `Duração` | Duração total do evento. | 00:02:00 |
| `Velocidade inicial` | Velocidade no início do evento (km/h). | 80 |
| `Velocidade final` | Velocidade no fim do evento (km/h). | 95 |
| `Velocidade máxima` | Velocidade máxima atingida (km/h). | 110 |
| `Valor inicial da velocidade configurada` | Limite de velocidade na via (km/h). | 90 |
| `Valor final da velocidade configurada`| Limite de velocidade na via (km/h). | 90 |
| `RPM inicial` | Rotações por minuto no início. | 1500 |
| `RPM final` | Rotações por minuto no fim. | 2200 |
| `RPM máximo` | Rotações por minuto máximas. | 2500 |
| `Valor inicial do RPM configurado`| Limite inferior da faixa verde. | 1200 |
| `Valor final do RPM configurado` | Limite superior da faixa verde. | 1800 |
| `Hodômetro inicial` | Hodômetro no início (km). | 150000 |
| `Hodômetro final` | Hodômetro no fim (km). | 150003 |
| `Distância` | Distância percorrida durante a violação (km). | 3 |
| `Latitude inicial` | Latitude do início da violação. | -26.3034 |
| `Latitude final` | **Longitude** do início da violação. | -48.8457 |
| `Pedal de freio` | Indica se o freio foi acionado (Sim/Não). | Não |
| `Posição do Acelerador` | Percentual de uso do acelerador (%). | 85 |

**Nota Importante**: A coluna `Latitude final` é interpretada como a **Longitude** para formar o par de coordenadas geográficas (Latitude, Longitude).

## 🧠 Técnicas de IA Implementadas

### 1. **Constitutional AI**
- Princípios éticos embutidos no prompt
- Feedback construtivo e respeitoso
- Foco em segurança e melhoria

### 2. **Chain-of-Thought (CoT)**
- Processamento em etapas lógicas
- Análise estruturada dos dados
- Síntese progressiva da informação

### 3. **Self-Correction/Reflection**
- Validação automática das respostas
- Verificação de formato e conteúdo
- Tratamento de erros robusto

### 4. **Estruturação XML**
- Tags hierárquicas para clareza
- Redução de ambiguidade
- Melhor parsing pelo modelo

### 5. **Few-Shot Learning**
- Exemplos concretos no prompt
- Padrões de resposta consistentes
- Melhoria da qualidade da saída

```xml
<prompt>
    <system_setup>
        <persona>
            ...
        </persona>
        <guiding_principles name="Constitutional AI">
            <principle>...</principle>
            <principle>...</principle>
        </guiding_principles>
    </system_setup>

    <task_definition>
        <goal>...</goal>
        <output_format>
           ...
        </output_format>
    </task_definition>

    <examples>
        <example name="...">
            <input_data>
                <driver_name>...</driver_name>
                <total_score>...</total_score>
                <violations_summary>
                    ...
                </violations_summary>
            </input_data>
            <output_report>
                ...
            </output_report>
        </example>
    </examples>

    <final_task>
        <context>
            <driver_name>...</driver_name>
            <total_score>...</total_score>
        </context>
        <input_data>
            <violations_summary>
                ...
            </violations_summary>
            <violations_summary>
                ...
            </violations_summary>
        </input_data>
        <instruction>
            ...
        </instruction>
    </final_task>
</prompt>
```


## Regras de Negócio (Cálculo de Gravidade)

O "índice de gravidade" é o principal indicador para avaliar o comportamento do motorista. Ele é calculado para cada violação com base em regras específicas, que podem ser ajustadas na interface da aplicação.

---

### **TOP 1: "Velocidade Excessiva"**
A pontuação varia conforme o tipo de via (A coluna "Valor inicial da velocidade configurada" determina qual a variação e tipo de violação. Se a coluna "Valor inicial da velocidade configurada" estivar abaixo de 40, será Pátio, abaixo de 90 será Serra, igual ou acima de 90 será Rodovia)
* *Este evento será gerado quando o veículo permanecer, por um tempo superior à tolerância, com a velocidade
acima do valor máximo configurado de condução em pista seca.*

* **Rodovia (Limite: 90 km/h)**
    * **Gravidade base**: 0.2 por violação.
    * **Incremento por gravidade**:
        * +0.2 a cada 5 km/h acima do limite.
        * +0.4 (adicional) para velocidades acima de 100 km/h.
    * **Incremento por duração**: +0.1 a cada 10 segundos de duração do evento.

* **Serra (Limite: 40 km/h)**
    * **Gravidade base**: 0.1 por violação.
    * **Incremento por gravidade**:
        * +0.1 a cada 5 km/h acima do limite.
        * +0.2 (adicional) para velocidades acima de 65 km/h.
    * **Incremento por duração**: +0.05 a cada 10 segundos de duração.

* **Pátio (Limite: 21 km/h)**
    * **Gravidade base**: 0.1 por violação.
    * **Incremento por gravidade**: +0.1 a cada 5 km/h acima do limite.
    * **Incremento por duração**: +0.05 a cada 10 segundos de duração.

---

### **TOP 2: "Marcha Lenta"**
* Eventos com duração inferior a 10 minutos são desconsiderados.
* **Gravidade base**: 0.1 por violação válida.
* **Incremento por duração**: +0.1 a cada 20 minutos de duração.
* *Este evento registra o tempo em que o veículo permanece parado e com o motor ligado, iniciando a contagem
quando o RPM estiver com o valor diferente de zero e com velocidade abaixo de 5km/h. Finalizando a contagem
quando o valor do RPM ficar com o valor zero ou quando a velocidade apresentar um valor superior a 5km/h.
Em ambos os casos, o tempo sempre tem que ser superior à tolerância configurada.*
---

### **TOP 3: "Freada Brusca"**

* **Gravidade base**: 0.1 por violação.
* *Sem fator de incremento.*
* *Este evento será gerado quando houver uma redução na velocidade acima do valor configurado em um segundo.*
---

### **TOP 4: "RPM Excessiva"**
* **Gravidade base**: 0.07 por violação.
* **Incremento por duração**: +0.07 a cada 30 segundos de duração.
* *Este evento será gerado quando o veículo permanecer, por um tempo superior à tolerância, com o valor do RPM acima do valor configurado.*
---

### **TOP 5: "Faixa Verde"**
* Refere-se ao tempo de condução fora da faixa de RPM ideal (faixa verde de economia).
* **Gravidade base**: 0.07 por violação.
* **Incremento por duração**: +0.07 a cada 3 minutos de duração.
* *Esse evento registra o tempo em que um veículo permanece fora da faixa ideal de rotação do motor, iniciando a
contagem quando o RPM estiver abaixo ou acima dos limites configurados. Finalizando a contagem quando o
RPM retornar aos valores da faixa verde ou zerar o valor, e, em ambos os casos, o tempo sempre tem que ser no
caso de valores de RPM acima dos limites configurados, também e levado em consideracão o acionamento do
pedal do acelerador, caso esse não esteja acionado, o evento não é registrado, pois neste cenário o veículo está
utilizando o freio motor.*
---

### **TOP 6: "Freio Motor"**
* **Gravidade base**: 0.07 por violação.
* **Incremento por duração**: +0.07 a cada 2 minutos de duração.
* *Este evento registra o tempo em que o veículo permanece em uso do freio motor, iniciando a contagem quando
o RPM estiver com um valor entre o limite superior configurado no evento de fora da faixa verde e o limite
configurado no evento de excesso de RPM e sem acionamento do pedal do acelerador. Finalizando a contagem
quando o valor do RPM ficar fora do intervalo mencionado acima ou quando o pedal do acelerador for acionado.
Em ambos os casos, o tempo sempre tem que ser superior à tolerância configurada.*


## Features e Funcionalidades do Projeto

Além das regras de negócio e visualizações básicas descritas acima, o sistema foi ampliado com recursos avançados para análise de risco, categorização e relatórios, tornando a solução mais robusta e útil para gestão de frotas e motoristas:

### 1. **Ranking por Veículo**
- Implementado ranking de risco por veículo, com KPIs, tabelas e gráficos específicos, permitindo identificar veículos com maior concentração de violações e risco.

### 2. **Classificação de Violações por Categoria**
- Todas as violações são classificadas em duas categorias:
  - **Econômica**: Freio motor, RPM excessiva, Marcha lenta, Faixa verde.
  - **Segurança**: Velocidade excessiva, Freada brusca.
- Essa classificação é usada em todos os dashboards, rankings e relatórios.

### 3. **Indicadores de Categoria (Econômica e Segurança)**
- **Na aba "Visão Geral da Frota"**:
  - KPIs de "Pontuação Econômica" (amarelo/laranja) e "Pontuação Segurança" (vermelho).
  - Barra de distribuição mostrando o percentual de cada categoria na pontuação total da frota.
  - Legenda explicando quais violações pertencem a cada categoria.
- **Na análise individual do motorista**:
  - KPIs de pontuação total, econômica e de segurança.
  - Barra de distribuição por categoria, com percentuais e legenda.
- **Nos rankings por categoria**:
  - Rankings e gráficos específicos para cada categoria, tanto para motoristas quanto para veículos.

### 4. **Relatórios HTML Detalhados**
- Exportação de relatório individual do motorista em HTML, incluindo:
  - KPIs de categoria.
  - Barra de distribuição por categoria.
  - Tabelas de violações separadas por categoria, com cores e destaques visuais.
  - Legenda das categorias.

### 5. **Consistência Visual e Cores**
- Cores padronizadas para cada categoria em todos os gráficos, KPIs e tabelas:
  - Econômica: amarelo/laranja.
  - Segurança: vermelho.

### 6. **Testes Automatizados**
- Scripts de teste para garantir o correto funcionamento dos rankings, indicadores de categoria e exportação de relatórios.

### 7. **Aprimoramentos Gerais**
- Correções de bugs e melhorias de performance.
- Ajustes de layout para melhor experiência do usuário.
- Mensagens e legendas explicativas para facilitar a interpretação dos dados.

**Resumo:**  
O sistema oferece uma análise muito mais detalhada e segmentada do risco, tanto para motoristas quanto para veículos, com indicadores claros de segurança e economia, rankings por categoria, relatórios completos e visualização intuitiva. Isso permite uma gestão proativa e direcionada, facilitando ações corretivas e preventivas na frota.

## 🛠️ Como Executar o Projeto

### Requisitos
```bash
pip install -r requirements.txt
```

### Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto com a seguinte configuração:

```bash
# Chave da API Gemini (Google AI)
# Obtenha sua chave em: https://makersuite.google.com/app/apikey
GEMINI_API_KEY=sua_chave_aqui
```

**Importante:** Substitua `sua_chave_aqui` pela chave real da API Gemini.

Para mais detalhes sobre a configuração, consulte o arquivo `ENV_SETUP.md`.

### Execução

#### Aplicação
```bash
python main.py
```


## Como Publicar o Projeto

Este é um projeto Streamlit. Para executá-lo, siga os passos abaixo:

1.  **Clone o repositório (se aplicável)**
    ```bash
    git clone <url-do-repositorio>
    cd <diretorio-do-projeto>
    ```

2.  **Crie um ambiente virtual (recomendado)**
    ```bash
    python -m venv venv
    source venv/bin/activate  # No Windows: venv\Scripts\activate
    ```

3.  **Instale as dependências**
    O arquivo `requirements.txt` contém todas as bibliotecas necessárias.
    ```bash
    pip install -r requirements.txt
    ```

4.  **Execute a aplicação**
    O `Procfile` indica o comando de execução. Use o comando abaixo no seu terminal:
    ```bash
    streamlit run drivers-management/main.py
    ```

5.  **Acesse no navegador**
    Abra o navegador e acesse o endereço local fornecido pelo Streamlit (geralmente `http://localhost:8501`).


## 🔧 Arquitetura Técnica

### Frontend
- **Dash/Plotly**: Framework web para dashboards
- **HTML/CSS**: Interface responsiva
- **JavaScript**: Interatividade dos gráficos

### Backend
- **Python**: Lógica de processamento
- **Pandas**: Manipulação de dados
- **Requests**: Integração com APIs

### IA/ML
- **Google Gemini**: Modelo de linguagem
- **Prompt Engineering**: Técnicas de prompt
- **Markdown**: Formatação de relatórios


## 🔒 Segurança

### Autenticação
- Sistema de login básico
- Proteção por usuário e senha
- Acesso restrito ao dashboard

### Dados
- Processamento local dos arquivos
- Não armazenamento permanente
- Links seguros para mapas

