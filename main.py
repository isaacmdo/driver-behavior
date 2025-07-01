import pandas as pd
import re
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State, ALL
import plotly.graph_objects as go
import base64
import io
import requests
import json
from datetime import datetime
from markdown import markdown
from flask import request, Response
import time
import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Dicionário de usuários e senhas
USERS = {
    'admin': '123'
}

def check_auth(username, password):
    return username in USERS and USERS[username] == password

def authenticate():
    """Envia resposta 401 para ativar o pop-up nativo de login do navegador"""
    return Response(
        'Login necessário!\n',
        401,
        {'WWW-Authenticate': 'Basic realm="Dashboard Protegido"'}
    )



# --- CONFIGURAÇÃO DA LÓGICA DE GRAVIDADE (VALORES PADRÃO) ---
DEFAULT_GRAVITY_CONFIG = {
    "Velocidade_Excessiva_Rodovia": {
        "base_weight": 0.2, "speed_increment": 5, "speed_factor": 0.2,
        "speed_factor_high": 0.4, "speed_threshold_high": 100,
        "duration_increment": 10, "duration_factor": 0.1,
    },
    "Velocidade_Excessiva_Serra": {
        "base_weight": 0.1, "speed_increment": 5, "speed_factor": 0.1,
        "speed_factor_high": 0.2, "speed_threshold_high": 65,
        "duration_increment": 10, "duration_factor": 0.05,
    },
    "Velocidade_Excessiva_Patio": {
        "base_weight": 0.1, "speed_increment": 5, "speed_factor": 0.1,
        "duration_increment": 10, "duration_factor": 0.05,
    },
    "Marcha_lenta": {
        "base_weight": 0.1, "duration_increment": 1200, "duration_factor": 0.1, # 20 minutos
        "min_duration_filter": 600 # 10 minutos
    },
    "Freada_Brusca": {
        "base_weight": 0.1,
    },
    "RPM_Excessiva": {
        "base_weight": 0.07, "duration_increment": 30, "duration_factor": 0.07,
    },
    "Faixa_Verde": {
        "base_weight": 0.07, "duration_increment": 180, "duration_factor": 0.07, # 3 minutos
    },
    "Freio_Motor": {
        "base_weight": 0.07, "duration_increment": 120, "duration_factor": 0.07, # 2 minutos
    }
}
# Tipos de violações que serão processadas. "Banguela" foi removida.
VIOLATION_TYPES = ["Velocidade excessiva", "Marcha lenta", "Freada brusca", "RPM excessiva", "Faixa verde", "Freio motor"]

# Classificação das violações por categoria
VIOLATION_CATEGORIES = {
    "Econômica": ["Freio motor", "RPM excessiva", "Marcha lenta", "Faixa verde"],
    "Segurança": ["Velocidade excessiva", "Freada brusca"]
}

# Cores para as categorias
CATEGORY_COLORS = {
    "Econômica": "#F59E0B",  # Amarelo/Laranja
    "Segurança": "#EF4444"   # Vermelho
}

# --- FUNÇÕES DE PROCESSAMENTO DE DADOS ---

def dms_to_dd(dms_str):
    if not isinstance(dms_str, str): return None
    try:
        parts = re.findall(r'[\d,.]+|[NSLOEWnsloew]', dms_str)
        if len(parts) < 4: raise ValueError("Formato DMS inválido")
        degrees = float(parts[0].replace(',', '.'))
        minutes = float(parts[1].replace(',', '.'))
        seconds = float(parts[2].replace(',', '.'))
        direction = parts[3].upper()
        dd = degrees + minutes / 60 + seconds / 3600
        if direction in ['S', 'SUL', 'W', 'O', 'OESTE']: dd = -dd
        return dd
    except (ValueError, IndexError):
        try: return float(dms_str.replace(',', '.'))
        except (ValueError, TypeError): return None

def convert_seconds_to_hhmm(seconds):
    """Converte segundos em formato HH:MM"""
    if pd.isna(seconds) or seconds == 0:
        return "00:00"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours:02d}:{minutes:02d}"

def convert_duration_to_seconds(duration_str):
    if not isinstance(duration_str, str): return 0
    try:
        h, m, s = map(int, duration_str.split(':'))
        return h * 3600 + m * 60 + s
    except (ValueError, TypeError): return 0

def generate_maps_route_link(lat_i, lon_i, lat_f, lon_f):
    if pd.isna(lat_i) or pd.isna(lon_i) or pd.isna(lat_f) or pd.isna(lon_f):
        return "Percurso indisponível"
    if lat_i == lat_f and lon_i == lon_f:
        return f"https://www.google.com/maps?q={lat_i},{lon_i}"
    return f"https://www.google.com/maps/dir/{lat_i},{lon_i}/{lat_f},{lon_f}"

def clean_column_names(df):
    new_columns = {col: col.strip().lower().replace(' ', '_').replace('ã', 'a').replace('ç', 'c') for col in df.columns}
    df = df.rename(columns=new_columns)
    rename_map = {
        'latitude_inicial': 'latitude_inicial', 'longitude_inicial': 'longitude_inicial',
        'latitude_final': 'latitude_final', 'longitude_final': 'longitude_final',
        'data_inicial_da_violacao': 'data_evento'
    }
    df = df.rename(columns=rename_map)
    return df
    
def calculate_event_gravity_factor(row, gravity_config):
    """Calcula o Fator de Gravidade para uma única violação (linha)."""
    viol_type = row.get('violacao')
    factor = 1.0
    duration = row.get('duracao_seconds', 0)

    if viol_type == "Velocidade excessiva":
        limite = row.get('valor_final_da_velocidade_configurada', 0)
        # Categoriza a violação
        if limite <= 20: conf = gravity_config["Velocidade_Excessiva_Patio"]
        elif limite <= 40: conf = gravity_config["Velocidade_Excessiva_Serra"]
        else: conf = gravity_config["Velocidade_Excessiva_Rodovia"]
        
        extrapolation = row.get('velocidade_maxima', 0) - limite
        if extrapolation > 0 and conf.get('speed_increment', 0) > 0:
            speed_multiplier = conf.get('speed_factor_high', conf['speed_factor']) if 'speed_threshold_high' in conf and row.get('velocidade_maxima', 0) > conf['speed_threshold_high'] else conf['speed_factor']
            factor += (extrapolation / conf['speed_increment']) * speed_multiplier
        if duration > 0 and conf.get('duration_increment', 0) > 0:
            factor += (duration / conf['duration_increment']) * conf.get('duration_factor')
            
    elif viol_type == "Marcha lenta":
        conf = gravity_config["Marcha_lenta"]
        if duration >= conf.get('min_duration_filter', 600) and row.get('pedal_de_freio', '').lower() != 'sim' and conf.get('duration_increment', 0) > 0:
            factor += (duration / conf['duration_increment']) * conf.get('duration_factor')
            
    elif viol_type in ["RPM excessiva", "Freio motor", "Faixa verde"]:
        conf_map = {"RPM excessiva": "RPM_Excessiva", "Freio motor": "Freio_Motor", "Faixa verde": "Faixa_Verde"}
        conf = gravity_config[conf_map[viol_type]]
        if duration > 0 and conf.get('duration_increment', 0) > 0:
             factor += (duration / conf['duration_increment']) * conf.get('duration_factor')

    elif viol_type == "Freada brusca":
        # Freada brusca não tem fator de gravidade, pontuação fixa de 0.1 por violação
        factor = 0.0
        
    return factor

def process_uploaded_data(contents, filename, gravity_config):
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    try:
        if 'csv' not in filename: return None, None, html.Div(['O arquivo precisa ser um .CSV.'])
        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), delimiter=';', on_bad_lines='warn').fillna(0)
        df = clean_column_names(df)
        
        # Adicionar índice da linha do CSV (começando de 2 para considerar o header como linha 1)
        df['linha_csv'] = df.index + 2

        df = df[df['violacao'].isin(VIOLATION_TYPES)]

        if 'data_evento' not in df.columns: return None, None, html.Div(['Coluna de data ("Data inicial da violação") não encontrada.'])
        df['data_evento'] = pd.to_datetime(df['data_evento'], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['data_evento'])

        # Remover pontos dos valores de rpm_máximo de forma inteligente
        # Se termina com .0, remove apenas o .0
        # Se tem ponto no meio (como 1.644), remove o ponto
        for rpm_col in ['rpm_máximo', 'rpm_maximo']:
            if rpm_col in df.columns:
                series = pd.Series(df[rpm_col]).astype(str)
                series = series.str.replace(r'\.0$', '', regex=True)  # Remove .0 no final
                series = series.str.replace('.', '', regex=False)  # Remove outros pontos
                df[rpm_col] = series

        numeric_cols = ['velocidade_maxima', 'valor_final_da_velocidade_configurada', 'rpm_maximo', 'valor_final_do_rpm_configurado', 'distancia', 'velocidade_inicial', 'velocidade_final']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].fillna(0)

        if 'rpm_máximo' in df.columns:
            df['rpm_máximo'] = pd.to_numeric(df['rpm_máximo'], errors='coerce')
            df['rpm_máximo'] = df['rpm_máximo'].fillna(0)

        coord_cols = ['latitude_inicial', 'longitude_inicial', 'latitude_final', 'longitude_final']
        for col in coord_cols:
            if col in df.columns: 
                df[col] = df[col].apply(dms_to_dd)
        
        df['duracao_seconds'] = df['duracao'].apply(convert_duration_to_seconds)
        df['fator_gravidade_evento'] = df.apply(calculate_event_gravity_factor, axis=1, gravity_config=gravity_config)

        # Contagem de violações por motorista e tipo (para referência, mas não para multiplicação)
        counts = df.groupby(['motorista', 'violacao']).size().reset_index(name='qtd_violacoes')
        df = pd.merge(df, counts, on=['motorista', 'violacao'], how='left')
        
        def get_base_weight(viol_type, limite):
            if viol_type == 'Velocidade excessiva':
                if limite <= 20: return gravity_config["Velocidade_Excessiva_Patio"]['base_weight']
                elif limite > 20 and limite <= 40: return gravity_config["Velocidade_Excessiva_Serra"]['base_weight']
                else: return gravity_config["Velocidade_Excessiva_Rodovia"]['base_weight']
            else:
                conf_map = {"Marcha lenta": "Marcha_lenta", "Freada brusca": "Freada_Brusca", "RPM excessiva": "RPM_Excessiva", "Faixa verde": "Faixa_Verde", "Freio motor": "Freio_Motor"}
                key = conf_map.get(viol_type)
                return gravity_config.get(key, {}).get('base_weight', 0)

        # Cada violação tem pontuação individual baseada em seu próprio fator de gravidade
        df['score_final'] = df.apply(lambda row: get_base_weight(row['violacao'], row['valor_final_da_velocidade_configurada']) * row.get('fator_gravidade_evento', 1), axis=1)
        
        # Correção especial para Freada brusca: apenas base_weight por violação, sem multiplicadores
        freada_brusca_mask = df['violacao'] == 'Freada brusca'
        if freada_brusca_mask.any():
            df.loc[freada_brusca_mask, 'score_final'] = gravity_config.get('Freada_Brusca', {}).get('base_weight', 0.1)
        
        # Ranking por motorista
        ranking_list = []
        for driver, group in df.groupby('motorista'):
            if not driver: continue
            total_score = group['score_final'].sum()
            violation_scores = group.groupby('violacao')['score_final'].sum().to_dict()
            summary = {'Motorista': driver, 'Pontuação Total': total_score}
            for v_type in VIOLATION_TYPES:
                summary[v_type] = violation_scores.get(v_type, 0)
            ranking_list.append(summary)

        ranking_df = pd.DataFrame(ranking_list)
        
        # Ranking por veículo
        ranking_veiculo_list = []
        for veiculo, group in df.groupby('nome_do_veículo'):
            if not veiculo: continue
            total_score = group['score_final'].sum()
            violation_scores = group.groupby('violacao')['score_final'].sum().to_dict()
            summary = {'Veículo': veiculo, 'Pontuação Total': total_score}
            for v_type in VIOLATION_TYPES:
                summary[v_type] = violation_scores.get(v_type, 0)
            ranking_veiculo_list.append(summary)

        ranking_veiculo_df = pd.DataFrame(ranking_veiculo_list)
        
        return df, ranking_df, None

    except Exception as e:
        print(f"Erro no processamento: {e}")
        # Rankings por categoria - Motoristas
        ranking_categoria_motorista_list = []
        for driver, group in df.groupby('motorista'):
            if not driver: continue
            total_score = group['score_final'].sum()
            economica_score = group[group['violacao'].isin(VIOLATION_CATEGORIES['Econômica'])]['score_final'].sum()
            seguranca_score = group[group['violacao'].isin(VIOLATION_CATEGORIES['Segurança'])]['score_final'].sum()
            summary = {
                'Motorista': driver, 
                'Pontuação Total': total_score,
                'Pontuação Econômica': economica_score,
                'Pontuação Segurança': seguranca_score,
                'Percentual Econômica': (economica_score / total_score * 100) if total_score > 0 else 0,
                'Percentual Segurança': (seguranca_score / total_score * 100) if total_score > 0 else 0
            }
            ranking_categoria_motorista_list.append(summary)
        ranking_categoria_motorista_df = pd.DataFrame(ranking_categoria_motorista_list)
        
        # Rankings por categoria - Veículos
        ranking_categoria_veiculo_list = []
        for veiculo, group in df.groupby('nome_do_veículo'):
            if not veiculo: continue
            total_score = group['score_final'].sum()
            
            # Calcula pontuação por categoria
            economica_score = group[group['violacao'].isin(VIOLATION_CATEGORIES['Econômica'])]['score_final'].sum()
            seguranca_score = group[group['violacao'].isin(VIOLATION_CATEGORIES['Segurança'])]['score_final'].sum()
            
            summary = {
                'Veículo': veiculo, 
                'Pontuação Total': total_score,
                'Pontuação Econômica': economica_score,
                'Pontuação Segurança': seguranca_score,
                'Percentual Econômica': (economica_score / total_score * 100) if total_score > 0 else 0,
                'Percentual Segurança': (seguranca_score / total_score * 100) if total_score > 0 else 0
            }
            ranking_categoria_veiculo_list.append(summary)

        ranking_categoria_veiculo_df = pd.DataFrame(ranking_categoria_veiculo_list)
        
        return df, ranking_df, ranking_categoria_motorista_df, None

    except Exception as e:
        print(f"Erro no processamento: {e}")
        return None, None, html.Div([f'Ocorreu um erro ao processar o arquivo: {e}'])


