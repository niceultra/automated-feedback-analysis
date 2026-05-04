import streamlit as st
import pandas as pd
import psycopg2
import streamlit.components.v1 as components

# --- ДАННЫЕ ПОДКЛЮЧЕНИЯ ---
DB_HOST = st.secrets["DB_HOST"]
DB_NAME = st.secrets["DB_NAME"]
DB_USER = st.secrets["DB_USER"]
DB_PASS = st.secrets["DB_PASS"]

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=6432,
        sslmode='require'
    )

def get_all_products():
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT nm_id, category_name, product_name, product_url FROM products", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame(columns=['nm_id', 'category_name', 'product_name', 'product_url'])

# --- ФУНКЦИИ ХЕЛПЕРЫ ---
def color_sentiment(val):
    if val == 2 or val == 'Positive': return 'color: #4caf50; font-weight: bold;'
    if val == 1 or val == 'Negative': return 'color: #f44336; font-weight: bold;'
    return 'color: #9e9e9e;'

# --- СТРАНИЦА: ГЛАВНАЯ ---
st.title("Мониторинг каталога")
st.markdown("<p style='opacity: 0.6;'>Аналитическая точность и инсайты вашего бренда</p>", unsafe_allow_html=True)

# Метрики
m1, m2, m3 = st.columns(3)
product_df = get_all_products()
m1.metric("Товаров в базе", len(product_df))
m2.metric("Активность системы", "Высокая")
m3.metric("Точность BERT", "94%", delta="↑ 2%")

st.divider()

st.markdown('<div class="section-title">📦 База товаров для анализа</div>', unsafe_allow_html=True)

search_query = st.text_input("Поиск по категориям", placeholder="Например: Красота", label_visibility="collapsed")

if not product_df.empty:
    categories = product_df['category_name'].unique()
    if search_query:
        categories = [cat for cat in categories if search_query.lower() in cat.lower()]

    for category in categories:
        with st.expander(f"📦 {category}", expanded=False):
            cat_prods = product_df[product_df['category_name'] == category]
            for _, row in cat_prods.iterrows():
                is_active = st.session_state.get('current_sku') == row['nm_id']
                button_label = f"✅ {row['product_name']}" if is_active else f"▫️ {row['product_name']}"

                if st.button(button_label, key=f"btn_{row['nm_id']}", use_container_width=True):
                    st.session_state.current_sku = row['nm_id']
                    st.session_state.current_category = category
                    st.rerun()

if st.session_state.get('current_sku'):
    st.write("")
    selected_name = product_df[product_df['nm_id'] == st.session_state.current_sku]['product_name'].values[0]
    st.info(f"Выбран товар: **{selected_name}**")

    if st.button("🚀 Перейти к детальной аналитике", type="primary", use_container_width=True):
        st.switch_page("pages/2_Аналитика.py")

st.divider()

st.subheader("Полный список артикулов")
if not product_df.empty:
    display_list = product_df[['nm_id', 'product_name', 'category_name']].rename(
        columns={'nm_id': 'ID', 'product_name': 'Наименование', 'category_name': 'Категория'}
    )
    st.dataframe(display_list, use_container_width=True, hide_index=True)