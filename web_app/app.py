import streamlit as st
import os
import logging

# Включаем подробное логирование Streamlit
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Проверяем загрузку страниц
st.sidebar.write("### Отладка страниц")
try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    ctx = get_script_run_ctx()
    if ctx and ctx.page_script_hash:
        st.sidebar.write(f"Текущая страница: {ctx.page_script_hash}")

    # Проверяем, какие страницы обнаружены
    if hasattr(st, '_main_run_count'):
        st.sidebar.write("Обнаруженные страницы:")
        for page in st._get_all_pages():
            st.sidebar.write(f"- {page['page_name']}")
except Exception as e:
    st.sidebar.error(f"Ошибка при проверке страниц: {str(e)}")