# --- INICIALIZAÇÃO DO APP DASH ---
app = dash.Dash(__name__, suppress_callback_exceptions=True)
server = app.server

# Protege toda a aplicação (exceto arquivos estáticos)
@server.before_request
def require_authentication():
    if request.path.startswith("/assets") or request.path.startswith("/static"):
        return  # Libera assets do Dash
    auth = request.authorization
    if not auth or not check_auth(auth.username, auth.password):
        return authenticate()

# --- ESTILIZAÇÃO ---
colors = {'background': '#111827', 'card_bg': '#1F2937', 'text': '#E5E7EB', 'text_light': '#9CA3AF', 'border': '#374151', 'accent_blue': '#3B82F6', 'accent_red': '#EF4444', 'accent_yellow': '#F59E0B', 'accent_purple': '#8B5CF6', 'accent_orange': '#FB923C', 'accent_green': '#10B981'}
kpi_card_style = {'backgroundColor': colors['card_bg'], 'padding': '20px', 'border': f"1px solid {colors['border']}", 'borderRadius': '8px', 'textAlign': 'center'}

# Estilo melhorado para upload
upload_style = {
    'width': '100%', 
    'height': '120px', 
    'lineHeight': '120px', 
    'borderWidth': '3px', 
    'borderStyle': 'dashed', 
    'borderRadius': '12px', 
    'textAlign': 'center', 
    'margin': '20px 0', 
    'borderColor': colors['accent_blue'],
    'backgroundColor': colors['card_bg'],
    'color': colors['text'],
    'fontSize': '16px',
    'fontWeight': '500',
    'cursor': 'pointer',
    'transition': 'all 0.3s ease',
    'position': 'relative',
    'overflow': 'hidden'
}

# Estilo para hover do upload
upload_style_hover = {
    'borderColor': colors['accent_yellow'],
    'backgroundColor': '#374151',
    'transform': 'scale(1.02)',
    'boxShadow': f'0 4px 12px rgba(59, 130, 246, 0.3)'
}

# Estilo para o botão "Analisar Outro Arquivo"
back_button_style = {
    'backgroundColor': colors['accent_blue'],
    'color': 'white',
    'border': 'none',
    'padding': '12px 24px',
    'borderRadius': '8px',
    'cursor': 'pointer',
    'fontWeight': '600',
    'fontSize': '14px',
    'marginBottom': '20px',
    'transition': 'all 0.3s ease',
    'boxShadow': '0 2px 4px rgba(59, 130, 246, 0.2)',
    'display': 'flex',
    'alignItems': 'center',
    'gap': '8px'
}

tab_style = {'borderBottom': f"1px solid {colors['border']}", 'padding': '6px', 'backgroundColor': colors['card_bg'], 'color': colors['text_light']}
tab_selected_style = {'borderTop': f"2px solid {colors['accent_blue']}", 'borderBottom': f"1px solid {colors['background']}", 'backgroundColor': colors['background'], 'color': 'white', 'padding': '6px', 'fontWeight': 'bold'}

# CSS responsivo para esconder parâmetros em dispositivos móveis
responsive_css = """
<style>
    @media (max-width: 768px) {
        #parameters-section {
            display: none !important;
        }
        .mobile-info {
            display: block !important;
            background-color: #1F2937;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid #374151;
            text-align: center;
        }
    }
    @media (min-width: 769px) {
        .mobile-info {
            display: none !important;
        }
    }
</style>
"""

# --- FUNÇÕES DE LAYOUT ---
def get_documentation_for_violation(viol_type_key):
    """Retorna a documentação completa para cada violação."""
    docs = {
        "Velocidade_Excessiva_Rodovia": """
        **🏛️ Rodovia (Limite: 90 km/h)**
        
        **📋 Gatilho do Evento:**
        Este evento será gerado quando o veículo permanecer, por um tempo superior à tolerância, com a velocidade acima do valor máximo configurado de condução em pista seca.
        
        **🧮 Regra de Cálculo:**
        - **Gravidade base**: 0.2 por violação
        - **Incremento por velocidade**: +0.2 a cada 5 km/h acima do limite
        - **Incremento adicional**: +0.4 para velocidades acima de 100 km/h
        - **Incremento por duração**: +0.1 a cada 10 segundos de duração
        
        **⚙️ Impacto dos Parâmetros:**
        - **base_weight**: Pontuação inicial por violação
        - **speed_increment**: Intervalo de velocidade para incremento (km/h)
        - **speed_factor**: Multiplicador por incremento de velocidade
        - **speed_threshold_high**: Velocidade para incremento adicional (km/h)
        - **speed_factor_high**: Multiplicador adicional para velocidades altas
        - **duration_increment**: Intervalo de tempo para incremento (segundos)
        - **duration_factor**: Multiplicador por incremento de duração
        """,
        
        "Velocidade_Excessiva_Serra": """
        **⛰️ Serra (Limite: 40 km/h)**
        
        **📋 Gatilho do Evento:**
        Este evento será gerado quando o veículo permanecer, por um tempo superior à tolerância, com a velocidade acima do valor máximo configurado de condução em pista seca.
        
        **🧮 Regra de Cálculo:**
        - **Gravidade base**: 0.1 por violação
        - **Incremento por velocidade**: +0.1 a cada 5 km/h acima do limite
        - **Incremento adicional**: +0.2 para velocidades acima de 65 km/h
        - **Incremento por duração**: +0.05 a cada 10 segundos de duração
        
        **⚙️ Impacto dos Parâmetros:**
        - **base_weight**: Pontuação inicial por violação
        - **speed_increment**: Intervalo de velocidade para incremento (km/h)
        - **speed_factor**: Multiplicador por incremento de velocidade
        - **speed_threshold_high**: Velocidade para incremento adicional (km/h)
        - **speed_factor_high**: Multiplicador adicional para velocidades altas
        - **duration_increment**: Intervalo de tempo para incremento (segundos)
        - **duration_factor**: Multiplicador por incremento de duração
        """,
        
        "Velocidade_Excessiva_Patio": """
        **🏢 Pátio (Limite: 21 km/h)**
        
        **📋 Gatilho do Evento:**
        Este evento será gerado quando o veículo permanecer, por um tempo superior à tolerância, com a velocidade acima do valor máximo configurado de condução em pista seca.
        
        **🧮 Regra de Cálculo:**
        - **Gravidade base**: 0.1 por violação
        - **Incremento por velocidade**: +0.1 a cada 5 km/h acima do limite
        - **Incremento por duração**: +0.05 a cada 10 segundos de duração
        
        **⚙️ Impacto dos Parâmetros:**
        - **base_weight**: Pontuação inicial por violação
        - **speed_increment**: Intervalo de velocidade para incremento (km/h)
        - **speed_factor**: Multiplicador por incremento de velocidade
        - **duration_increment**: Intervalo de tempo para incremento (segundos)
        - **duration_factor**: Multiplicador por incremento de duração
        """,
        
        "Marcha_lenta": """
        **🛑 Marcha Lenta**
        
        **📋 Gatilho do Evento:**
        Este evento registra o tempo em que o veículo permanece parado e com o motor ligado, iniciando a contagem quando o RPM estiver com o valor diferente de zero e com velocidade abaixo de 5km/h. Finalizando a contagem quando o valor do RPM ficar com o valor zero ou quando a velocidade apresentar um valor superior a 5km/h. Em ambos os casos, o tempo sempre tem que ser superior à tolerância configurada.
        
        **🧮 Regra de Cálculo:**
        - **Filtro mínimo**: Eventos com duração inferior a 10 minutos são desconsiderados
        - **Gravidade base**: 0.1 por violação válida
        - **Incremento por duração**: +0.1 a cada 20 minutos de duração
        
        **⚙️ Impacto dos Parâmetros:**
        - **base_weight**: Pontuação inicial por violação
        - **min_duration_filter**: Duração mínima para considerar violação (segundos)
        - **duration_increment**: Intervalo de tempo para incremento (segundos)
        - **duration_factor**: Multiplicador por incremento de duração
        """,
        
        "Freada_Brusca": """
        **🛑 Freada Brusca**
        
        **📋 Gatilho do Evento:**
        Este evento será gerado quando houver uma redução na velocidade acima do valor configurado em um segundo.
        
        **🧮 Regra de Cálculo:**
        - **Gravidade base**: 0.1 por violação
        - **Sem fator de incremento**
        
        **⚙️ Impacto dos Parâmetros:**
        - **base_weight**: Pontuação inicial por violação (único parâmetro)
        """,
        
        "RPM_Excessiva": """
        **⚡ RPM Excessiva**
        
        **📋 Gatilho do Evento:**
        Este evento será gerado quando o veículo permanecer, por um tempo superior à tolerância, com o valor do RPM acima do valor configurado.
        
        **🧮 Regra de Cálculo:**
        - **Gravidade base**: 0.07 por violação
        - **Incremento por duração**: +0.07 a cada 30 segundos de duração
        
        **⚙️ Impacto dos Parâmetros:**
        - **base_weight**: Pontuação inicial por violação
        - **duration_increment**: Intervalo de tempo para incremento (segundos)
        - **duration_factor**: Multiplicador por incremento de duração
        """,
        
        "Faixa_Verde": """
        **🟢 Faixa Verde**
        
        **📋 Gatilho do Evento:**
        Esse evento registra o tempo em que um veículo permanece fora da faixa ideal de rotação do motor, iniciando a contagem quando o RPM estiver abaixo ou acima dos limites configurados. Finalizando a contagem quando o RPM retornar aos valores da faixa verde ou zerar o valor, e, em ambos os casos, o tempo sempre tem que ser no caso de valores de RPM acima dos limites configurados, também e levado em consideracão o acionamento do pedal do acelerador, caso esse não esteja acionado, o evento não é registrado, pois neste cenário o veículo está utilizando o freio motor.
        
        **🧮 Regra de Cálculo:**
        - **Gravidade base**: 0.07 por violação
        - **Incremento por duração**: +0.07 a cada 3 minutos de duração
        
        **⚙️ Impacto dos Parâmetros:**
        - **base_weight**: Pontuação inicial por violação
        - **duration_increment**: Intervalo de tempo para incremento (segundos)
        - **duration_factor**: Multiplicador por incremento de duração
        """,
        
        "Freio_Motor": """
        **🔧 Freio Motor**
        
        **📋 Gatilho do Evento:**
        Este evento registra o tempo em que o veículo permanece em uso do freio motor, iniciando a contagem quando o RPM estiver com um valor entre o limite superior configurado no evento de fora da faixa verde e o limite configurado no evento de excesso de RPM e sem acionamento do pedal do acelerador. Finalizando a contagem quando o valor do RPM ficar fora do intervalo mencionado acima ou quando o pedal do acelerador for acionado. Em ambos os casos, o tempo sempre tem que ser superior à tolerância configurada.
        
        **🧮 Regra de Cálculo:**
        - **Gravidade base**: 0.07 por violação
        - **Incremento por duração**: +0.07 a cada 2 minutos de duração
        
        **⚙️ Impacto dos Parâmetros:**
        - **base_weight**: Pontuação inicial por violação
        - **duration_increment**: Intervalo de tempo para incremento (segundos)
        - **duration_factor**: Multiplicador por incremento de duração
        """
    }
    
    return dcc.Markdown(docs.get(viol_type_key, "Sem documentação disponível."), 
                       dangerously_allow_html=True, 
                       style={'backgroundColor': colors['background'], 'padding': '15px', 'borderRadius': '5px', 'border': f"1px solid {colors['border']}"})

