import os
import streamlit as st
from PIL import Image


def local_css(file_name):
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(parent_dir, file_name)

    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    else:
        st.error(f"Файл {file_name} не найден по пути: {file_path}")


# 1. Настройка страницы
st.set_page_config(
    page_title="InsightCopy AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Подключаем стили
local_css("style.css")

# Боковая панель (Streamlit автоматически добавит навигацию по страницам)
with st.sidebar:
    st.title("📂 InsightCopy AI")
    st.caption("Sentiment Analysis Dashboard")
    st.divider()

    # Streamlit автоматически добавит здесь навигацию по страницам из папки pages
    st.markdown("### Дополнительные настройки")
    # Здесь могут быть другие элементы управления