def create_parameter_editor():
    """Cria a seção de edição dos parâmetros de gravidade."""
    sections = []
    
    # Agrupa parâmetros de velocidade
    speed_params = {k: v for k, v in DEFAULT_GRAVITY_CONFIG.items() if "Velocidade" in k}
    other_params = {k: v for k, v in DEFAULT_GRAVITY_CONFIG.items() if "Velocidade" not in k}

    # Seção de Velocidade
    speed_inputs = []
    for viol_type, params in speed_params.items():
        doc_html = get_documentation_for_violation(viol_type)
        inputs_viol = [
            html.Div([
                html.Div([
                    html.Label(f"{key}:", style={'marginRight': '10px', 'fontWeight': 'bold', 'color': colors['accent_yellow']}),
                    html.Span(get_parameter_description(key), style={'fontSize': '0.8em', 'color': colors['text_light'], 'fontStyle': 'italic'})
                ], style={'display': 'flex', 'flexDirection': 'column', 'marginBottom': '5px'}),
                dcc.Input(id={'type': 'gravity-input', 'index': f'{viol_type}-{key}'}, type='number', value=value, 
                         style={'width': '100px', 'backgroundColor': '#374151', 'border': 'none', 'padding': '5px', 'borderRadius': '3px'})
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '10px', 'padding': '8px', 'backgroundColor': colors['background'], 'borderRadius': '5px'})
            for key, value in params.items()
        ]
        speed_inputs.append(html.Div([doc_html, html.Div(inputs_viol)], style={'flex': '1 1 30%', 'minWidth': '350px', 'padding': '15px'}))

    sections.append(
        html.Div([
            html.H4("Velocidade Excessiva (Categorias)", style={'color': colors['accent_yellow'], 'borderBottom': f"1px solid {colors['border']}", 'paddingBottom': '5px', 'marginBottom': '15px'}),
            html.Div(speed_inputs, style={'display': 'flex', 'flexWrap': 'wrap', 'gap': '20px'})
        ], style={'backgroundColor': colors['card_bg'], 'padding': '20px', 'borderRadius': '8px', 'marginBottom': '15px'})
    )

    # Outras violações
    for viol_type, params in other_params.items():
        doc_html = get_documentation_for_violation(viol_type)
        inputs = [
            html.Div([
                html.Div([
                    html.Label(f"{key}:", style={'marginRight': '10px', 'fontWeight': 'bold', 'color': colors['accent_yellow']}),
                    html.Span(get_parameter_description(key), style={'fontSize': '0.8em', 'color': colors['text_light'], 'fontStyle': 'italic'})
                ], style={'display': 'flex', 'flexDirection': 'column', 'marginBottom': '5px'}),
                dcc.Input(id={'type': 'gravity-input', 'index': f'{viol_type}-{key}'}, type='number', value=value, 
                         style={'width': '100px', 'backgroundColor': '#374151', 'border': 'none', 'padding': '5px', 'borderRadius': '3px'})
            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '10px', 'padding': '8px', 'backgroundColor': colors['background'], 'borderRadius': '5px'})
            for key, value in params.items()
        ]
        sections.append(
            html.Div([
                html.H4(viol_type.replace('_', ' '), style={'color': colors['accent_yellow'], 'borderBottom': f"1px solid {colors['border']}", 'paddingBottom': '5px'}),
                html.Div([
                    doc_html,
                    html.Div(inputs, style={'flex': 1, 'minWidth': '300px', 'paddingTop': '20px'})
                ], style={'display': 'flex', 'flexDirection': 'column', 'marginTop': '15px', 'gap': '20px'})
            ], style={'backgroundColor': colors['card_bg'], 'padding': '20px', 'borderRadius': '8px', 'marginBottom': '15px'})
        )
    return html.Div(sections)

def get_parameter_description(param_name):
    """Retorna a descrição do impacto de cada parâmetro."""
    descriptions = {
        'base_weight': 'Pontuação inicial por violação',
        'speed_increment': 'Intervalo de velocidade para incremento (km/h)',
        'speed_factor': 'Multiplicador por incremento de velocidade',
        'speed_threshold_high': 'Velocidade para incremento adicional (km/h)',
        'speed_factor_high': 'Multiplicador adicional para velocidades altas',
        'duration_increment': 'Intervalo de tempo para incremento (segundos)',
        'duration_factor': 'Multiplicador por incremento de duração',
        'min_duration_filter': 'Duração mínima para considerar violação (segundos)'
    }
    return descriptions.get(param_name, 'Parâmetro de configuração')

app.layout = html.Div(style={'backgroundColor': colors['background'], 'color': colors['text'], 'fontFamily': 'sans-serif'}, children=[
    html.Div(style={'maxWidth': '1280px', 'margin': '0 auto', 'padding': '20px'}, children=[
        dcc.Store(id='store-violations-df'), dcc.Store(id='store-ranking-df'),
        html.H1('Dashboard de Violações', style={'textAlign': 'center', 'marginBottom': '10px', 'fontSize': '3em'}),
        html.P('Análise de Telemetria e Desempenho dos Motoristas', style={'textAlign': 'center', 'marginBottom': '20px', 'color': colors['text_light']}),
        
        html.Div(id='initial-setup-container', children=[
            # Botão Voltar para Análise (aparece apenas se já houver dados carregados)
            html.Div(id='back-to-dashboard-btn-container'),
            # Seção de Upload do CSV (sempre visível)
            html.Div(className='upload-section', style={'backgroundColor': colors['card_bg'], 'padding': '30px', 'borderRadius': '12px', 'marginBottom': '30px', 'border': f"1px solid {colors['border']}", 'boxShadow': '0 4px 6px rgba(0, 0, 0, 0.1)'}, children=[
                html.Div(style={'textAlign': 'center', 'marginBottom': '25px'}, children=[
                    html.H2('📊 Upload do Arquivo CSV', style={'color': colors['text'], 'marginBottom': '10px', 'fontSize': '2.2em', 'fontWeight': '600'}),
                    html.P('Faça upload do arquivo CSV com dados de telemetria para iniciar a análise de risco da frota', 
                           style={'color': colors['text_light'], 'fontSize': '1.1em', 'maxWidth': '600px', 'margin': '0 auto'})
                ]),
                
                # Área de upload melhorada
                html.Div(style={'position': 'relative', 'marginBottom': '20px'}, children=[
                    dcc.Upload(
                        id='upload-data', 
                        children=html.Div([
                            html.Div(style={'fontSize': '3em', 'marginBottom': '15px', 'color': colors['accent_blue']}, children='📁'),
                            html.Div([
                                html.Span('Arraste e solte seu arquivo CSV aqui', style={'fontSize': '18px', 'fontWeight': '600', 'color': colors['text']}),
                                html.Br(),
                                html.Span('ou clique para selecionar', style={'fontSize': '14px', 'color': colors['text_light']})
                            ]),
                            html.Div(style={'marginTop': '15px', 'padding': '8px 16px', 'backgroundColor': colors['accent_blue'], 'color': 'white', 'borderRadius': '6px', 'fontSize': '12px', 'fontWeight': '500'}, 
                                    children='Formatos aceitos: .csv')
                        ]), 
                        style=upload_style
                    ),
                    
                    # Informações sobre o arquivo
                    html.Div(style={'marginTop': '15px', 'padding': '15px', 'backgroundColor': colors['background'], 'borderRadius': '8px', 'border': f"1px solid {colors['border']}"}, children=[
                        html.H4('📋 Informações sobre o arquivo:', style={'color': colors['accent_yellow'], 'marginBottom': '10px', 'fontSize': '16px'}),
                        html.Ul([
                            html.Li('O arquivo deve conter colunas: motorista, nome_do_veículo, data_evento, violacao, duracao, latitude_inicial, longitude_inicial, latitude_final, longitude_final', style={'color': colors['text_light'], 'fontSize': '14px', 'marginBottom': '5px'}),
                            html.Li('Formato de data: DD/MM/YYYY HH:MM:SS', style={'color': colors['text_light'], 'fontSize': '14px', 'marginBottom': '5px'}),
                            html.Li('Coordenadas em formato decimal (ex: -27.123456, -48.123456)', style={'color': colors['text_light'], 'fontSize': '14px', 'marginBottom': '5px'}),
                            html.Li('Duração em formato HH:MM:SS', style={'color': colors['text_light'], 'fontSize': '14px'})
                        ], style={'margin': '0', 'paddingLeft': '20px'})
                    ])
                ]),
                
                html.Div(id='upload-error-output'),
                
                # Loading para processamento do CSV
                dcc.Loading(
                    id="loading-csv",
                    type="default",
                    className='dash-loading',
                    children=html.Div(id="csv-processing-status", style={'textAlign': 'center', 'marginTop': '15px'})
                )
            ]),
            
            # Mensagem informativa para dispositivos móveis
            html.Div([
                html.H4('📱 Dispositivo Móvel Detectado', style={'color': colors['accent_yellow'], 'marginBottom': '10px'}),
                html.P('Os parâmetros de configuração foram ocultados para melhor experiência em dispositivos móveis. Use os valores padrão ou acesse em um computador para ajustes personalizados.', 
                       style={'color': colors['text_light'], 'fontSize': '0.9em'})
            ], className='mobile-info', style={'display': 'none'}),
            
            # Seção de Parâmetros (oculta em dispositivos móveis)
            html.Div(id='parameters-section', children=[
            html.H2('Ajuste Fino dos Parâmetros de Gravidade', style={'textAlign': 'center', 'marginBottom': '20px'}),
            html.Div([
                html.Button('Resetar para o Padrão', id='reset-gravity-button', n_clicks=0, style={'marginBottom': '20px', 'backgroundColor': colors['accent_yellow'], 'color': 'black', 'border': 'none', 'padding': '10px 20px', 'borderRadius': '5px', 'cursor': 'pointer', 'fontWeight': 'bold'}),
            ], style={'textAlign': 'center'}),
            create_parameter_editor(),
            ], style={'backgroundColor': colors['card_bg'], 'padding': '20px', 'borderRadius': '8px'}),
        ]),

        html.Div(id='main-dashboard-content', style={'display': 'none'})
    ])
])

# --- CALLBACKS ---

# Callback para resetar os parâmetros
@app.callback(
    [Output({'type': 'gravity-input', 'index': f'{v_key}-{p_key}'}, 'value') for v_key, p_val in DEFAULT_GRAVITY_CONFIG.items() for p_key in p_val.keys()],
    [Input('reset-gravity-button', 'n_clicks')]
)
def reset_gravity_parameters(n_clicks):
    if n_clicks == 0:
        raise dash.exceptions.PreventUpdate
    return [p_val[p_key] for v_key, p_val in DEFAULT_GRAVITY_CONFIG.items() for p_key in p_val.keys()]

# Callback para processar o upload e construir a UI principal
@app.callback(
    [Output('main-dashboard-content', 'children'), Output('main-dashboard-content', 'style'), Output('initial-setup-container', 'style'), Output('store-violations-df', 'data'), Output('store-ranking-df', 'data'), Output('upload-error-output', 'children'), Output('csv-processing-status', 'children')],
    [Input('upload-data', 'contents')],
    [State('upload-data', 'filename'), State({'type': 'gravity-input', 'index': ALL}, 'id'), State({'type': 'gravity-input', 'index': ALL}, 'value')]
)
def update_on_upload(contents, filename, gravity_ids, gravity_values):
    if contents is None: 
        raise dash.exceptions.PreventUpdate
    
    # Status inicial de processamento
    processing_status = html.Div([
        html.H4('🔄 Processando arquivo CSV...', style={'color': colors['accent_blue']}),
        html.P('Aguarde enquanto analisamos os dados...', style={'color': colors['text_light']})
    ])
    
    gravity_config = {}
    for i, comp_id in enumerate(gravity_ids):
        viol_type, param_name = comp_id['index'].split('-')
        if viol_type not in gravity_config:
            gravity_config[viol_type] = {}
        gravity_config[viol_type][param_name] = gravity_values[i]
        
    violations_df, ranking_df, error_div = process_uploaded_data(contents, filename, gravity_config)
    
    if error_div is not None: 
        return None, {'display': 'none'}, {'display': 'block'}, None, None, error_div, ""
    
    dashboard_layout = build_dashboard_layout(ranking_df)
    
    # Status de conclusão
    completion_status = html.Div([
        html.H4('✅ Processamento concluído!', style={'color': '#10B981'}),
        html.P(f'Arquivo processado com sucesso: {len(violations_df)} violações encontradas', style={'color': colors['text_light']})
    ])
    
    return dashboard_layout, {'display': 'block'}, {'display': 'none'}, violations_df.to_json(date_format='iso',orient='split'), ranking_df.to_json(orient='split'), None, completion_status

# Callback para o botão "Analisar Outro Arquivo"
@app.callback(
    [Output('initial-setup-container', 'style', allow_duplicate=True), Output('main-dashboard-content', 'style', allow_duplicate=True)],
    [Input('back-to-upload-button', 'n_clicks')],
    prevent_initial_call=True
)
def go_back_to_setup(n_clicks):
    if n_clicks > 0:
        return {'display': 'block'}, {'display': 'none'}
    return dash.no_update, dash.no_update

def build_dashboard_layout(ranking_df):
    """Constrói a UI do dashboard após o upload."""
    
    return html.Div([
        html.Div(style={'display': 'flex', 'justifyContent': 'center', 'marginBottom': '20px'}, children=[
            html.Button([
                html.Span('🔄', style={'fontSize': '16px', 'marginRight': '8px'}),
                'Analisar Outro Arquivo'
            ], id='back-to-upload-button', n_clicks=0, className='nav-button', style=back_button_style)
        ]),
        dcc.Tabs(id="tabs-main", value='tab-general', children=[
            dcc.Tab(label='Visão Geral da Frota', value='tab-general', style=tab_style, selected_style=tab_selected_style, className='dash-tab', children=[
                html.Div(className='dash-container', style={'padding': '20px 0'}, children=[
                    dcc.Loading(
                        id="loading-general-kpis",
                        type="default",
                        className='dash-loading',
                        children=html.Div(id='kpi-container-general', className='kpi-row')
                    ),
                    dcc.Loading(
                        id="loading-general-charts",
                        type="default",
                        className='dash-loading',
                        children=html.Div(className='dashboard-carousel', children=[
                            html.H3('Dashboards de Análise'),
                            dcc.Tabs(id="dashboard-tabs", value='timeline-tab', children=[
                                # Dashboard 1: Timeline de Risco
                                dcc.Tab(
                                    label='📈 Evolução Temporal',
                                    value='timeline-tab',
                                    style=tab_style,
                                    selected_style=tab_selected_style,
                                    className='dash-tab',
                                    children=html.Div(className='dashboard-content', children=[
                                        html.H4('Evolução do Risco da Frota por Dia'),
                                        html.P('Acompanhe a evolução do risco da frota ao longo do tempo, identificando tendências e padrões sazonais.'),
                                        dcc.Graph(id='daily-risk-timeline-general', className='dash-graph', style={'height': '400px'})
                                    ])
                                ),
                                # Dashboard 2: Violações por Tipo
                                dcc.Tab(
                                    label='📊 Tipos de Violação',
                                    value='violations-tab',
                                    style=tab_style,
                                    selected_style=tab_selected_style,
                                    className='dash-tab',
                                    children=html.Div(className='dashboard-content', children=[
                                        html.H4('Pontuação de Risco por Tipo de Violação'),
                                        html.P('Identifique quais tipos de violação representam maior risco para a frota e onde focar os esforços de melhoria.'),
                                        dcc.Graph(id='violations-chart-general', className='dash-graph', style={'height': '400px'})
                                    ])
                                ),
                                # Dashboard 3: Concentração de Risco
                                dcc.Tab(
                                    label='🥧 Concentração de Risco',
                                    value='concentration-tab',
                                    style=tab_style,
                                    selected_style=tab_selected_style,
                                    className='dash-tab',
                                    children=html.Div(className='dashboard-content', children=[
                                        html.H4('Concentração de Risco - Top 5 vs Outros'),
                                        html.P('Visualize como o risco está distribuído entre os motoristas, identificando se há concentração em poucos indivíduos.'),
                                        dcc.Graph(id='risk-concentration-chart', className='dash-graph', style={'height': '400px'})
                                    ])
                                ),
                                # Dashboard 4: Quantidade de Violações por Tipo
                                dcc.Tab(
                                    label='📊 Quantidade por Tipo',
                                    value='quantity-tab',
                                    style=tab_style,
                                    selected_style=tab_selected_style,
                                    className='dash-tab',
                                    children=html.Div(className='dashboard-content', children=[
                                        html.H4('Quantidade de Violações por Tipo'),
                                        html.P('Visualize a distribuição da quantidade de cada tipo de violação na frota, identificando os tipos mais frequentes.'),
                                        dcc.Graph(id='violations-quantity-chart', className='dash-graph', style={'height': '400px'})
                                    ])
                                )
                            ])
                        ])
                    ),
                    html.Div(className='card-container', style={'backgroundColor': colors['card_bg'], 'padding': '20px', 'borderRadius': '8px', 'marginBottom': '20px'}, children=[
                        html.H2('Ranking Geral de Risco', style={'marginBottom': '10px'}),
                        dcc.Loading(
                            id="loading-general-table",
                            type="default",
                            className='dash-loading',
                            children=html.Div(
                                className='table-container',
                                children=dash_table.DataTable(
                                    id='ranking-table', 
                                    style_cell={'backgroundColor': colors['card_bg'], 'color': colors['text'], 'border': f"1px solid {colors['border']}", 'padding': '10px', 'textAlign': 'left'}, 
                                    style_header={'backgroundColor': colors['border'], 'fontWeight': 'bold'}, 
                                    style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#374151'}], 
                                    page_size=10,
                                    filter_action='native',
                                    sort_action='native',
                                    sort_mode='multi'
                                )
                            )
                        )
                    ]),
                    html.Div(className='card-container', style={'backgroundColor': colors['card_bg'], 'padding': '20px', 'borderRadius': '8px', 'marginTop': '20px'}, children=[
                        html.H2('Todas as Violações', style={'marginBottom': '10px'}),
                        dcc.Loading(
                            id="loading-violations-table",
                            type="default",
                            className='dash-loading',
                            children=html.Div(
                                className='table-container',
                                style={'overflowX': 'auto', 'maxWidth': '100%'},
                                children=dash_table.DataTable(
                                    id='violations-table', 
                                    style_cell={'backgroundColor': colors['card_bg'], 'color': colors['text'], 'border': f"1px solid {colors['border']}", 'padding': '10px', 'textAlign': 'left', 'minWidth': '120px', 'maxWidth': '200px', 'overflow': 'hidden', 'textOverflow': 'ellipsis'}, 
                                    style_header={'backgroundColor': colors['border'], 'fontWeight': 'bold'}, 
                                    style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#374151'}], 
                                    page_size=20,
                                    filter_action='native',
                                    sort_action='native',
                                    sort_mode='multi',
                                    columns=[
                                        {'name': 'Linha CSV', 'id': 'linha_csv'},
                                        {'name': 'Data/Hora', 'id': 'data_evento'},
                                        {'name': 'Motorista', 'id': 'motorista'},
                                        {'name': 'Veículo', 'id': 'nome_do_veículo'},
                                        {'name': 'Violação', 'id': 'violacao'},
                                        {'name': 'Pontuação', 'id': 'score_final'},
                                        {'name': 'Duração', 'id': 'duracao'},
                                        {'name': 'Distância', 'id': 'distância'},
                                        {'name': 'Velocidade máxima', 'id': 'velocidade_máxima'},
                                        {'name': 'RPM máximo', 'id': 'rpm_máximo'},
                                        {'name': 'Mapa', 'id': 'mapa_link', 'type': 'text', 'presentation': 'markdown'}
                                    ]
                                )
                            )
                        )
                    ]),
                ])
            ]),
            dcc.Tab(label='Análise Individual por Motorista', value='tab-individual', style=tab_style, selected_style=tab_selected_style, className='dash-tab', children=[
                html.Div(
                    style={'backgroundColor': colors['background'], 'minHeight': '100vh', 'padding': '0'},
                    children=[
                        html.Div(className='card-container individual-dashboard', style={'backgroundColor': colors['card_bg'], 'padding': '20px', 'borderRadius': '8px', 'marginTop': '20px'}, children=[
                            html.H2('Relatório de Melhoria Individual', style={'marginBottom': '20px'}),
                            dcc.Dropdown(id='driver-dropdown', options=[{'label': driver, 'value': driver} for driver in sorted(ranking_df['Motorista'])], placeholder='Selecione um motorista...', style={'color': '#000'}, className='dash-dropdown'),
                            html.Div(id='individual-dashboard-output', style={'marginTop': '20px'})
                        ])
                    ]
                )
            ]),
        ])
    ])

# Callback para a Visão Geral da Frota
@app.callback(
    [Output('kpi-container-general', 'children'), Output('ranking-table', 'columns'), Output('ranking-table', 'data'), Output('violations-chart-general', 'figure'), Output('risk-concentration-chart', 'figure'), Output('daily-risk-timeline-general', 'figure'), Output('violations-quantity-chart', 'figure'), Output('violations-table', 'columns'), Output('violations-table', 'data')],
    [Input('store-violations-df', 'data'), Input('store-ranking-df', 'data')]
)
def update_general_dashboard(violations_json, ranking_json):
    if violations_json is None or ranking_json is None: 
        raise dash.exceptions.PreventUpdate
    
    # Simular um pequeno delay para mostrar o loading
    time.sleep(0.1)
    
    violations_df = pd.read_json(violations_json, orient='split')
    violations_df['data_evento'] = pd.to_datetime(violations_df['data_evento'])
    ranking_df = pd.read_json(ranking_json, orient='split')
    
    kpi_drivers = ranking_df['Motorista'].nunique()
    kpi_violations = len(violations_df)
    kpi_avg_score = ranking_df['Pontuação Total'].mean() if not ranking_df.empty else 0
    kpi_main_violation = violations_df['violacao'].mode()[0] if not violations_df.empty else "N/A"
    
    # Novo KPI: Pontuação Total da Frota
    kpi_total_score = violations_df['score_final'].sum() if not violations_df.empty else 0

    # Calcula tempo total de Marcha lenta
    marcha_lenta_violations = violations_df[violations_df['violacao'] == 'Marcha lenta']
    total_marcha_lenta_seconds = marcha_lenta_violations['duracao_seconds'].sum()
    kpi_marcha_lenta_time = convert_seconds_to_hhmm(total_marcha_lenta_seconds)
    
    # Calcula tempo total de Velocidade Excessiva
    velocidade_excessiva_violations = violations_df[violations_df['violacao'] == 'Velocidade excessiva']
    total_velocidade_excessiva_seconds = velocidade_excessiva_violations['duracao_seconds'].sum()
    kpi_velocidade_excessiva_time = convert_seconds_to_hhmm(total_velocidade_excessiva_seconds)
    
    # Calcula tempo total de Faixa verde
    faixa_verde_violations = violations_df[violations_df['violacao'] == 'Faixa verde']
    total_faixa_verde_seconds = faixa_verde_violations['duracao_seconds'].sum()
    kpi_faixa_verde_time = convert_seconds_to_hhmm(total_faixa_verde_seconds)
    
    # Calcula pontuação por categoria para a frota
    economica_score = violations_df[violations_df['violacao'].isin(VIOLATION_CATEGORIES['Econômica'])]['score_final'].sum()
    seguranca_score = violations_df[violations_df['violacao'].isin(VIOLATION_CATEGORIES['Segurança'])]['score_final'].sum()
    total_score = violations_df['score_final'].sum()
    percentual_economica = (economica_score / total_score * 100) if total_score > 0 else 0
    percentual_seguranca = (seguranca_score / total_score * 100) if total_score > 0 else 0
    
    kpis = html.Div([
        html.Div(className='kpi-row', style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(200px, 1fr))', 'gap': '20px', 'marginBottom': '20px'}, children=[
            html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Pontuação Total', style={'color': colors['text_light']}), html.P(f"{kpi_total_score:,.2f}".replace('.', ','), style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': colors['accent_blue']})]),
            html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Motoristas', style={'color': colors['text_light']}), html.P(kpi_drivers, style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': colors['accent_yellow']})]),
            html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Total de Violações', style={'color': colors['text_light']}), html.P(kpi_violations, style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': colors['accent_red']})]),
            html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Pontuação Média', style={'color': colors['text_light']}), html.P(f"{kpi_avg_score:,.2f}".replace('.', ','), style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': colors['accent_purple']})]),
            html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Violação Principal', style={'color': colors['text_light']}), html.P(kpi_main_violation, style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': colors['accent_orange']})]),
            html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Tempo Marcha Lenta', style={'color': colors['text_light']}), html.P(kpi_marcha_lenta_time, style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': colors['accent_orange']})]),
            html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Tempo Velocidade Excessiva', style={'color': colors['text_light']}), html.P(kpi_velocidade_excessiva_time, style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': colors['accent_purple']})]),
            html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Tempo Faixa Verde', style={'color': colors['text_light']}), html.P(kpi_faixa_verde_time, style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': colors['accent_green']})]),
            html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Pontuação Econômica', style={'color': colors['text_light']}), html.P(f"{economica_score:,.2f}".replace('.', ','), style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': CATEGORY_COLORS['Econômica']})]),
            html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Pontuação Segurança', style={'color': colors['text_light']}), html.P(f"{seguranca_score:,.2f}".replace('.', ','), style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': CATEGORY_COLORS['Segurança']})]),
        ]),
        # Barra de distribuição por categoria
        html.Div(className='card-container', style={'backgroundColor': colors['card_bg'], 'padding': '15px', 'borderRadius': '8px', 'marginBottom': '20px', 'border': f"1px solid {colors['border']}"}, children=[
            html.H4('Distribuição por Categoria da Frota', style={'marginTop': 0, 'color': colors['text']}),
            html.P('A frota apresenta uma distribuição de violações entre as categorias Econômica e Segurança:'),
            html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '10px'}, children=[
                html.Div(f"Econômica: {percentual_economica:.1f}%", style={'flex': 1, 'height': '30px', 'borderRadius': '4px', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center', 'color': 'white', 'fontWeight': 'bold', 'backgroundColor': CATEGORY_COLORS['Econômica']}),
                html.Div(f"Segurança: {percentual_seguranca:.1f}%", style={'flex': 1, 'height': '30px', 'borderRadius': '4px', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center', 'color': 'white', 'fontWeight': 'bold', 'backgroundColor': CATEGORY_COLORS['Segurança']}),
            ]),
            html.P([
                html.Strong('Econômica:'), ' Freio motor, RPM excessiva, Marcha lenta, Faixa verde', html.Br(),
                html.Strong('Segurança:'), ' Velocidade excessiva, Freada brusca'
            ], style={'marginTop': '10px', 'fontSize': '0.9em', 'color': colors['text_light']})
        ])
    ])

    if not ranking_df.empty:
        display_columns = ['Motorista', 'Pontuação Total'] + VIOLATION_TYPES
        ranking_display_df = ranking_df.sort_values(by='Pontuação Total', ascending=False).reset_index(drop=True)
        ranking_display_df['Rank'] = ranking_display_df.index + 1
        ranking_display_df = ranking_display_df[['Rank'] + [col for col in ranking_display_df.columns if col != 'Rank']]
        
        # Formatar pontuações com vírgula
        for col in ranking_display_df.columns:
            if 'Pontuação' in col or col in VIOLATION_TYPES:
                ranking_display_df[col] = ranking_display_df[col].apply(lambda x: f"{x:,.2f}".replace('.', ',') if pd.notna(x) else "0,00")
        
        table_cols = [{'name': i.replace('_', ' ').title(), 'id': i} for i in ranking_display_df.columns if i in display_columns]
        table_data = ranking_display_df.to_dict('records')
    else:
        table_cols, table_data = [], []

    daily_scores = violations_df.groupby(violations_df['data_evento'].dt.date)['score_final'].sum()
    timeline_fig = go.Figure(data=[go.Scatter(x=daily_scores.index, y=daily_scores.values, mode='lines+markers', line=dict(color=colors['accent_blue']))])
    timeline_fig.update_layout(title_text='Evolução do Risco da Frota por Dia', title_x=0.5, plot_bgcolor=colors['card_bg'], paper_bgcolor=colors['card_bg'], font_color=colors['text'], yaxis_gridcolor=colors['border'])

    violation_sums = violations_df.groupby('violacao')['score_final'].sum().sort_values(ascending=False)
    bar_fig = go.Figure(data=[go.Bar(x=violation_sums.index, y=violation_sums.values, marker_color=colors['accent_red'])])
    bar_fig.update_layout(title_text='Pontuação de Risco por Tipo de Violação (Frota)', title_x=0.5, plot_bgcolor=colors['card_bg'], paper_bgcolor=colors['card_bg'], font_color=colors['text'], yaxis_gridcolor=colors['border'])

    top_5_score = ranking_df.nlargest(5, 'Pontuação Total')['Pontuação Total'].sum()
    others_score = ranking_df.iloc[5:]['Pontuação Total'].sum()
    pie_fig = go.Figure(data=[go.Pie(labels=['Top 5 Motoristas', 'Outros'], values=[top_5_score, others_score], hole=.3, marker_colors=[colors['accent_red'], colors['accent_blue']])])
    pie_fig.update_layout(title_text='Concentração de Risco', title_x=0.5, plot_bgcolor=colors['card_bg'], paper_bgcolor=colors['card_bg'], font_color=colors['text'], legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5))

    # Preparar tabela de violações
    violations_display_df = violations_df.copy()
    
    # Preparar colunas para a tabela de violações
    violations_columns = [
        {'name': 'Linha CSV', 'id': 'linha_csv'},
        {'name': 'Data/Hora', 'id': 'data_evento'},
        {'name': 'Motorista', 'id': 'motorista'},
        {'name': 'Veículo', 'id': 'nome_do_veículo'},
        {'name': 'Violação', 'id': 'violacao'},
        {'name': 'Pontuação', 'id': 'score_final'},
        {'name': 'Duração', 'id': 'duracao'},
        {'name': 'Distância', 'id': 'distância'},
        {'name': 'Velocidade máxima', 'id': 'velocidade_máxima'},
        {'name': 'RPM máximo', 'id': 'rpm_máximo'},
        {'name': 'Mapa', 'id': 'mapa_link', 'type': 'text', 'presentation': 'markdown'}
    ]
    
    # Preparar dados para a tabela de violações
    violations_data = violations_display_df[['linha_csv', 'data_evento', 'motorista', 'nome_do_veículo', 'violacao', 'score_final', 'duracao', 'distância', 'velocidade_máxima', 'rpm_máximo', 'latitude_inicial', 'longitude_inicial', 'latitude_final', 'longitude_final']].copy()
    violations_data['data_evento'] = violations_data['data_evento'].dt.strftime('%d/%m/%Y %H:%M:%S')
    # Formata a pontuação para string com vírgula como separador decimal
    violations_data['score_final'] = violations_data['score_final'].round(2).apply(lambda x: f'{x:.2f}'.replace('.', ','))
    violations_data['mapa_link'] = violations_data.apply(
        lambda row: f"[Ver Mapa]({generate_maps_route_link(row['latitude_inicial'], row['longitude_inicial'], row['latitude_final'], row['longitude_final'])})" if pd.notna(row['latitude_inicial']) and pd.notna(row['longitude_inicial']) else "N/A",
        axis=1
    )
    violations_data = violations_data[['linha_csv', 'data_evento', 'motorista', 'nome_do_veículo', 'violacao', 'score_final', 'duracao', 'distância', 'velocidade_máxima', 'rpm_máximo', 'mapa_link']]
    violations_data = violations_data.to_dict('records')

    # Criar gráfico de quantidade de violações por tipo (horizontal)
    violation_counts = violations_df['violacao'].value_counts().sort_values(ascending=True)
    quantity_fig = go.Figure(data=[go.Bar(
        y=violation_counts.index,
        x=violation_counts.values,
        orientation='h',
        marker_color=colors['accent_blue'],
        text=violation_counts.values,
        textposition='auto'
    )])
    quantity_fig.update_layout(
        title_text='Quantidade de Violações por Tipo',
        title_x=0.5,
        plot_bgcolor=colors['card_bg'],
        paper_bgcolor=colors['card_bg'],
        font_color=colors['text'],
        xaxis_gridcolor=colors['border'],
        yaxis=dict(
            title=dict(text='Tipo de Violação', font=dict(color=colors['text'])),
            tickfont=dict(color=colors['text'])
        ),
        xaxis=dict(
            title=dict(text='Quantidade', font=dict(color=colors['text'])),
            tickfont=dict(color=colors['text'])
        ),
        margin=dict(l=20, r=20, t=60, b=20)
    )

    return kpis, table_cols, table_data, bar_fig, pie_fig, timeline_fig, quantity_fig, violations_columns, violations_data

# Callback para a aba de Ranking por Veículo
@app.callback(
    [Output('kpi-container-veiculo', 'children'), Output('ranking-table-veiculo', 'columns'), Output('ranking-table-veiculo', 'data')],
    [Input('store-ranking-veiculo-df', 'data')]
)
def update_veiculo_dashboard(ranking_veiculo_json):
    if ranking_veiculo_json is None: 
        raise dash.exceptions.PreventUpdate
    
    # Simular um pequeno delay para mostrar o loading
    time.sleep(0.1)
    
    ranking_veiculo_df = pd.read_json(ranking_veiculo_json, orient='split')
    
    kpi_veiculos = ranking_veiculo_df['Veículo'].nunique()
    kpi_avg_score_veiculo = ranking_veiculo_df['Pontuação Total'].mean() if not ranking_veiculo_df.empty else 0
    kpi_top_veiculo = ranking_veiculo_df.loc[ranking_veiculo_df['Pontuação Total'].idxmax(), 'Veículo'] if not ranking_veiculo_df.empty else "N/A"
    kpi_top_score = ranking_veiculo_df['Pontuação Total'].max() if not ranking_veiculo_df.empty else 0
    
    kpis = html.Div(className='kpi-row', style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(200px, 1fr))', 'gap': '20px', 'marginBottom': '20px'}, children=[
        html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Veículos Ativos', style={'color': colors['text_light']}), html.P(f"{kpi_veiculos}", style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': colors['accent_blue']})]),
        html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Pontuação Média', style={'color': colors['text_light']}), html.P(f"{kpi_avg_score_veiculo:,.0f}".replace('.', ','), style={'fontSize': '2.2em', 'fontWeight': 'bold'})]),
        html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Veículo de Maior Risco', style={'color': colors['text_light']}), html.P(kpi_top_veiculo, style={'fontSize': '1.8em', 'fontWeight': 'bold', 'color': colors['accent_red']})]),
        html.Div(className='kpi-card', style=kpi_card_style, children=[html.H3('Pontuação Máxima', style={'color': colors['text_light']}), html.P(f"{kpi_top_score:,.0f}".replace('.', ','), style={'fontSize': '2.2em', 'fontWeight': 'bold', 'color': colors['accent_yellow']})]),
    ])

    if not ranking_veiculo_df.empty:
        display_columns = ['Veículo', 'Pontuação Total'] + VIOLATION_TYPES
        ranking_display_df = ranking_veiculo_df.sort_values(by='Pontuação Total', ascending=False).reset_index(drop=True)
        ranking_display_df['Rank'] = ranking_display_df.index + 1
        ranking_display_df = ranking_display_df[['Rank'] + [col for col in ranking_display_df.columns if col != 'Rank']]
        
        # Formatar pontuações com vírgula
        for col in ranking_display_df.columns:
            if 'Pontuação' in col or col in VIOLATION_TYPES:
                ranking_display_df[col] = ranking_display_df[col].apply(lambda x: f"{x:,.2f}".replace('.', ',') if pd.notna(x) else "0,00")
        
        table_cols = [{'name': i.replace('_', ' ').title(), 'id': i} for i in ranking_display_df.columns if i in display_columns]
        table_data = ranking_display_df.to_dict('records')
    else:
        table_cols, table_data = [], []

    return kpis, table_cols, table_data

# Callback para criar o layout do dashboard individual
@app.callback(Output('individual-dashboard-output', 'children'), [Input('driver-dropdown', 'value')], [State('store-violations-df', 'data')])
def create_individual_layout(selected_driver, violations_json):
    if not selected_driver or violations_json is None:
        return html.P("Selecione um motorista para ver sua análise detalhada.", style={'color': colors['text_light'], 'textAlign': 'center'})

    violations_df = pd.read_json(violations_json, orient='split')
    violations_df['data_evento'] = pd.to_datetime(violations_df['data_evento'])
    driver_violations_df = violations_df[violations_df['motorista'] == selected_driver]
    
    if driver_violations_df.empty or driver_violations_df['data_evento'].isnull().all():
        return html.P("Não há dados de violação válidos para este motorista.")
    
    available_violations = driver_violations_df['violacao'].unique()

    return html.Div([
        dcc.Loading(
            id="loading-individual-content",
            type="default",
            children=html.Div([
                html.Div(id='individual-kpis-container'),
                html.Div(style={'display': 'flex', 'gap': '20px', 'alignItems': 'center', 'marginBottom': '20px', 'marginTop': '20px'}, children=[
                    dcc.Dropdown(id='individual-violation-filter', options=[{'label': v, 'value': v} for v in available_violations], value=list(available_violations), multi=True, placeholder="Filtrar violações...", style={'flex': '1', 'color': '#000'})
                ]),
                dcc.Graph(id='individual-daily-chart', clear_on_unhover=True),
                html.Div(id='ai-section-container', children=[
                    html.H3("Análise do Instrutor Virtual", style={'marginTop': '20px', 'textAlign': 'center'}),
                    html.Div(style={'textAlign': 'center', 'marginTop': '10px', 'marginBottom': '10px'}, children=[
                        dcc.Loading(
                            id="loading-ai-button",
                            type="default",
                            className='dash-loading',
                            children=html.Button('Gerar Análise com IA', id='ai-report-button', n_clicks=0, style={'backgroundColor': colors['accent_purple'], 'color': 'white', 'border': 'none', 'padding': '10px 20px', 'borderRadius': '5px', 'cursor': 'pointer', 'marginRight': '10px'})
                        ),
                    ]),
                    dcc.Textarea(
                        id='ai-report-output', 
                        style={
                            'width': '100%', 
                            'minHeight': '300px', 
                            'padding': '15px', 
                            'border': f"1px solid {colors['border']}", 
                            'borderRadius': '5px', 
                            'backgroundColor': colors['background'], 
                            'color': colors['text'], 
                            'fontFamily': 'sans-serif', 
                            'lineHeight': '1.6',
                            'resize': 'vertical',
                            'fontSize': '14px'
                        },
                        placeholder="Clique em 'Gerar Análise com IA' para obter um relatório personalizado editável..."
                    ),
                ]),
                html.Div(style={'textAlign': 'center', 'marginTop': '20px', 'display': 'flex', 'gap': '10px', 'justifyContent': 'center'}, children=[
                     html.Button('Exportar HTML', id='btn-export-html', n_clicks=0, style={'backgroundColor': colors['accent_blue'], 'color': 'white', 'border': 'none', 'padding': '10px 20px', 'borderRadius': '5px', 'cursor': 'pointer'}),
                ]),
                dcc.Download(id="download-html"),
                html.H4(id='individual-list-header', style={'marginTop': '30px', 'marginBottom': '10px'}),
                html.Div(id='individual-violation-list', style={'maxHeight': '400px', 'overflowY': 'auto', 'paddingRight': '10px'})
            ])
        )
    ])

# Callback para o conteúdo do dashboard individual
@app.callback(
    [Output('individual-kpis-container', 'children'), Output('individual-daily-chart', 'figure'), Output('individual-list-header', 'children'), Output('individual-violation-list', 'children')],
    [Input('driver-dropdown', 'value'), Input('individual-violation-filter', 'value')],
    [State('store-violations-df', 'data')]
)
def update_individual_content(selected_driver, selected_violations, violations_json):
    if selected_driver is None or violations_json is None: 
        raise dash.exceptions.PreventUpdate
    
    # Simular um pequeno delay para mostrar o loading
    time.sleep(0.1)

    violations_df = pd.read_json(violations_json, orient='split')
    violations_df['data_evento'] = pd.to_datetime(violations_df['data_evento'])
    
    driver_df_full = violations_df[violations_df['motorista'] == selected_driver]
    
    total_score = driver_df_full['score_final'].sum()
    total_events = len(driver_df_full)
    main_violation = driver_df_full['violacao'].mode()[0] if not driver_df_full.empty else "Nenhuma"
    worst_day_score = driver_df_full.groupby(driver_df_full['data_evento'].dt.date)['score_final'].sum().max()
    worst_day = driver_df_full.groupby(driver_df_full['data_evento'].dt.date)['score_final'].sum().idxmax() if not pd.isna(worst_day_score) else "N/A"
    
    # Calcula pontuação por categoria
    economica_score = driver_df_full[driver_df_full['violacao'].isin(VIOLATION_CATEGORIES['Econômica'])]['score_final'].sum()
    seguranca_score = driver_df_full[driver_df_full['violacao'].isin(VIOLATION_CATEGORIES['Segurança'])]['score_final'].sum()
    percentual_economica = (economica_score / total_score * 100) if total_score > 0 else 0
    percentual_seguranca = (seguranca_score / total_score * 100) if total_score > 0 else 0
    
    kpis = html.Div([
        html.Div(style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(200px, 1fr))', 'gap': '20px', 'marginBottom': '20px'}, children=[
        html.Div(style=kpi_card_style, children=[html.H4('Pontuação Total', style={'color': colors['text_light']}), html.P(f"{total_score:,.2f}".replace('.', ','), style={'fontSize': '2em', 'fontWeight': 'bold', 'color': colors['accent_red']})]),
        html.Div(style=kpi_card_style, children=[html.H4('Total de Eventos', style={'color': colors['text_light']}), html.P(f"{total_events}", style={'fontSize': '2em', 'fontWeight': 'bold'})]),
            html.Div(style=kpi_card_style, children=[html.H4('Pontuação Econômica', style={'color': colors['text_light']}), html.P(f"{economica_score:,.2f}".replace('.', ','), style={'fontSize': '1.8em', 'fontWeight': 'bold', 'color': CATEGORY_COLORS['Econômica']})]),
            html.Div(style=kpi_card_style, children=[html.H4('Pontuação Segurança', style={'color': colors['text_light']}), html.P(f"{seguranca_score:,.2f}".replace('.', ','), style={'fontSize': '1.8em', 'fontWeight': 'bold', 'color': CATEGORY_COLORS['Segurança']})]),
        html.Div(style=kpi_card_style, children=[html.H4('Violação Principal', style={'color': colors['text_light']}), html.P(main_violation, style={'fontSize': '1.5em', 'fontWeight': 'bold', 'color': colors['accent_yellow']})]),
        html.Div(style=kpi_card_style, children=[html.H4('Dia de Maior Risco', style={'color': colors['text_light']}), html.P(f"{worst_day.strftime('%d/%m') if worst_day != 'N/A' else 'N/A'}", style={'fontSize': '1.5em', 'fontWeight': 'bold'})]),
        ]),
        # Barra de distribuição por categoria
        html.Div(style={'backgroundColor': colors['card_bg'], 'padding': '15px', 'borderRadius': '8px', 'marginBottom': '20px', 'border': f"1px solid {colors['border']}"}, children=[
            html.H4('Distribuição por Categoria', style={'marginTop': 0, 'color': colors['text']}),
            html.P('Este motorista apresenta uma distribuição de violações entre as categorias Econômica e Segurança:'),
            html.Div(style={'display': 'flex', 'gap': '10px', 'marginTop': '10px'}, children=[
                html.Div(f"Econômica: {percentual_economica:.1f}%", style={'flex': 1, 'height': '30px', 'borderRadius': '4px', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center', 'color': 'white', 'fontWeight': 'bold', 'backgroundColor': CATEGORY_COLORS['Econômica']}),
                html.Div(f"Segurança: {percentual_seguranca:.1f}%", style={'flex': 1, 'height': '30px', 'borderRadius': '4px', 'display': 'flex', 'alignItems': 'center', 'justifyContent': 'center', 'color': 'white', 'fontWeight': 'bold', 'backgroundColor': CATEGORY_COLORS['Segurança']}),
            ]),
            html.P([
                html.Strong('Econômica:'), ' Freio motor, RPM excessiva, Marcha lenta, Faixa verde', html.Br(),
                html.Strong('Segurança:'), ' Velocidade excessiva, Freada brusca'
            ], style={'marginTop': '10px', 'fontSize': '0.9em', 'color': colors['text_light']})
        ])
    ])
    
    driver_df_filtered = driver_df_full[driver_df_full['violacao'].isin(selected_violations)]
    daily_scores = driver_df_filtered.groupby(driver_df_filtered['data_evento'].dt.date)['score_final'].sum()
    
    # Criar gráfico simples sem interação de clique
    fig = go.Figure(data=[go.Bar(x=daily_scores.index, y=daily_scores.values, marker_color=colors['accent_yellow'])])
    fig.update_layout(
        title_text=f'Pontuação de Risco por Dia - {selected_driver}',
        title_x=0.5, 
        plot_bgcolor=colors['card_bg'], 
        paper_bgcolor=colors['card_bg'], 
        font_color=colors['text'], 
        yaxis_gridcolor=colors['border'], 
        yaxis_title='Pontuação de Risco', 
        uirevision=selected_driver,
    )

    # Sempre mostrar todas as violações, sem filtro por clique
    list_df = driver_df_filtered
    header = html.Div([
        html.H4(f'Lista de Violações ({len(list_df)} eventos):'),
        html.P("📊 A lista abaixo mostra todas as violações do motorista.", 
               style={'fontSize': '0.9em', 'color': colors['text_light'], 'fontStyle': 'italic', 'marginTop': '5px'})
    ])

    list_items = [html.Div(style={'borderLeft': f"3px solid {colors['accent_red']}", 'padding': '10px', 'marginBottom': '10px', 'backgroundColor': colors['background']}, children=[
        html.P(f"{violation['data_evento'].strftime('%d/%m/%Y %H:%M:%S')} - {violation['violacao']}", style={'fontWeight': 'bold', 'fontSize': '1.1em'}),
        html.P(f"Duração: {violation['duracao']} | Pontos: {f'{violation['score_final']:.2f}'.replace('.', ',')}") ,
        html.A('Ver Percurso no Mapa', href=generate_maps_route_link(violation.get('latitude_inicial'), violation.get('longitude_inicial'), violation.get('latitude_final'), violation.get('longitude_final')), target='_blank', style={'color': colors['accent_blue'], 'textDecoration': 'underline'})
    ]) for _, violation in list_df.sort_values('score_final', ascending=False).iterrows() if pd.notna(violation['data_evento'])]
    
    if not list_items:
        list_items = [html.P("Nenhuma violação encontrada para os filtros selecionados.")]

    return kpis, fig, header, list_items


def get_virtual_instructor_prompt_template():
    """
    Estruturação com Tags XML para estrutura hierárquica, reduzindo a ambiguidade e melhorando a análise do prompt pelo modelo.
    """
    return """
<prompt>
    <system_setup>
        <persona>
            Você é um "Instrutor de Direção Virtual", um especialista em gestão de frotas e análise de telemetria, com a capacidade de interpretar dados para fornecer coaching personalizado e construtivo. Sua missão é ajudar motoristas a aprimorarem suas habilidades, focando em segurança e eficiência.
        </persona>
        <guiding_principles name="Constitutional AI">
            <principle>O feedback deve ser estritamente baseado nos dados fornecidos, sem fazer suposições sobre as intenções ou condições externas não descritas.</principle>
            <principle>O tom deve ser sempre de apoio e construtivo, focando em oportunidades de melhoria, não em erros. A linguagem deve ser clara, respeitosa e educativa.</principle>
            <principle>As recomendações devem ser práticas, acionáveis e diretamente relacionadas aos eventos analisados.</principle>
            <principle>A segurança é o valor fundamental. Priorize sempre a vida e a prevenção de acidentes.</principle>
        </guiding_principles>
    </system_setup>

    <task_definition>
        <goal>Gerar um relatório de melhoria de direção individual e personalizado para o motorista.</goal>
        <output_format>
            O relatório deve ser em Markdown e seguir rigorosamente esta estrutura:
            1.  **Análise Geral:** Uma saudação ao motorista e um resumo do seu desempenho, mencionando a pontuação total e o que ela representa.
            2.  **Pontos de Melhoria Detalhados:** Uma análise das violações mais significativas, explicando o risco e fornecendo uma dica prática para cada uma, incluindo o link do mapa.
            3.  **Recomendação Final:** Uma conclusão com uma dica de ouro, baseada no padrão geral de comportamento observado nos dados.
        </output_format>
    </task_definition>

    <examples>
        <example name="Análise para João Silva">
            <input_data>
                <driver_name>João Silva</driver_name>
                <total_score>85,00</total_score>
                <violations_summary>
- **Violação:** Velocidade excessiva (Pontos: 30,00)
  - **Data:** 01/12/2024 10:15:00
  - **Duração:** 00:01:30
  - **Localização:** <a href="https://www.google.com/maps/dir/-26.30,-48.84/-26.32,-48.85" target="_blank">Ver Percurso</a>
                </violations_summary>
            </input_data>
            <output_report>
### Análise do Instrutor Virtual: João Silva

Olá, João! Analisamos seu desempenho e alguns pontos de atenção que podemos trabalhar para tornar sua condução ainda mais segura e eficiente.

#### Pontos de Melhoria com Contexto

* **Violação: Velocidade excessiva (30,00 pontos) em 01/12/2024 10:15:00**
    * **Risco Associado:** O excesso de velocidade, mesmo que por um curto período, aumenta drasticamente a distância necessária para frenagem e o risco de acidentes graves, além de impactar o consumo.
    * **Dica Prática:** Em trechos de rodovia, é fundamental manter a velocidade de cruzeiro compatível com o limite da via e as condições do tráfego. Utilizar o piloto automático (se disponível) pode ajudar a manter a constância.
    * **Local da Ocorrência:** <a href="https://www.google.com/maps/dir/-26.30,-48.84/-26.32,-48.85" target="_blank">Ver Percurso no Mapa</a>

#### Recomendação Final

Notamos que a principal violação foi pontual. A dica de ouro é sempre realizar uma checagem mental dos limites da via ao entrar em um novo trecho, especialmente em rodovias de grande movimento. Manter a atenção a essa variação de velocidade é a chave para uma viagem perfeita. Parabéns pelo bom trabalho e continue se aprimorando!
            </output_report>
        </example>
    </examples>

    <final_task>
        <context>
            <driver_name>{driver_name}</driver_name>
            <total_score>{total_score}</total_score>
        </context>
        <input_data>
            <violations_summary>{violations_summary}</violations_summary>
        </input_data>
        <instruction>
        Execute a análise e gere o relatório para o motorista especificado, seguindo rigorosamente o formato e as diretrizes.
        </instruction>
    </final_task>
</prompt>
"""

def generate_virtual_instructor_report(driver_name, driver_df):
    """
    Gera um relatório de melhoria de direção usando um LLM.
    Esta função orquestra a chamada para a API do modelo de linguagem.
    """

    # 1. Análise e Síntese dos Dados Chain-of-Thought (CoT)
    if driver_df.empty:
        return "Não há dados de violação para gerar a análise."

    total_score = driver_df['score_final'].sum()
    top_violations = driver_df.sort_values('score_final', ascending=False).head(3)

    violations_summary = ""
    for _, row in top_violations.iterrows():
        map_link_url = generate_maps_route_link(row.get('latitude_inicial'), row.get('longitude_inicial'), row.get('latitude_final'), row.get('longitude_final'))
        map_link_html = f'<a href="{map_link_url}" target="_blank" style="color: #3B82F6; text-decoration: underline;">Ver Percurso</a>'
        
        # Formata a pontuação com 2 casas decimais e vírgula como separador decimal
        score_formatted = f"{row['score_final']:.2f}".replace('.', ',')
        
        details = f"- **Violação:** {row['violacao']} (Pontos: {score_formatted})\n"
        details += f"  - **Data:** {row['data_evento'].strftime('%d/%m/%Y %H:%M:%S')}\n"
        if row['duracao'] != "00:00:00":
             details += f"  - **Duração:** {row['duracao']}\n"
        if row.get('velocidade_maxima', 0) > 0:
            details += f"  - **Velocidade Máxima:** {row.get('velocidade_maxima', 'N/A')} km/h\n"
        if row.get('rpm_maximo', 0) > 0:
            details += f"  - **RPM Máximo:** {row.get('rpm_maximo', 'N/A')}\n"
        details += f"  - **Localização:** {map_link_html}\n"
        violations_summary += details

    # 2. Construção do Prompt Final
    prompt_template = get_virtual_instructor_prompt_template()
    final_prompt = prompt_template.format(
        driver_name=driver_name,
        total_score=f"{total_score:.2f}".replace('.', ','),
        violations_summary=violations_summary
    )
    
    # 3. Chamada à API do LLM
    try:
        apiKey = os.getenv('GEMINI_API_KEY')
        if not apiKey:
            return "Erro: A chave da API não foi configurada. Verifique se a variável GEMINI_API_KEY está definida no arquivo .env"

        apiUrl = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={apiKey}"
        
        payload = {
            "contents": [{"role": "user", "parts": [{"text": final_prompt}]}],
             "generationConfig": {
                "temperature": 0.4,
                "topP": 1,
                "topK": 32,
                "maxOutputTokens": 4096,
            }
        }
        
        response = requests.post(apiUrl, json=payload, headers={'Content-Type': 'application/json'}, timeout=90)
        response.raise_for_status()
        
        result = response.json()
        
        # (Self-Correction/Reflection)
        if result.get('candidates') and result['candidates'][0]['content']['parts']:
            text = result['candidates'][0]['content']['parts'][0]['text']
            return text 
        else:
            print(f"Resposta inesperada da API para {driver_name}: {result}")
            return "Não foi possível gerar a análise. A resposta da IA estava em um formato inesperado."

    except requests.exceptions.RequestException as e:
        print(f"Erro de conexão ao gerar a análise para {driver_name}: {e}")
        return f"Erro de conexão ao gerar a análise. Verifique sua rede e a chave da API."
    except Exception as e:
        print(f"Ocorreu um erro inesperado ao gerar a análise para {driver_name}: {e}")
        return f"Ocorreu um erro inesperado ao gerar a análise."



# Callback para gerar relatório de IA
@app.callback(
    Output('ai-report-output', 'value'),
    [Input('ai-report-button', 'n_clicks')],
    [State('driver-dropdown', 'value'), State('store-violations-df', 'data')]
)
def generate_ai_report(n_clicks, selected_driver, violations_json):
    if n_clicks == 0 or not selected_driver or not violations_json:
        return ""

    violations_df = pd.read_json(violations_json, orient='split')
    violations_df['data_evento'] = pd.to_datetime(violations_df['data_evento'])
    driver_df = violations_df[violations_df['motorista'] == selected_driver]
    
    # Chama a nova função otimizada com técnicas avançadas
    ai_report_text = generate_virtual_instructor_report(selected_driver, driver_df)
    
    # Retorna o texto simples para edição
    return ai_report_text

# Callback para exportação HTML
@app.callback(
    Output("download-html", "data"),
    Input("btn-export-html", "n_clicks"),
    [State('driver-dropdown', 'value'), 
     State('store-violations-df', 'data'),
     State('ai-report-output', 'value')], 
    prevent_initial_call=True,
)
def export_html(n_clicks, selected_driver, violations_json, ai_report_text):
    if n_clicks is None or n_clicks == 0 or not selected_driver or not violations_json:
        raise dash.exceptions.PreventUpdate

    violations_df = pd.read_json(violations_json, orient='split')
    violations_df['data_evento'] = pd.to_datetime(violations_df['data_evento'])
    driver_df = violations_df[violations_df['motorista'] == selected_driver].sort_values('score_final', ascending=False)
    
    total_score = driver_df['score_final'].sum()
    total_events = len(driver_df)
    main_violation = driver_df['violacao'].mode()[0] if not driver_df.empty else "Nenhuma"
    worst_day_score = driver_df.groupby(driver_df['data_evento'].dt.date)['score_final'].sum().max()
    worst_day = driver_df.groupby(driver_df['data_evento'].dt.date)['score_final'].sum().idxmax() if not pd.isna(worst_day_score) else "N/A"
    
    kpi_html = f"""
        <div class="kpi-card"><h3>Total de Eventos</h3><p>{total_events}</p></div>
        <div class="kpi-card"><h3>Violação Principal</h3><p>{main_violation}</p></div>
        <div class="kpi-card"><h3>Dia de Maior Risco</h3><p>{worst_day.strftime('%d/%m') if worst_day != 'N/A' else 'N/A'}</p></div>
    """

    daily_scores = driver_df.groupby(driver_df['data_evento'].dt.date)['score_final'].sum()
    chart_data = {'x': [d.strftime('%Y-%m-%d') for d in daily_scores.index], 'y': daily_scores.values.tolist()}

    # Usa o texto editado do textarea, ou gera um novo se estiver vazio
    if ai_report_text and ai_report_text.strip():
        ai_text_html = markdown(ai_report_text, extensions=['extra'])
    else:
        # Gera um novo relatório se o textarea estiver vazio
        ai_report_text = generate_virtual_instructor_report(selected_driver, driver_df)
        ai_text_html = markdown(ai_report_text, extensions=['extra'])

    list_html = "<div class='table-container'><table><thead><tr><th>Data e Hora - Violação</th><th>Info</th><th>Mapa</th></tr></thead><tbody>"
    for _, row in driver_df.iterrows():
        map_link = generate_maps_route_link(row.get('latitude_inicial'), row.get('longitude_inicial'), row.get('latitude_final'), row.get('longitude_final'))
        
        list_html += f"<tr><td>{row['data_evento'].strftime('%d/%m/%Y %H:%M:%S')} - {row['violacao']}</td><td>Duração: {row['duracao']} | Pontos: {f'{row['score_final']:.2f}'.replace('.', ',')}</td><td><a href='{map_link}' target='_blank'>Ver Percurso no Mapa</a></td></tr>"
    list_html += "</tbody></table></div>"

    html_string = f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta charset="UTF-8">
            <title>Relatório - {selected_driver}</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 15px; background-color: #111827; color: #E5E7EB; }}
                h1, h2, h3, h4 {{ color: #FFF; }}
                .container {{ max-width: 900px; margin: auto; }}
                .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 20px; }}
                .kpi-card {{ background-color: #1F2937; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #374151; }}
                .kpi-card h3 {{ margin: 0 0 10px 0; color: #9CA3AF; font-size: 0.9em; }}
                .kpi-card p {{ margin: 0; font-size: 1.8em; font-weight: bold; }}
                .chart-container {{ background-color: #1F2937; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                .violation-list-container {{ margin-top: 20px; }}
                .table-container {{ max-height: 400px; overflow-y: auto; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ padding: 8px 12px; border: 1px solid #374151; text-align: left; }}
                thead {{ background-color: #374151; position: sticky; top: 0; }}
                tbody tr:nth-child(even) {{ background-color: #1F2937; }}
                .ai-report {{ margin-top: 20px; padding: 15px; border-radius: 5px; background-color: #1F2937; border: 1px solid #374151; }}
                .ai-report h1, .ai-report h2, .ai-report h3, .ai-report p, .ai-report ul, .ai-report li {{ color: #E5E7EB !important; border: none; }}
                .satisfaction-survey {{ margin-top: 20px; padding: 15px; border-radius: 5px; background-color: #1F2937; border: 1px solid #374151; }}
                .satisfaction-survey iframe {{ border-radius: 5px; }}
                a {{ color: #3B82F6; }}
                @media print {{ 
                    body {{ background-color: #FFF; color: #000; }} 
                    h1, h2, h3, h4, .ai-report h1, .ai-report h2, .ai-report h3, .ai-report p, .ai-report ul, .ai-report li {{ color: #000 !important; }}
                    .kpi-card, .chart-container, .ai-report, .violation-list-container, table, th, td {{ background-color: #FFF !important; border: 1px solid #ddd; color: #000; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Relatório de Desempenho - {selected_driver}</h1>
                <div class="kpi-grid">{kpi_html}</div>
                
                <div class="chart-container">
                    <canvas id="reportChart"></canvas>
                </div>
                <div class="violation-list-container">
                    <h4>Lista de Violações ({len(driver_df)} eventos)</h4>
                    {list_html}
                </div>
                <div class="ai-report">
                    <h2>Análise do Instrutor Virtual</h2>
                    {ai_text_html}
                </div>
                <!-- <div class="satisfaction-survey">
                    <h2>Pesquisa de Satisfação</h2>
                    <p>Sua opinião é muito importante para nós! Por favor, reserve um momento para avaliar este relatório.</p>
                    <iframe src="https://docs.google.com/forms/d/e/1FAIpQLSfu_h1b_gY2n2f_g_g_g_g_g_g_g_g_g_g_g_g_g_g_g_g/viewform?embedded=true" width="100%" height="600" frameborder="0" marginheight="0" marginwidth="0">Carregando…</iframe>
                </div> -->
            </div>
            <script>
                const ctx = document.getElementById('reportChart').getContext('2d');
                new Chart(ctx, {{
                    type: 'bar',
                    data: {{
                        labels: {json.dumps(chart_data.get('x', []))},
                        datasets: [{{
                            label: 'Pontuação de Risco por Dia',
                            data: {json.dumps(chart_data.get('y', []))},
                            backgroundColor: '#F59E0B'
                        }}]
                    }},
                    options: {{
                        scales: {{
                            y: {{ beginAtZero: true }}
                        }}
                    }}
                }});
            </script>
        </body>
    </html>
    """
    
    return dict(content=html_string, filename=f"relatorio_{selected_driver}.html")

# Callback para acionar a impressão para PDF
@app.callback(
    Output('individual-dashboard-output', 'children', allow_duplicate=True),
    Input("btn-export-pdf", "n_clicks"),
    prevent_initial_call=True,
)
def export_pdf(n_clicks):
    if n_clicks > 0:
        return html.Script("window.print()")
    return dash.no_update

# Callback para mostrar o botão 'Voltar para Análise' na tela de upload
@app.callback(
    Output('back-to-dashboard-btn-container', 'children'),
    [Input('store-violations-df', 'data'), Input('main-dashboard-content', 'style'), Input('initial-setup-container', 'style')]
)
def show_back_to_dashboard_btn(violations_data, dashboard_style, setup_style):
    # Só mostra o botão se já houver dados carregados e a tela de upload estiver visível
    if violations_data is not None and (setup_style is None or setup_style.get('display', 'block') == 'block'):
        return html.Div([
            html.Button([
                html.Span('⬅️', style={'fontSize': '16px', 'marginRight': '8px'}),
                'Voltar para Análise'
            ], id='btn-back-to-dashboard', n_clicks=0, style={
                'backgroundColor': colors['accent_blue'],
                'color': 'white',
                'border': 'none',
                'padding': '12px 24px',
                'borderRadius': '8px',
                'cursor': 'pointer',
                'fontWeight': '600',
                'fontSize': '14px',
                'marginBottom': '20px',
                'marginTop': '10px',
                'transition': 'all 0.3s ease',
                'boxShadow': '0 2px 4px rgba(59, 130, 246, 0.2)',
                'display': 'flex',
                'alignItems': 'center',
                'gap': '8px',
                'marginLeft': 'auto',
                'marginRight': 'auto'
            })
        ], style={'textAlign': 'center'})
    return None

# Callback para voltar ao dashboard ao clicar no botão
@app.callback(
    [Output('initial-setup-container', 'style', allow_duplicate=True), Output('main-dashboard-content', 'style', allow_duplicate=True)],
    [Input('btn-back-to-dashboard', 'n_clicks')],
    prevent_initial_call=True
)
def back_to_dashboard(n_clicks):
    if n_clicks and n_clicks > 0:
        return {'display': 'none'}, {'display': 'block'}
    return dash.no_update, dash.no_update

# --- BLOCO DE EXECUÇÃO ---
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
